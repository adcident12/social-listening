from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from digest import _tokens

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
    share_count INTEGER DEFAULT 0,
    permalink TEXT,
    keywords TEXT,
    sentiment TEXT,
    summary TEXT,
    theme TEXT,
    model_version TEXT,
    prompt_version TEXT,
    PRIMARY KEY (post_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_group_time ON posts (group_id, created_at);
CREATE TABLE IF NOT EXISTS comments (
    comment_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    poster_name TEXT,
    body TEXT,
    created_at TEXT,
    reaction_count INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (comment_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments (post_id, group_id);
CREATE TABLE IF NOT EXISTS alerts (
    post_id TEXT NOT NULL,
    rule TEXT NOT NULL,
    fired_at TEXT NOT NULL,
    group_id TEXT,
    UNIQUE (post_id, rule)
);
"""

def init_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    acols = {c[1] for c in conn.execute("PRAGMA table_info(alerts)")}
    if "group_id" not in acols:
        conn.execute("ALTER TABLE alerts ADD COLUMN group_id TEXT")
        conn.commit()
    cols = {c[1] for c in conn.execute("PRAGMA table_info(posts)")}
    # ponytail: migration ทีละคอลัมน์, ใช้ CREATE ใหม่ถ้า schema เปลี่ยนมาก
    for col, ddl in (("share_count", "ALTER TABLE posts ADD COLUMN share_count INTEGER DEFAULT 0"),
                     ("keywords", "ALTER TABLE posts ADD COLUMN keywords TEXT"),
                     ("sentiment", "ALTER TABLE posts ADD COLUMN sentiment TEXT"),
                     ("summary", "ALTER TABLE posts ADD COLUMN summary TEXT"),
                     ("theme", "ALTER TABLE posts ADD COLUMN theme TEXT"),
                     ("model_version", "ALTER TABLE posts ADD COLUMN model_version TEXT"),
                     ("prompt_version", "ALTER TABLE posts ADD COLUMN prompt_version TEXT"),):
        if col not in cols:
            conn.execute(ddl)
            conn.commit()
    return conn

def upsert_posts(conn: sqlite3.Connection, group_id: str,
                 posts: list[dict], fetched_at: str) -> int:
    conn.executemany(
        """
        INSERT INTO posts (post_id, group_id, poster_name, body, created_at,
                           fetched_at, reaction_count, comment_count, share_count, permalink, keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(post_id, group_id) DO UPDATE SET
            poster_name = excluded.poster_name,
            body        = excluded.body,
            created_at  = excluded.created_at,
            fetched_at  = excluded.fetched_at,
            reaction_count = excluded.reaction_count,
            comment_count  = excluded.comment_count,
            share_count    = excluded.share_count,
            permalink     = excluded.permalink,
            keywords      = excluded.keywords
        """,
        [
            (p["post_id"], group_id, p["poster_name"], p["body"], p["created_at"],
             fetched_at, p["reaction_count"], p["comment_count"],
             p.get("share_count", 0), p["permalink"],
             json.dumps(sorted(set(_tokens(p["body"] or "")))))
            for p in posts
        ],
    )
    conn.commit()
    return len(posts)

def upsert_comments(conn: sqlite3.Connection, group_id: str,
                    posts: list[dict], fetched_at: str) -> int:
    """flattens p["comments"] → comments · comment_id = hash(post_id+poster+body) (DOM id ไม่ garant)"""
    rows = []
    for p in posts:
        for c in p.get("comments") or []:
            cid = hashlib.sha1(f'{p["post_id"]}|{c.get("poster_name") or ""}|{c.get("body") or ""}'.encode("utf-8")).hexdigest()[:16]
            rows.append((cid, p["post_id"], group_id, c.get("poster_name"), c.get("body"),
                         c.get("created_at"), c.get("reaction_count", 0), fetched_at))
    conn.executemany(
        """
        INSERT INTO comments (comment_id, post_id, group_id, poster_name, body,
                              created_at, reaction_count, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(comment_id, group_id) DO UPDATE SET
            poster_name    = excluded.poster_name,
            body           = excluded.body,
            created_at     = excluded.created_at,
            reaction_count = excluded.reaction_count,
            fetched_at     = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)

def pending_sentiment(conn: sqlite3.Connection, group_id: str) -> list[dict]:
    """posts ยังไม่มี sentiment และ body ไม่ใช่ว่าง — วิเคราะห์ทีละโพสต์ ครั้งเดียว (idempotent)"""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT post_id, body FROM posts
        WHERE group_id = ? AND sentiment IS NULL AND body IS NOT NULL AND body != ''
        """,
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def save_sentiment(conn: sqlite3.Connection, group_id: str, post_id: str,
                   result) -> None:
    """guard sentiment IS NULL — กัน overwrite ตัวที่คำนวณแล้ว (re-run/parallel-safe)"""
    conn.execute(
        """
        UPDATE posts SET sentiment = ?, summary = ?, theme = ?,
               model_version = ?, prompt_version = ?
        WHERE post_id = ? AND group_id = ? AND sentiment IS NULL
        """,
        (result.label, result.summary, result.theme,
         result.model_version, result.prompt_version, post_id, group_id),
    )
    conn.commit()

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
