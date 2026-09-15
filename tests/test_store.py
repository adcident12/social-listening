from store import fetch_recent, init_db, upsert_posts

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
