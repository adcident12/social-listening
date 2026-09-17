from __future__ import annotations

import json
import os
import re
import sqlite3
import tomllib
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from store import fetch_recent, init_db

# ponytail: SL_DB env สำหรับ test — default คือ db ของระบบ
DB = Path(os.environ.get("SL_DB", "data/sl.db"))
init_db(DB)  # สร้างตารางถ้ายังไม่มี (ตอน import) — DB ว่าง = zero state ไม่ใช่ 500

app = FastAPI(title="social-listening")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _gid_from_url(url: str) -> str:
    # pattern เดียวกับ fetch.group_id_from_url — ไม่ import fetch เพราะลาก playwright มาด้วย
    m = re.search(r"/groups/([0-9A-Za-z._-]+)", url)
    if not m:
        raise HTTPException(500, f"no group id in config url: {url}")
    return m.group(1)


def _group_info(gid: str | None) -> tuple[str, str]:
    """(name, group_id) จาก config.toml — ไม่ส่ง gid = groups[0] · gid อื่นที่ไม่ได้อยู่ใน config ใช้ตามนั้น (schema รองรับ)"""
    with open("config.toml", "rb") as f:
        groups = tomllib.load(f)["groups"]
    if gid is None:
        g = groups[0]
        return g.get("name", "group"), _gid_from_url(g["url"])
    for g in groups:
        if _gid_from_url(g["url"]) == gid:
            return g.get("name", gid), gid
    return "group", gid


@contextmanager
def _ro():
    # connection ใหม่ต่อ request (กัน cross-thread) · timeout=5 → DB busy = 503 (spec §7)
    conn = None
    try:
        conn = sqlite3.connect(str(DB), timeout=5)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.OperationalError as e:
        raise HTTPException(503, "db busy") from e
    finally:
        if conn:
            conn.close()


def _row_to_post(r) -> dict:
    return {
        "post_id": r["post_id"],
        "group_id": r["group_id"],
        "poster_name": r["poster_name"],
        "body": r["body"],
        "created_at": r["created_at"],
        "fetched_at": r["fetched_at"],
        "reaction_count": r["reaction_count"] or 0,
        "comment_count": r["comment_count"] or 0,
        "share_count": r["share_count"] or 0,
        "permalink": r["permalink"],
        "keywords": json.loads(r["keywords"]) if r["keywords"] else [],
    }


@app.get("/health")
def health():
    with _ro() as conn:
        row = conn.execute("SELECT MAX(fetched_at) FROM posts").fetchone()
    return {"ok": True, "last_fetched": row[0]}


@app.get("/posts")
def list_posts(
    q: str | None = None,
    poster: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort: str = Query("date", pattern="^(date|engagement)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    group_id: str | None = None,
):
    _, gid = _group_info(group_id)
    where, params = ["group_id = ?"], [gid]
    if q:
        where.append("body LIKE ?")
        params.append(f"%{q}%")
    if poster:
        where.append("poster_name LIKE ?")
        params.append(f"%{poster}%")
    if since:
        where.append("(created_at IS NULL OR created_at >= ?)")
        params.append(since)
    if until:
        where.append("(created_at IS NULL OR created_at <= ?)")
        params.append(until)
    if sort == "engagement":
        order = ("(COALESCE(reaction_count,0)+COALESCE(comment_count,0)"
                 "+COALESCE(share_count,0)) DESC, created_at DESC")
    else:
        order = "created_at DESC"
    where_sql = " AND ".join(where)
    with _ro() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM posts WHERE {where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM posts WHERE {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
    return {"total": total, "posts": [_row_to_post(r) for r in rows]}
