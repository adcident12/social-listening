import json
import sqlite3
from sentiment import SentimentResult
from store import fetch_recent, init_db, upsert_comments, upsert_posts, pending_sentiment, save_sentiment

def _posts():
    return [
        {"post_id": "p1", "poster_name": "A", "body": "hello",
         "created_at": "2026-09-14T10:00:00+00:00",
         "reaction_count": 3, "comment_count": 1, "permalink": "https://x/1"},
        {"post_id": "p2", "poster_name": "B", "body": "world",
         "created_at": "2026-09-15T09:00:00+00:00",
         "reaction_count": 0, "comment_count": 0, "permalink": "https://x/2"},
    ]

def test_upsert_dedupes_on_post_id(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T01:00:00+00:00")
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 2

def test_upsert_updates_reactions(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    updated = [dict(_posts()[0], reaction_count=99)]
    upsert_posts(conn, "g1", updated, "2026-09-15T01:00:00+00:00")
    row = conn.execute("SELECT reaction_count FROM posts WHERE post_id='p1'").fetchone()
    assert row[0] == 99

def test_fetch_recent_filters_since_and_sorts_desc(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    rows = fetch_recent(conn, "g1", "2026-09-15T00:00:00+00:00")
    assert [r["post_id"] for r in rows] == ["p2"]
    rows = fetch_recent(conn, "g1", "2020-01-01T00:00:00+00:00")
    assert [r["post_id"] for r in rows] == ["p2", "p1"]

def test_upsert_populates_keywords(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", [
        {"post_id": "p1", "poster_name": "A", "body": "flashsale flashsale review",
         "created_at": "2026-09-14T10:00:00+00:00",
         "reaction_count": 0, "comment_count": 0, "permalink": "https://x/1"},
    ], "2026-09-15T00:00:00+00:00")
    row = conn.execute("SELECT keywords FROM posts WHERE post_id='p1'").fetchone()
    kws = json.loads(row[0])
    assert kws.count("flashsale") == 1  # dedupe — 1 คำต่อโพสต์
    assert "review" in kws


def test_posts_has_sentiment_columns(tmp_path):
    conn = init_db(tmp_path / "t.db")
    cols = {c[1] for c in conn.execute("PRAGMA table_info(posts)")}
    for c in ("sentiment", "summary", "theme", "model_version", "prompt_version"):
        assert c in cols


def test_init_db_migrates_old_posts_table(tmp_path):
    db = tmp_path / "old.db"
    old = sqlite3.connect(str(db))
    old.execute("""CREATE TABLE posts (post_id TEXT NOT NULL, group_id TEXT NOT NULL,
        poster_name TEXT, body TEXT, created_at TEXT, fetched_at TEXT NOT NULL,
        reaction_count INTEGER DEFAULT 0, comment_count INTEGER DEFAULT 0,
        share_count INTEGER DEFAULT 0, permalink TEXT, keywords TEXT,
        PRIMARY KEY (post_id, group_id))""")
    old.execute("INSERT INTO posts (post_id, group_id, body, fetched_at) VALUES ('p1','g1','hi','2026-09-15T00:00:00+00:00')")
    old.commit()
    old.close()
    conn = init_db(db)  # ต้อง migrate ไม่ crash
    cols = {c[1] for c in conn.execute("PRAGMA table_info(posts)")}
    assert "sentiment" in cols and "theme" in cols
    assert conn.execute("SELECT body FROM posts WHERE post_id='p1'").fetchone()[0] == "hi"


def test_init_db_migrates_old_alerts_table(tmp_path):
    db = tmp_path / "old.db"
    old = sqlite3.connect(str(db))
    old.execute("""CREATE TABLE alerts (post_id TEXT NOT NULL, rule TEXT NOT NULL,
        fired_at TEXT NOT NULL, UNIQUE (post_id, rule))""")
    old.execute("INSERT INTO alerts VALUES ('n1','negative','2026-09-19T00:00:00+00:00')")
    old.commit()
    old.close()
    conn = init_db(db)  # ต้อง migrate ไม่ crash
    cols = {c[1] for c in conn.execute("PRAGMA table_info(alerts)")}
    assert "group_id" in cols
    assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 1  # row เก่ายังอยู่ (group_id = NULL)


def test_upsert_comments(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    n = upsert_comments(conn, "g1", [
        {"post_id": "p1", "comments": [
            {"poster_name": "C1", "body": "comment one", "created_at": "2026-09-14T11:00:00+00:00", "reaction_count": 2},
            {"poster_name": "C2", "body": "comment two"},
        ]},
        {"post_id": "p2", "comments": []},
    ], "2026-09-15T00:00:00+00:00")
    assert n == 2
    rows = conn.execute("SELECT poster_name, body FROM comments WHERE post_id='p1' ORDER BY poster_name").fetchall()
    assert rows == [("C1", "comment one"), ("C2", "comment two")]


def test_upsert_comments_dedupes_and_updates(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    cs = [{"post_id": "p1", "comments": [
        {"poster_name": "C1", "body": "comment one", "created_at": None, "reaction_count": 2},
    ]}]
    upsert_comments(conn, "g1", cs, "2026-09-15T00:00:00+00:00")
    upsert_comments(conn, "g1", [dict(cs[0], comments=[dict(cs[0]["comments"][0], reaction_count=5)])],
                    "2026-09-15T01:00:00+00:00")
    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1
    assert conn.execute("SELECT reaction_count FROM comments").fetchone()[0] == 5


def test_pending_sentiment_and_save(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    upsert_posts(conn, "g2", _posts(), "2026-09-15T00:00:00+00:00")  # อีกกลุ่ม — ห้ามปน
    assert {r["post_id"] for r in pending_sentiment(conn, "g1")} == {"p1", "p2"}
    save_sentiment(conn, "g1", "p1", SentimentResult("positive", "good", "price", "m", "1"))
    row = conn.execute("SELECT sentiment, summary, theme, model_version, prompt_version FROM posts WHERE post_id='p1' AND group_id='g1'").fetchone()
    assert tuple(row) == ("positive", "good", "price", "m", "1")
    assert {r["post_id"] for r in pending_sentiment(conn, "g1")} == {"p2"}
    assert {r["post_id"] for r in pending_sentiment(conn, "g2")} == {"p1", "p2"}  # g2 ยัง untouched


def test_save_sentiment_does_not_overwrite(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    save_sentiment(conn, "g1", "p1", SentimentResult("positive", "good", "price", "m", "1"))
    save_sentiment(conn, "g1", "p1", SentimentResult("negative", "bad", "other", "m2", "2"))
    assert conn.execute("SELECT sentiment, model_version FROM posts WHERE post_id='p1'").fetchone() == ("positive", "m")


def test_upsert_posts_preserves_sentiment(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", _posts(), "2026-09-15T00:00:00+00:00")
    save_sentiment(conn, "g1", "p1", SentimentResult("positive", "good", "price", "m", "1"))
    upsert_posts(conn, "g1", _posts(), "2026-09-15T01:00:00+00:00")  # re-fetch
    assert conn.execute("SELECT sentiment FROM posts WHERE post_id='p1'").fetchone()[0] == "positive"


def test_pending_skips_empty_body(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", [
        {"post_id": "p1", "poster_name": "A", "body": "", "created_at": "2026-09-14T10:00:00+00:00",
         "reaction_count": 0, "comment_count": 0, "permalink": "x"},
        {"post_id": "p2", "poster_name": "B", "body": "hello", "created_at": "2026-09-14T10:00:00+00:00",
         "reaction_count": 0, "comment_count": 0, "permalink": "y"},
    ], "2026-09-15T00:00:00+00:00")
    assert [r["post_id"] for r in pending_sentiment(conn, "g1")] == ["p2"]
