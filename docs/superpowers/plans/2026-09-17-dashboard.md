# Dashboard (FastAPI + Next.js) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard ส่วนตัว (localhost, no auth) — Trends, Post list + filter, Post detail — อ่านข้อมูลจาก `data/sl.db` ผ่าน FastAPI เล็กๆ

**Architecture:** `api.py` (FastAPI, port 8000) เปิด SQLite connection ใหม่ต่อ request (read-only, busy → 503) · `dashboard/` (Next.js 15 App Router + TS + Tailwind) client-side fetch API ตรงๆ (CORS 1 บรรทัด) poll ทุก 60 วิ · keyword คำนวณฝั่ง Python (reuse `digest._tokens`) เก็บเป็น JSON column

**Tech Stack:** Python 3.12 (fastapi, uvicorn, httpx) · Next.js 15 + TypeScript + Tailwind · SQLite (db เดิม)

**Spec:** `docs/superpowers/specs/2026-09-17-dashboard-design.md`

**Deviation from spec (documented):** response ของ `/stats` มี field เพิ่ม `"group"` (ชื่อกลุ่มจาก config.toml) — spec §6 ให้แสดง group name ใน UI แต่ §5 ไม่มี endpoint ใดส่งชื่อมา → additive field เท่านั้น shape เดิมไม่เปลี่ยน

## Global Constraints

- Python ทุกตัวรันผ่าน `.venv\Scripts\python` · tests: `.venv\Scripts\python -m pytest` (จาก repo root)
- Windows PowerShell — CRLF warning ตอน commit เป็นปกติ อย่า fix
- Commit style เดิม: fine-grained conventional (เช่น `feat(store): ...`, `feat(api): ...`)
- API port 8000 · Next.js 3000 · db path `data/sl.db` (test override ได้ด้วย env `SL_DB` — set ก่อน `import api`)
- ฝั่ง JS ห้ามเพิ่ม dependency นอกเหนือจากผลลัพธ์ของ `create-next-app`
- Comments ภาษาไทยได้ (convention ของ repo) · คำตอบจาก API = JSON UTF-8

---

### Task 1: `keywords` column ใน store.py

**Files:**
- Modify: `store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `digest._tokens(text: str) -> list[str]` (มีอยู่แล้ว — pythainlp, calibrate แล้ว)
- Produces: column `posts.keywords` (JSON array string) — `upsert_posts` populate อัตโนมัติ · row เก่า = NULL (API ต้องทน NULL)

- [ ] **Step 1: Write the failing test**

`tests/test_store.py` — เพิ่ม `import json` เป็นบรรทัดแรก แล้วเพิ่ม test นี้ต่อท้าย:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_store.py::test_upsert_populates_keywords -v`
Expected: FAIL — `sqlite3.OperationalError: no such column: keywords`

- [ ] **Step 3: Implement**

`store.py` — 4 จุด:

1. imports (หลัง `import sqlite3`):
```python
import json
from digest import _tokens
```
2. `_SCHEMA` — เพิ่มคอลัมน์ก่อนบรรทัด `PRIMARY KEY`:
```sql
    permalink TEXT,
    keywords TEXT,
    PRIMARY KEY (post_id, group_id)
```
3. migration tuple ใน `init_db` — เพิ่มสมาชิก (เก็บ comment ponytail เดิมไว้):
```python
    for col, ddl in (("share_count", "ALTER TABLE posts ADD COLUMN share_count INTEGER DEFAULT 0"),
                     ("keywords", "ALTER TABLE posts ADD COLUMN keywords TEXT"),):  # ponytail: migration ทีละคอลัมน์, ใช้ CREATE ใหม่ถ้า schema เปลี่ยนมาก
        if col not in cols:
            conn.execute(ddl)
            conn.commit()
```
4. `upsert_posts` — เพิ่ม `keywords` ใน 3 ส่วน:
```python
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
            permalink      = excluded.permalink,
            keywords       = excluded.keywords
```
และ tuple ใน list comprehension เพิ่ม element สุดท้าย:
```python
        [
            (p["post_id"], group_id, p["poster_name"], p["body"], p["created_at"],
             fetched_at, p["reaction_count"], p["comment_count"],
             p.get("share_count", 0), p["permalink"],
             json.dumps(sorted(set(_tokens(p["body"] or "")))))
            for p in posts
        ],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests -v`
Expected: 16 passed (15 เดิม + 1 ใหม่)

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat(store): store per-post keywords as JSON (reuse digest tokenizer)"
```

---

### Task 2: `api.py` — /health + /posts

**Files:**
- Create: `api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `store.init_db`, `store.fetch_recent` · env `SL_DB` (default `data/sl.db`) · `config.toml` (`groups[].name` + `url` → default group_id)
- Produces: `api.app` (FastAPI), `api.DB` (Path) · `GET /health`, `GET /posts` (shape spec §5) · task 3 ใช้ต่อ: `_ro()` (contextmanager, 503 "db busy"), `_row_to_post()`, `_group_info()`

- [ ] **Step 1: Install deps**

Run: `.venv\Scripts\python -m pip install fastapi uvicorn httpx`
Expected: Successfully installed (httpx = TestClient ของ FastAPI)

- [ ] **Step 2: Write the failing tests**

สร้าง `tests/test_api.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 4: Implement `api.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: 5 passed

- [ ] **Step 6: Run full suite + commit**

Run: `.venv\Scripts\python -m pytest tests` → Expected: 21 passed

```bash
git add api.py tests/test_api.py
git commit -m "feat(api): health + posts list (FastAPI over SQLite, 503 on db busy)"
```

---

### Task 3: `api.py` — /posts/{id} + /stats

**Files:**
- Modify: `api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `_ro()`, `_row_to_post()`, `_group_info()`, `fetch_recent` จาก task 2
- Produces: `GET /posts/{post_id}` (404 ถ้าไม่มี) · `GET /stats?days=&group_id=` — response = shape spec §5 + field `"group"` (ชื่อกลุ่ม, ดู Deviation ด้านบน)

- [ ] **Step 1: Write the failing tests**

เพิ่มใน `tests/test_api.py` ต่อจาก test เดิม:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: 5 ใหม่ FAIL (404/405 — endpoints ยังไม่มี) · 5 เดิม PASS

- [ ] **Step 3: Implement — เพิ่ม 2 functions ต่อท้าย `api.py`**

```python
@app.get("/posts/{post_id}")
def get_post(post_id: str, group_id: str | None = None):
    _, gid = _group_info(group_id)
    with _ro() as conn:
        r = conn.execute("SELECT * FROM posts WHERE post_id=? AND group_id=?",
                         (post_id, gid)).fetchone()
    if not r:
        raise HTTPException(404, "post not found")
    return _row_to_post(r)


@app.get("/stats")
def stats(days: int = Query(7, ge=1, le=90), group_id: str | None = None):
    name, gid = _group_info(group_id)
    now = datetime.now(timezone.utc)
    with _ro() as conn:
        rows = fetch_recent(conn, gid, (now - timedelta(days=days)).isoformat())
        new24 = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE group_id=? AND"
            " (created_at IS NULL OR created_at >= ?)",
            (gid, (now - timedelta(days=1)).isoformat())).fetchone()[0]
        last = conn.execute("SELECT MAX(fetched_at) FROM posts").fetchone()[0]
    # fetch_recent return list[dict] — r["col"] ได้เลย
    kw: Counter = Counter()
    for r in rows:
        if r["keywords"]:  # NULL (row ก่อน migration) = skip
            kw.update(json.loads(r["keywords"]))
    total = len(rows)
    return {
        "group": name,
        "days": days,
        "total_posts": total,
        "new_since_yesterday": new24,
        "last_fetched": last,
        "top_keywords": [
            {"word": w, "count": c, "pct": c / total} for w, c in kw.most_common(15)
        ],
        "top_posters": [
            {"name": n, "count": c}
            for n, c in Counter(r["poster_name"] or "?" for r in rows).most_common(10)
        ],
        "top_posts": [
            {
                "post_id": r["post_id"],
                "poster_name": r["poster_name"],
                "snippet": " ".join((r["body"] or "").split())[:120],
                "created_at": r["created_at"],
                "engagement": (r["reaction_count"] or 0) + (r["comment_count"] or 0)
                              + (r["share_count"] or 0),
                "permalink": r["permalink"],
            }
            for r in sorted(rows, key=lambda r: (r["reaction_count"] or 0)
                            + (r["comment_count"] or 0) + (r["share_count"] or 0),
                            reverse=True)[:10]
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests -v`
Expected: 26 passed (21 + 5)

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat(api): post detail + stats (keywords/posters/engagement, 24h delta)"
```

---

### Task 4: dashboard scaffold + lib + Trends page

**Files:**
- Create: `dashboard/` (entire — จาก create-next-app), `dashboard/lib/api.ts`, `dashboard/lib/usePoll.ts`, `dashboard/components/Trends.tsx`
- Modify: `dashboard/app/layout.tsx`, `dashboard/app/page.tsx` (แทนที่ของ scaffold)

**Interfaces:**
- Consumes: API จาก task 2-3 (http://localhost:8000)
- Produces: `usePoll<T>(url, ms)` → `{data, error, stale}` (signature ตาม spec §6) · types `Post`/`Stats`/`PostsResponse` + `API` base · layout + nav ให้ task 5 ใช้

- [ ] **Step 1: Scaffold**

Run (workdir = repo root): `npx --yes create-next-app@latest dashboard --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm --yes`
Expected: สร้าง `dashboard/` (Next 15, TS, Tailwind, App Router) · scaffold เขียน `dashboard/.gitignore` (มี node_modules) มาให้อัตโนมัติ — `git status` ต้องไม่เห็น node_modules

- [ ] **Step 2: Write `dashboard/lib/api.ts`**

```ts
export const API = process.env.API_URL ?? "http://localhost:8000";

export type Post = {
  post_id: string;
  group_id: string;
  poster_name: string | null;
  body: string | null;
  created_at: string | null;
  fetched_at: string;
  reaction_count: number;
  comment_count: number;
  share_count: number;
  permalink: string | null;
  keywords: string[];
};

export type Stats = {
  group: string;
  days: number;
  total_posts: number;
  new_since_yesterday: number;
  last_fetched: string | null;
  top_keywords: { word: string; count: number; pct: number }[];
  top_posters: { name: string; count: number }[];
  top_posts: {
    post_id: string;
    poster_name: string | null;
    snippet: string;
    created_at: string | null;
    engagement: number;
    permalink: string | null;
  }[];
};

export type PostsResponse = { total: number; posts: Post[] };
```

- [ ] **Step 3: Write `dashboard/lib/usePoll.ts`**

```ts
"use client";
import { useEffect, useState } from "react";
import { API } from "./api";

// url เปลี่ยน (filter ใหม่) = poll ใหม่ · stale = มีข้อมูลเก่าแต่ fetch ล่าสุดพัง
// (ข้อมูลเดิมยัง render อยู่ — spec §6)
export function usePoll<T>(url: string, ms = 60_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let on = true;
    const load = () =>
      fetch(`${API}${url}`, { cache: "no-store" })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<T>;
        })
        .then((d) => {
          if (on) {
            setData(d);
            setError(null);
          }
        })
        .catch((e) => {
          if (on) setError(String(e));
        });
    load();
    const t = setInterval(load, ms);
    return () => {
      on = false;
      clearInterval(t);
    };
  }, [url, ms]);

  return { data, error, stale: data !== null && error !== null };
}
```

- [ ] **Step 4: Replace `dashboard/app/layout.tsx`**

```tsx
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata = { title: "Social Listening" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th">
      <body className="min-h-screen bg-white text-neutral-900 antialiased">
        <nav className="flex items-center gap-4 border-b px-6 py-3">
          <span className="mr-4 font-bold">Social Listening</span>
          <Link href="/" className="text-blue-700">Trends</Link>
          <Link href="/posts" className="text-blue-700">Posts</Link>
        </nav>
        <main className="mx-auto max-w-4xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
```

(กลุ่มชื่อแสดงที่ header ของแต่ละหน้า — มาจาก `/stats.group`)

- [ ] **Step 5: Write `dashboard/components/Trends.tsx`**

```tsx
"use client";
import Link from "next/link";
import { type Stats } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function Trends() {
  const { data, error } = usePoll<Stats>("/stats?days=7");

  if (!data) {
    return (
      <div className="rounded bg-red-50 p-3 text-sm text-red-700">
        เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
        <code>python -m uvicorn api:app --port 8000</code>
      </div>
    );
  }
  const max = data.top_keywords[0]?.count ?? 1;
  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded bg-yellow-50 p-2 text-sm text-yellow-800">
          {error.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">
          {data.group} — 7 วันล่าสุด
        </h1>
        <span className="text-sm text-neutral-500">
          {data.new_since_yesterday} โพสต์ใหม่ 24 ชม. · {data.total_posts} posts ·
          ล่าสุด {data.last_fetched?.slice(0, 16)}
        </span>
      </header>
      <section>
        <h2 className="mb-2 text-lg font-semibold">Top keywords</h2>
        {data.top_keywords.length === 0 && (
          <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
        )}
        {data.top_keywords.map((k) => (
          <div key={k.word} className="mb-1 flex items-center gap-2">
            <span className="w-40 truncate">{k.word}</span>
            <div className="h-4 flex-1 rounded bg-neutral-100">
              <div
                className="h-full rounded bg-blue-600"
                style={{ width: `${(k.count / max) * 100}%` }}
              />
            </div>
            <span className="w-20 text-right text-sm">
              {k.count} · {(k.pct * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </section>
      <section className="grid grid-cols-1 gap-8 sm:grid-cols-2">
        <div>
          <h2 className="mb-2 text-lg font-semibold">Top posters</h2>
          {data.top_posters.length === 0 && (
            <p className="text-sm text-neutral-500">ยังไม่มีโพสต์ใน range นี้</p>
          )}
          <ol className="list-decimal pl-5">
            {data.top_posters.map((p) => (
              <li key={p.name}>
                {p.name} — {p.count}
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h2 className="mb-2 text-lg font-semibold">Top posts by engagement</h2>
          <ul className="space-y-3">
            {data.top_posts.map((p) => (
              <li key={p.post_id}>
                <Link
                  href={`/posts/${p.post_id}`}
                  className="text-sm text-blue-700 hover:underline"
                >
                  [{p.engagement}] {p.created_at ?? "—"} — {p.poster_name}
                </Link>
                <p className="text-sm text-neutral-600">{p.snippet}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 6: Replace `dashboard/app/page.tsx`**

```tsx
import Trends from "@/components/Trends";

export default function Home() {
  return <Trends />;
}
```

- [ ] **Step 7: Verify build**

Run (workdir = repo root): `cd dashboard; npm run build`
Expected: build สำเร็จ (type check + lint ผ่าน)

- [ ] **Step 8: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): scaffold Next.js + trends page (keyword/poster bars, 24h delta)"
```

---

### Task 5: Posts list + Detail

**Files:**
- Create: `dashboard/components/PostList.tsx`, `dashboard/components/PostDetail.tsx`, `dashboard/app/posts/page.tsx`, `dashboard/app/posts/[id]/page.tsx`

**Interfaces:**
- Consumes: `usePoll`, types จาก task 4
- Produces: pages `/posts` (filter bar + ตาราง + pagination) และ `/posts/[id]` (full text)

- [ ] **Step 1: Write `dashboard/components/PostList.tsx`**

```tsx
"use client";
import Link from "next/link";
import { useState } from "react";
import { type PostsResponse } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const LIMIT = 50;

export default function PostList() {
  const [q, setQ] = useState("");
  const [poster, setPoster] = useState("");
  const [sort, setSort] = useState<"date" | "engagement">("date");
  const [page, setPage] = useState(0);

  const qs = new URLSearchParams({
    sort,
    limit: String(LIMIT),
    offset: String(page * LIMIT),
  });
  if (q) qs.set("q", q);
  if (poster) qs.set("poster", poster);
  const { data, error } = usePoll<PostsResponse>(`/posts?${qs}`);

  const posts = data?.posts ?? [];
  const eng = (p: { reaction_count: number; comment_count: number; share_count: number }) =>
    p.reaction_count + p.comment_count + p.share_count;

  return (
    <div className="space-y-4">
      {error && !data && (
        <div className="rounded bg-red-50 p-3 text-sm text-red-700">
          เชื่อมต่อ API ไม่ได้ ({error}) — รัน{" "}
          <code>python -m uvicorn api:app --port 8000</code>
        </div>
      )}
      {error && data && (
        <div className="rounded bg-yellow-50 p-2 text-sm text-yellow-800">
          {error.includes("503")
            ? "DB occupied — กำลัง retry ทุก 60 วิ"
            : "refresh พัง — แสดงข้อมูลล่าสุด"}
        </div>
      )}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(0);
        }}
      >
        <input
          className="rounded border px-2 py-1 text-sm"
          placeholder="ค้นหาในข้อความ…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <input
          className="rounded border px-2 py-1 text-sm"
          placeholder="poster"
          value={poster}
          onChange={(e) => setPoster(e.target.value)}
        />
        <select
          className="rounded border px-2 py-1 text-sm"
          value={sort}
          onChange={(e) => setSort(e.target.value as "date" | "engagement")}
        >
          <option value="date">ล่าสุดก่อน</option>
          <option value="engagement">engagement สูงสุด</option>
        </select>
        <button className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
          ค้นหา
        </button>
        <span className="text-sm text-neutral-500">{data?.total ?? 0} posts</span>
      </form>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-neutral-500">
            <th className="py-1 pr-2">เวลา</th>
            <th className="py-1 pr-2">poster</th>
            <th className="py-1 pr-2">ข้อความ</th>
            <th className="py-1 pr-2 text-right">R/C/S</th>
            <th className="py-1 pr-2 text-right">engagement</th>
            <th className="py-1" />
          </tr>
        </thead>
        <tbody>
          {posts.map((p) => (
            <tr key={p.post_id} className="border-b align-top">
              <td className="whitespace-nowrap py-2 pr-2 text-neutral-500">
                {(p.created_at ?? "—").slice(0, 16)}
              </td>
              <td className="whitespace-nowrap py-2 pr-2">{p.poster_name ?? "—"}</td>
              <td className="py-2 pr-2">{(p.body ?? "").slice(0, 120)}</td>
              <td className="whitespace-nowrap py-2 pr-2 text-right text-neutral-500">
                {p.reaction_count}/{p.comment_count}/{p.share_count}
              </td>
              <td className="py-2 pr-2 text-right">{eng(p)}</td>
              <td className="py-2 text-right">
                <Link href={`/posts/${p.post_id}`} className="text-blue-700 hover:underline">
                  เปิด
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data && posts.length === 0 && (
        <p className="text-sm text-neutral-500">ไม่พบโพสต์</p>
      )}
      <div className="flex gap-2 text-sm">
        <button
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          className="rounded border px-3 py-1 disabled:opacity-40"
        >
          ก่อนหน้า
        </button>
        <button
          disabled={posts.length < LIMIT}
          onClick={() => setPage((p) => p + 1)}
          className="rounded border px-3 py-1 disabled:opacity-40"
        >
          ถัดไป
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `dashboard/components/PostDetail.tsx`**

```tsx
"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type Post } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function PostDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = usePoll<Post>(`/posts/${encodeURIComponent(id)}`);

  if (!data) {
    return (
      <p className="text-sm text-neutral-500">
        {error ? `ไม่พบโพสต์ (${error})` : "กำลังโหลด…"}
      </p>
    );
  }
  const eng = data.reaction_count + data.comment_count + data.share_count;
  return (
    <article className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-xl font-bold">{data.poster_name ?? "ไม่ทราบชื่อ"}</h1>
        <p className="text-sm text-neutral-500">
          {data.created_at ?? "—"} · engagement {eng} (R {data.reaction_count} / C{" "}
          {data.comment_count} / S {data.share_count})
        </p>
      </header>
      <p className="whitespace-pre-wrap leading-relaxed">
        {data.body ?? "(ไม่มีข้อความ)"}
      </p>
      {data.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {data.keywords.map((k) => (
            <span key={k} className="rounded bg-neutral-100 px-2 py-0.5 text-xs">
              {k}
            </span>
          ))}
        </div>
      )}
      {data.permalink && (
        <a
          className="inline-block text-blue-700 hover:underline"
          href={data.permalink}
          target="_blank"
          rel="noreferrer"
        >
          เปิดใน Facebook ↗
        </a>
      )}
      <Link href="/posts" className="block text-sm text-neutral-500">
        ← กลับไป list
      </Link>
    </article>
  );
}
```

- [ ] **Step 3: Write pages**

`dashboard/app/posts/page.tsx`:
```tsx
import PostList from "@/components/PostList";

export default function PostsPage() {
  return <PostList />;
}
```

`dashboard/app/posts/[id]/page.tsx`:
```tsx
import PostDetail from "@/components/PostDetail";

export default function PostPage() {
  return <PostDetail />;
}
```

- [ ] **Step 4: Verify build**

Run (workdir = repo root): `cd dashboard; npm run build`
Expected: build สำเร็จ · route `/posts` + `/posts/[id]` ปรากฏใน output

- [ ] **Step 5: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): posts list (search/filter/sort/pagination) + detail page"
```

---

### Task 6: e2e verify + README

**Files:**
- Modify: `README.md`
- (task นี้ verify + docs — ไม่สร้างไฟล์ใหม่)

**Interfaces:**
- Consumes: ทุกอย่างจาก task 1-5 + `cli.py monitor --once` + browser

- [ ] **Step 1: Refresh keywords ใน DB จริง**

Run: `.venv\Scripts\python cli.py monitor --once`
Expected: `fetched N posts` — posts ที่ fetch ใหม่ได้ keywords (post ที่ไม่ซ้ำในรอบนี้ keywords ยัง NULL = ปกติ, API ทน)

- [ ] **Step 2: Run API (background)**

Run (background: true, workdir = repo root): `.venv\Scripts\python -m uvicorn api:app --port 8000`
Expected: `Uvicorn running on http://127.0.0.1:8000` · browser ไป `http://localhost:8000/health` → `{"ok":true,...}`

- [ ] **Step 3: Run Next.js dev (background)**

Run (background: true, workdir = repo root): `cd dashboard; npm run dev`
Expected: `Ready on http://localhost:3000`

- [ ] **Step 4: Verify ใน browser (chrome-devtools)**

1. `http://localhost:3000/` — header มีชื่อกลุ่ม "กลุ่มเป้าหมาย" · top keywords bars มีค่า · top posters · top posts · badge "N โพสต์ใหม่ 24 ชม." + "ล่าสุด HH:MM" · ไม่ blank ไม่ error
2. `http://localhost:3000/posts` — ตารางมี rows · พิมพ์ keyword ที่เห็นใน posts ลงช่องค้น → rows เหลือเฉพาะที่ match · เปลี่ยน sort = engagement → row แรกเปลี่ยน · pagination ปุ่มกดได้ถ้า rows ≥ 50
3. คลิก "เปิด" row ใด row หนึ่ง → `/posts/[id]` — full text + keyword chips + "เปิดใน Facebook ↗" (href = permalink ใน db)
4. console ไม่มี error (list_console_messages)
5. (error path) stop uvicorn → refresh `/` → banner "เชื่อมต่อ API ไม่ได้" แล้ว start uvicorn ใหม่ → ข้อมูลกลับมา

- [ ] **Step 5: README**

เพิ่มใน `README.md` หลัง section `## Usage`:

```markdown
## Dashboard (UI)

ต้องมี data ใน `data/sl.db` (รัน `monitor` แล้ว) — terminal 2 ตัว:

    .venv\Scripts\python -m uvicorn api:app --port 8000
    cd dashboard; npm run dev        # → http://localhost:3000
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: dashboard run instructions"
```

(ถ้า step 4 พบ bug → แก้ + commit แยก `fix(...)` ก่อน แล้ว verify ใหม่)
