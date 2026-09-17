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
