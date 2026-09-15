from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    poster_name TEXT,
    body TEXT,
    created_at TEXT,
    fetched_at TEXT NOT NULL,
    reaction_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    permalink TEXT,
    PRIMARY KEY (post_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_group_time ON posts (group_id, created_at);
"""

def init_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    return conn

def upsert_posts(conn: sqlite3.Connection, group_id: str,
                 posts: list[dict], fetched_at: str) -> int:
    conn.executemany(
        """
        INSERT INTO posts (post_id, group_id, poster_name, body, created_at,
                           fetched_at, reaction_count, comment_count, permalink)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(post_id, group_id) DO UPDATE SET
            poster_name = excluded.poster_name,
            body        = excluded.body,
            created_at  = excluded.created_at,
            fetched_at  = excluded.fetched_at,
            reaction_count = excluded.reaction_count,
            comment_count  = excluded.comment_count,
            permalink     = excluded.permalink
        """,
        [
            (p["post_id"], group_id, p["poster_name"], p["body"], p["created_at"],
             fetched_at, p["reaction_count"], p["comment_count"], p["permalink"])
            for p in posts
        ],
    )
    conn.commit()
    return len(posts)

def fetch_recent(conn: sqlite3.Connection, group_id: str, since_iso: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM posts
        WHERE group_id = ? AND (created_at IS NULL OR created_at >= ?)
        ORDER BY created_at DESC
        """,
        (group_id, since_iso),
    ).fetchall()
    return [dict(r) for r in rows]
