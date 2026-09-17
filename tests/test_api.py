"""api.py — FastAPI ต่อ temp DB (ต้อง set SL_DB ก่อน import api)"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["SL_DB"] = tempfile.mktemp(suffix=".db")

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from store import init_db, upsert_posts  # noqa: E402

GID = "123"  # ไม่อยู่ใน config.toml — _group_info fallback ใช้ตามนั้น


def _ts(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


FETCHED_AT = _ts(1)


def _post(pid, body, created, r=0, c=0, s=0):
    return {"post_id": pid, "poster_name": "สมชาย", "body": body,
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
    assert d7["top_posters"][0] == {"name": "สมชาย", "count": 3}
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
