"""api.py — FastAPI ต่อ temp DB (ต้อง set SL_DB ก่อน import api)"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["SL_DB"] = tempfile.mktemp(suffix=".db")

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sentiment import SentimentResult  # noqa: E402
from store import init_db, save_sentiment, upsert_posts  # noqa: E402

GID = "123"  # ไม่อยู่ใน config.toml — _group_info fallback ใช้ตามนั้น


def _ts(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


FETCHED_AT = _ts(1)


def _post(pid, body, created, r=0, c=0, s=0, poster="สมชาย"):
    return {"post_id": pid, "poster_name": poster, "body": body,
            "created_at": created, "reaction_count": r, "comment_count": c,
            "share_count": s, "permalink": f"https://facebook.com/p/{pid}"}


def _seed():
    conn = init_db(api.DB)
    upsert_posts(conn, GID, [
        _post("a", "flashsale 50% ชื้อวันนี้", _ts(30), 5, 1, 0),
        _post("b", "flashsale 30% สินค้าใหม่", _ts(2), 2, 2, 2),
        _post("c", "review สินค้าอีกตัว", _ts(70), 9, 0, 0),
    ], FETCHED_AT)
    conn.commit()
    return conn


_seed()
client = TestClient(api.app)


def test_health():
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["last_fetched"] == FETCHED_AT


def test_posts_q_filters():
    d = client.get("/posts", params={"group_id": GID, "q": "flashsale"}).json()
    assert d["total"] == 2
    assert {p["post_id"] for p in d["posts"]} == {"a", "b"}


def test_posts_poster_and_date_filters():
    d = client.get("/posts", params={"group_id": GID, "poster": "สม"}).json()
    assert d["total"] == 3
    d = client.get("/posts", params={"group_id": GID, "since": _ts(3)}).json()
    assert [p["post_id"] for p in d["posts"]] == ["b"]  # b = 2 ชม. อยู่หลัง since
    d = client.get("/posts", params={"group_id": GID, "until": _ts(40)}).json()
    assert [p["post_id"] for p in d["posts"]] == ["c"]  # c = 70 ชม. อยู่ก่อน until


def test_posts_sort_engagement():
    d = client.get("/posts", params={"group_id": GID, "sort": "engagement"}).json()
    # c=9, a=6, b=6 (b ใหม่กว่า a → ชนะ tie)
    assert [p["post_id"] for p in d["posts"]] == ["c", "b", "a"]


def test_posts_pagination_date_desc():
    d = client.get("/posts", params={"group_id": GID, "limit": 2, "offset": 1}).json()
    # date desc ทั้งหมด = b, a, c
    assert d["total"] == 3
    assert [p["post_id"] for p in d["posts"]] == ["a", "c"]


def test_detail_ok():
    p = client.get("/posts/c", params={"group_id": GID}).json()
    assert p["post_id"] == "c"
    assert p["body"].startswith("review")
    assert "flashsale" not in p["keywords"]


def test_detail_404():
    assert client.get("/posts/nope", params={"group_id": GID}).status_code == 404


def test_stats_window_and_keyword_dedupe():
    d1 = client.get("/stats", params={"group_id": GID, "days": 1}).json()
    assert d1["total_posts"] == 1  # เฉพาะ b (2 ชม.)
    assert d1["new_since_yesterday"] == 1
    flash1 = next(k for k in d1["top_keywords"] if k["word"] == "flashsale")
    assert flash1["count"] == 1  # 1 ครั้ง/โพสต์
    d7 = client.get("/stats", params={"group_id": GID, "days": 7}).json()
    assert d7["total_posts"] == 3
    flash7 = next(k for k in d7["top_keywords"] if k["word"] == "flashsale")
    assert flash7["count"] == 2  # a + b
    assert d7["top_posters"][0] == {"name": "สมชาย", "count": 3, "avg_engagement": 7.0}
    assert d7["top_posts"][0]["post_id"] == "c"  # engagement 9 สูงสุด


def test_stats_tolerates_null_keywords():
    conn = init_db(api.DB)
    conn.execute(
        "INSERT INTO posts (post_id, group_id, poster_name, body, created_at, fetched_at,"
        " reaction_count, comment_count, share_count, permalink, keywords)"
        " VALUES ('nullkw', ?, 'x', 'old post no keywords', ?, ?, 1, 0, 0, NULL, NULL)",
        (GID, _ts(1), FETCHED_AT),
    )
    conn.commit()
    try:
        d = client.get("/stats", params={"group_id": GID, "days": 1}).json()
        assert d["total_posts"] == 2  # b + nullkw — ไม่ crash กับ keywords NULL
    finally:
        conn.execute("DELETE FROM posts WHERE post_id='nullkw'")
        conn.commit()


def test_stats_default_group_and_zero_state():
    # ไม่ส่ง group_id → groups[0] จาก config.toml (รันจาก repo root เท่านั้น)
    d = client.get("/stats").json()
    assert d["group"] == "กลุ่มเป้าหมาย"
    assert d["total_posts"] == 0  # temp DB ไม่มีโพสต์ของ group นี้ → zero state
    assert d["top_keywords"] == []


CONFIG_PATH = Path("config.toml")


def _write_config(groups):
    # (name, gid) — tests รันจาก repo root เท่านั้น
    text = "".join(
        f'[[groups]]\nname = "{name}"\nurl = "https://www.facebook.com/groups/{gid}"\n'
        for name, gid in groups)
    CONFIG_PATH.write_text(text, encoding="utf-8")


def test_groups_lists_config_order():
    orig = CONFIG_PATH.read_text(encoding="utf-8")
    _write_config([("g1", GID), ("g2", "456")])
    try:
        d = client.get("/groups").json()
        assert d == {"groups": [
            {"name": "g1", "group_id": GID},
            {"name": "g2", "group_id": "456"},
        ]}
    finally:
        CONFIG_PATH.write_text(orig, encoding="utf-8")


def test_compare_all_groups_sov_and_sample_size():
    orig = CONFIG_PATH.read_text(encoding="utf-8")
    _write_config([("g1", GID), ("g2", "456"), ("g3-empty", "789")])
    try:
        conn = init_db(api.DB)
        upsert_posts(conn, "456", [
            _post("d", "flashsale 20% ระวัง", _ts(20), 1, 0, 0),
            _post("e", "เรื่องอื่น", _ts(50)),
        ], FETCHED_AT)
        conn.commit()
        d = client.get("/stats/compare", params={"days": 2}).json()
        assert d["total_posts"] == 3  # g1: a(30h)+b(2h) · g2: d(20h) · c/e อยู่นอก 2 วัน
        g1 = next(g for g in d["groups"] if g["group_id"] == GID)
        g2 = next(g for g in d["groups"] if g["group_id"] == "456")
        g3 = next(g for g in d["groups"] if g["group_id"] == "789")
        assert g1["sample_size"] == 2
        assert abs(g1["share_of_voice"] - 2 / 3) < 1e-9
        assert g1["avg_engagement"] == 6.0  # a=6 + b=6
        assert g2["share_of_voice"] == 1 / 3
        assert g3["sample_size"] == 0
        assert g3["share_of_voice"] == 0.0  # กลุ่มว่าง → 0% ไม่ error
        assert g3["avg_engagement"] == 0.0
        assert g3["top_keywords"] == []
        assert g1["keyword_delta"]["sample_size"] == {"first_half": 1, "second_half": 1}
        fl = next(i for i in g1["keyword_delta"]["items"] if i["word"] == "flashsale")
        assert (fl["first_half"], fl["second_half"]) == (1, 1)  # a=ก่อนกลาง, b=หลังกลาง
        assert "flashsale" in {s["word"] for s in d["shared_keywords"]}  # g1 ∩ g2
    finally:
        CONFIG_PATH.write_text(orig, encoding="utf-8")


def test_compare_zero_posts_no_error():
    orig = CONFIG_PATH.read_text(encoding="utf-8")
    _write_config([("empty-only", "778")])
    try:
        d = client.get("/stats/compare").json()
        assert d["total_posts"] == 0
        assert d["groups"][0]["share_of_voice"] == 0.0
        assert d["shared_keywords"] == []
    finally:
        CONFIG_PATH.write_text(orig, encoding="utf-8")


def test_stats_top_posters_ranked_by_avg_engagement():
    conn = init_db(api.DB)
    upsert_posts(conn, "555", [
        _post("big", "kol post", _ts(5), 50, 0, 0, poster="KOL"),
        _post("y1", "y post", _ts(6), 1, 0, 0, poster="Y"),
        _post("y2", "y post", _ts(7), 1, 0, 0, poster="Y"),
    ], FETCHED_AT)
    conn.commit()
    d = client.get("/stats", params={"group_id": "555", "days": 7}).json()
    # KOL โพสต์น้อยแต่ engagement ต่อโพสต์สูงกว่า Y (โพสต์เยอะ) → เรียงอันดับตาม influence
    assert d["top_posters"][0] == {"name": "KOL", "count": 1, "avg_engagement": 50.0}
    assert d["top_posters"][1] == {"name": "Y", "count": 2, "avg_engagement": 1.0}


def test_stats_sentiment_breakdown():
    conn = init_db(api.DB)
    upsert_posts(conn, "888", [
        _post("s1", "ของดี คุ้มราคา", _ts(50)),
        _post("s2", "แย่มาก ไม่แนะนำ", _ts(60)),
        _post("s3", "โพสต์กลาง ๆ", _ts(70)),
    ], FETCHED_AT)
    save_sentiment(conn, "888", "s1", SentimentResult("positive", "ชมสินค้า", "product", "m", "1"))
    save_sentiment(conn, "888", "s2", SentimentResult("negative", "บ่นเรื่องสินค้า", "product", "m", "1"))
    conn.commit()
    d = client.get("/stats", params={"group_id": "888", "days": 7}).json()
    assert d["sentiment"] == [
        {"label": "positive", "count": 1, "pct": 1 / 3},
        {"label": "neutral", "count": 0, "pct": 0.0},
        {"label": "negative", "count": 1, "pct": 1 / 3},
        {"label": "unanalyzed", "count": 1, "pct": 1 / 3},
    ]
    p = client.get("/posts/s1", params={"group_id": "888"}).json()
    assert p["sentiment"] == "positive"
    assert p["summary"] == "ชมสินค้า"
    # total=0 (ทุกโพสต์อยู่นอก 1 วัน) → 4 entries หมด count/pct = 0 ไม่ crash
    d0 = client.get("/stats", params={"group_id": "888", "days": 1}).json()
    assert d0["total_posts"] == 0
    assert d0["sentiment"] == [
        {"label": lab, "count": 0, "pct": 0.0}
        for lab in ("positive", "neutral", "negative", "unanalyzed")
    ]


TL_GID = "666"
BKK = timezone(timedelta(hours=7))


def test_timeline_daily_buckets_bangkok():
    bkk_now = datetime.now(timezone.utc).astimezone(BKK)
    today0 = bkk_now.replace(hour=0, minute=0, second=0, microsecond=0)
    conn = init_db(api.DB)
    upsert_posts(conn, TL_GID, [
        _post("t1", "alpha beta", (today0 + timedelta(hours=1)).isoformat(), 5, 0, 0),
        _post("t2", "alpha gamma", (today0 + timedelta(hours=2)).isoformat(), 1, 1, 0),
        # 23:59 BKK = เมื่อวาน — ทั้งที่ใน UTC ยังเป็น "วันนี้" (กรณีข้ามเขตเวลา)
        _post("t3", "delta", (today0 - timedelta(minutes=1)).isoformat(), 2, 0, 0),
    ], FETCHED_AT)
    conn.commit()
    d = client.get("/stats/timeline", params={"days": 3, "group_id": TL_GID}).json()
    assert d["timezone"] == "Asia/Bangkok"
    assert len(d["buckets"]) == 3
    assert [b["date"] for b in d["buckets"][-2:]] == [
        (today0 - timedelta(days=1)).date().isoformat(),
        today0.date().isoformat(),
    ]
    tb, yb = d["buckets"][-1], d["buckets"][-2]
    assert (tb["posts"], tb["engagement"], tb["top_keyword"]) == (2, 7, "alpha")
    assert (yb["posts"], yb["engagement"], yb["top_keyword"]) == (1, 2, "delta")
    assert (d["buckets"][0]["posts"], d["buckets"][0]["top_keyword"]) == (0, None)
