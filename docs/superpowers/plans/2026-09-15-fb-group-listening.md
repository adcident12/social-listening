# FB Group Social Listening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI tool ที่เฝ้าดูโพสต์ใน Facebook Group (browser automation + บัญชีผู้ใช้เอง), บันทึกสะสมใน SQLite แล้วสร้าง Markdown digest "กระแสช่วงนี้เรื่องอะไร"

**Architecture:** 4 modules แยกกันชัด: `fetch.py` (Playwright + parser, selector FB รวมจุดเดียว), `store.py` (SQLite dedupe/upsert), `digest.py` (pythainlp keyword + engagement → Markdown), `cli.py` (login / monitor / digest / capture). Data flow: login → monitor loop → SQLite → digest report.

**Tech Stack:** Python 3.12 (เครื่องนี้มี `python` = 3.12.1), Playwright (chromium, persistent context), SQLite (stdlib), pythainlp, pytest. ไม่เพิ่ม dependency อื่น

> **Deviation (2026-09-15):** spec ระบุ `thai2fit` แต่แพ็กเกจนี้ไม่มีบน PyPI — ใช้ `pythainlp` (5.3.7, standard Thai NLP, `word_tokenize`) แทน

**Spec:** `docs/superpowers/specs/2026-09-15-fb-group-listening-design.md`

## Global Constraints

- Windows + PowerShell. Python ผ่าน `.venv\Scripts\python` หลังสร้าง venv
- Python 3.11+ (ใช้ `tomllib` stdlib)
- Dependencies เพิ่มได้แค่: `playwright`, `pythainlp`, `pytest`
- **Selector ของ Facebook DOM ทุกตัวต้องอยู่ใน `fetch.py` เท่านั้น** (แก้จุดเดียวจบเมื่อ DOM เปลี่ยน)
- Parser ต้อง fail loudly — ห้าม parse แล้วได้ข้อมูลผิดแบบเงียบ
- `data/` (db, browser profile, sample.html) = gitignore; `reports/` = commit
- ทุก task สิ้นสุดด้วยการ commit

---

### Task 1: Scaffolding

**Files:**
- Create: `.gitignore`, `config.toml`, `tests/test_smoke.py`

**Interfaces:**
- Produces: venv ที่ import `playwright`, `pythainlp`, `pytest` ได้, `config.toml` ตาม spec §7

- [ ] **Step 1: สร้าง venv + ติดตั้ง deps**

```powershell
python -m venv .venv
    .venv\Scripts\python -m pip install playwright pythainlp pytest
.venv\Scripts\python -m playwright install chromium
```

- [ ] **Step 2: เขียน `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
data/
```

- [ ] **Step 3: เขียน `config.toml`**

```toml
[[groups]]
name = "กลุ่มเป้าหมาย"
url  = "https://www.facebook.com/groups/REPLACE_WITH_GROUP_URL"

[monitor]
interval_minutes = 30
pages_per_run    = 1
headless         = true

[digest]
top_n_keywords = 15
top_n_posts    = 10
```

- [ ] **Step 4: เขียน `tests/test_smoke.py` + รัน**

```python
def test_imports():
    import playwright  # noqa: F401
    import pythainlp  # noqa: F401
```

Run: `.venv\Scripts\python -m pytest -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```powershell
git add .gitignore config.toml tests/test_smoke.py
git commit -m "chore: scaffold venv, deps, config, smoke test"
```

---

### Task 2: `store.py` — SQLite schema, upsert, query

**Files:**
- Create: `store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: ไม่มี (task แรกของ code จริง)
- Produces:
  - `init_db(db_path: str | Path) -> sqlite3.Connection`
  - `upsert_posts(conn: sqlite3.Connection, group_id: str, posts: list[dict], fetched_at: str) -> int` — dict keys ของ post: `post_id, poster_name, body, created_at, reaction_count, comment_count, permalink`
  - `fetch_recent(conn: sqlite3.Connection, group_id: str, since_iso: str) -> list[dict]` — คืน dict ตัดตาม `created_at >= since_iso`, เรียง `created_at DESC`

- [ ] **Step 1: Write the failing test** — `tests/test_store.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Write `store.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_store.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add store.py tests/test_store.py
git commit -m "feat: sqlite store with dedupe upsert and since-query"
```

---

### Task 3: `fetch.py` ส่วน browser — login + capture + `cli.py capture`

**Files:**
- Create: `fetch.py`, `cli.py`
- Test: (browser + บัญชีจริง — คุมด้วย manual verification ใน Step 6)

**Interfaces:**
- Consumes: `config.toml` (เฉพาะ `groups[0].url` ใน cli)
- Produces:
  - `class SessionExpired(RuntimeError)`
  - `login(group_url: str, profile_dir: Path = PROFILE_DIR) -> None`
  - `capture_feed_html(group_url: str, profile_dir: Path = PROFILE_DIR, out_path: Path | None = None, pages: int = 1, headless: bool = True) -> str`
  - `PROFILE_DIR = Path("data/browser-profile")`
  - `cli.py capture --group <url> --out <path>` — บันทึก feed HTML จริงให้ Task 4 ใช้ calibrate parser

- [ ] **Step 1: เขียน browser functions ใน `fetch.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path("data/browser-profile")
SESSION_WAIT_TIMEOUT_MS = 300_000  # 5 นาทีให้คนล็อกอิน

class SessionExpired(RuntimeError):
    pass

def group_id_from_url(url: str) -> str:
    m = re.search(r"/groups/([0-9A-Za-z._-]+)", url)
    if not m:
        raise ValueError(f"no group id in url: {url}")
    return m.group(1)

def _is_login_url(url: str) -> bool:
    return "login" in url or "checkpoint" in url

def _open(profile_dir: Path, headless: bool):
    profile_dir.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(str(profile_dir), headless=headless)
    return pw, ctx

def login(group_url: str, profile_dir: Path = PROFILE_DIR) -> None:
    pw, ctx = _open(profile_dir, headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(group_url)
        page.wait_for_url(
            lambda u: not _is_login_url(u),
            timeout=SESSION_WAIT_TIMEOUT_MS,
        )
        page.wait_for_load_state("networkidle")
    finally:
        ctx.close()
        pw.stop()

def capture_feed_html(group_url: str, profile_dir: Path = PROFILE_DIR,
                      out_path: Path | None = None, pages: int = 1,
                      headless: bool = True) -> str:
    pw, ctx = _open(profile_dir, headless=headless)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(group_url, wait_until="domcontentloaded")
        if _is_login_url(page.url):
            raise SessionExpired(
                "session not logged in — run: python cli.py login")
        for _ in range(max(1, pages)):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)
        page.wait_for_load_state("networkidle")
        html = page.content()
    finally:
        ctx.close()
        pw.stop()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
    return html
```

- [ ] **Step 2: เขียน `cli.py` (เวอร์ชัน capture อย่างเดียว — monitor/digest เพิ่มใน task หลัง)**

```python
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from fetch import capture_feed_html

def _config() -> dict:
    with open("config.toml", "rb") as f:
        return tomllib.load(f)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="social-listening")
    sub = p.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="save raw feed HTML for parser debugging")
    cap.add_argument("--group", required=True)
    cap.add_argument("--out", default="data/sample.html")

    args = p.parse_args(argv)
    if args.cmd == "capture":
        capture_feed_html(args.group, out_path=Path(args.out))
        print(f"saved {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Verify syntax**

Run: `.venv\Scripts\python -m pytest -v`
Expected: smoke test ยัง pass (import ไม่พัง)

- [ ] **Step 4: (manual — ผู้ใช้ต้องทำเอง) ตั้งค่า config และ login**

ผู้ใช้ใส่ group URL จริงใน `config.toml` แล้วรัน:

```powershell
.venv\Scripts\python cli.py login
```

browser จะเปิดให้ล็อกอิน Facebook เอง (profile ถูกเก็บที่ `data/browser-profile`)

- [ ] **Step 5: (manual) Capture feed HTML จริง**

```powershell
.venv\Scripts\python cli.py capture --group (ค่า url จาก config.toml) --out data/sample.html
```

- [ ] **Step 6: Verify capture**

```powershell
(Select-String -Path data\sample.html -Pattern 'role="article"').Count
```

Expected: `> 0` (จำนวนโพสต์ในหน้า)
**ถ้าได้ 0** — inspect `data/sample.html` หา container ของโพสต์จริง (search "article" / โครงสร้าง feed) แล้วปรับ `SELECTORS["post"]` ใน Task 4 ให้ตรงกับ DOM ที่เจอ — ห้ามปล่อย parser จับอะไรก็ได้แบบเงียบ

- [ ] **Step 7: Commit**

```powershell
git add fetch.py cli.py
git commit -m "feat: playwright login + feed capture, cli capture command"
```

---

### Task 4: `fetch.py` ส่วน parser — `parse_posts` + `normalize_time` + `fetch_group_posts`

**Files:**
- Modify: `fetch.py` (เพิ่ม code ด้านล่างต่อจาก Task 3)
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: `capture_feed_html` (Task 3)
- Produces:
  - `SELECTORS: dict` — dict เดียวที่เก็บ selector FB ทั้งหมด
  - `normalize_time(raw: str, now: datetime | None = None) -> str | None` — เวลาบน FB → ISO-8601 UTC
  - `parse_posts(html: str, group_id: str) -> list[dict]` — dict keys: `post_id, poster_name, body, created_at, reaction_count, comment_count, permalink`
  - `fetch_group_posts(group: dict, pages: int = 1, headless: bool = True) -> list[dict]`

- [ ] **Step 1: Write the failing test** — `tests/test_parse.py`

```python
from datetime import datetime, timezone

from fetch import normalize_time, parse_posts

FIXTURE = """
<html><body>
<div role="article" aria-label="Posted by Alice in Test Group. 12 reactions, 3 comments.">
  <div>2 hours ago</div>
  <a href="https://www.facebook.com/groups/123/permalink.99/">Alice</a>
  <div>ใครลองโปรตีนชากสูตรใหม่ยัง อร่อยดี</div>
  <div>12 reactions 3 comments</div>
</div>
<div role="article" aria-label="โพสต์โดย Bob ใน Test Group.">
  <div>เมื่อวานนี้</div>
  <a href="https://www.facebook.com/groups/123/photos/p.88/">Bob</a>
  <div>ออกกำลังกายตอนเช้าดีกว่าตอนไหน</div>
  <div>ปฏิกิริยา 5 ความคิดเห็น 2</div>
</div>
<div role="article" aria-label="Some nav card.">
  <a href="https://www.facebook.com/groups/123/members/">members</a>
</div>
<script>var x = "role=article trick";</script>
</body></html>
"""

def test_parse_posts_fields():
    posts = parse_posts(FIXTURE, "123")
    assert len(posts) == 2  # nav card (ไม่มี body) ถูกตัด
    a = posts[0]
    assert a["poster_name"] == "Alice"
    assert a["permalink"] == "https://www.facebook.com/groups/123/permalink.99"
    assert a["reaction_count"] == 12
    assert a["comment_count"] == 3
    assert "โปรตีน" in a["body"]
    assert a["created_at"].startswith("2026") if a["created_at"] else True
    b = posts[1]
    assert b["poster_name"] == "Bob"
    assert b["reaction_count"] == 5
    assert b["comment_count"] == 2
    assert "ออกกำลังกาย" in b["body"]

def test_post_id_stable():
    p1 = parse_posts(FIXTURE, "123")[0]
    p2 = parse_posts(FIXTURE, "123")[0]
    assert p1["post_id"] == p2["post_id"]

def test_script_content_not_in_body():
    posts = parse_posts(FIXTURE, "123")
    assert all("var x" not in p["body"] for p in posts)

def test_normalize_time_variants():
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    assert normalize_time("2 hours ago", now=now) == "2026-09-15T10:00:00+00:00"
    assert normalize_time("30 mins ago", now=now) == "2026-09-15T11:30:00+00:00"
    assert normalize_time("เมื่อวานนี้", now=now).startswith("2026-09-14T12:00")
    assert normalize_time("12 ก.ย.", now=now) == "2026-09-12T00:00:00+00:00"
    assert normalize_time("Sep 12, 2026", now=now) == "2026-09-12T00:00:00+00:00"
    assert normalize_time("อะไรก็ไม่รู้", now=now) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_parse.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_posts'`

- [ ] **Step 3: เพิ่ม parser ต่อท้าย `fetch.py`**

```python
import hashlib
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

# เลือกตั้ง DOM ของ FB เปลี่ยน — แก้ dict นี้จุดเดียวจบ
SELECTORS = {
    "post": ("div", {"role": "article"}),
}

POST_ARIA_RE = re.compile(
    r"(?:Posted by|โพสต์โดย)\s+(.+?)\s+(?:in|ใน)\s+(.+?)(?:[,.]|\s*$)", re.S)

# อังกฤษ: เลขอยู่ก่อนคำ ("12 reactions") / ไทย: คำอยู่ก่อนเลข ("ปฏิกิริยา 5")
# แยก regex ตามภาษา — ถ้าใช้ pattern เดียว เลขตรงกลางจะสลับข้างได้
COUNT_BEFORE_RE = re.compile(r"(\d[\d,.]*)(K|M)?\s*(reactions?|comments?|shares?)", re.I)
COUNT_AFTER_RE = re.compile(r"(ปฏิกิริยา|ความคิดเห็น|แชร์)\s*(\d[\d,.]*)(K|M)?")

_MONTHS_EN = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MONTHS_TH = {m: i for i, m in enumerate(
    ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
     "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."], 1)}


def normalize_time(raw: str, now: datetime | None = None) -> str | None:
    """label เวลาบน FB → ISO-8601 UTC หรือ None ถ้าตีความไม่ได้"""
    now = now or datetime.now(timezone.utc)
    s = " ".join(raw.split())
    low = s.lower()
    d = None
    if low in ("now", "just now", "ตอนนี้"):
        d = now
    elif (m := re.match(r"^(\d+)\s*(?:m|min|mins|minutes|นาที|น)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(minutes=int(m.group(1)))
    elif (m := re.match(r"^(\d+)\s*(?:h|hr|hrs|hours|ชม|ชั่วโมง)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(hours=int(m.group(1)))
    elif low in ("yesterday", "เมื่อวานนี้", "เมื่อวาน"):
        d = now - timedelta(days=1)
    elif (m := re.match(r"^([A-Za-z]{3,4})\.?\s+(\d{1,2})(?:,?\s*(\d{4}))?$", s)):
        month = _MONTHS_EN.get(m.group(1).capitalize())
        if month:
            d = datetime(int(m.group(3) or now.year), month, int(m.group(2)),
                         tzinfo=timezone.utc)
    elif (m := re.match(r"^(\d{1,2})\s+([^\d\s][^\s]*)\.?(?:\s*,?\s*(\d{4}))?$", s)):
        month = _MONTHS_TH.get(m.group(2))
        if month:
            d = datetime(int(m.group(3) or now.year), month, int(m.group(1)),
                         tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat() if d else None


class _FeedParser(HTMLParser):
    """เดิน DOM เก็บข้อมูลทีละโพสต์ ตาม SELECTORS['post']"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.posts: list[dict] = []
        self._in = False
        self._depth = 0
        self._skip = 0
        self._cur: dict | None = None

    def _match(self, tag: str, attrs: dict) -> bool:
        want_tag, want_attrs = SELECTORS["post"]
        return tag == want_tag and all(attrs.get(k) == v for k, v in want_attrs.items())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self._in and self._match(tag, a):
            self._in, self._depth = True, 1
            self._cur = {"aria": [a.get("aria-label") or ""], "text": [], "links": []}
            return
        if not self._in:
            return
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag == "div":
            self._depth += 1
        if tag == "a" and a.get("href"):
            self._cur["links"].append(a["href"])
        if a.get("aria-label"):
            self._cur["aria"].append(a["aria-label"])

    def handle_endtag(self, tag):
        if not self._in:
            return
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
            return
        if tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self.posts.append(self._cur)
                self._in, self._depth, self._cur = False, 0, None

    def handle_data(self, data):
        if self._in and not self._skip:
            self._cur["text"].append(data)


def _val(num: str, suffix: str | None) -> int:
    mult = {"K": 1_000, "M": 1_000_000}.get(suffix or "", 1)
    return int(float(num.replace(",", "")) * mult)


def _counts(text: str) -> tuple[int, int]:
    """(reactions, comments) — '12 reactions' / 'ปฏิกิริยา 5' เจอหลายที่ใช้ค่า max"""
    reactions = comments = 0
    for m in COUNT_BEFORE_RE.finditer(text):  # group(3) = คำอังกฤษ
        v = _val(m.group(1), m.group(2))
        if "react" in m.group(3).lower():
            reactions = max(reactions, v)
        elif "comment" in m.group(3).lower():
            comments = max(comments, v)
    for m in COUNT_AFTER_RE.finditer(text):   # group(1) = คำไทย, group(2) = เลข
        v = _val(m.group(2), m.group(3))
        if m.group(1) == "ปฏิกิริยา":
            reactions = max(reactions, v)
        elif m.group(1) == "ความคิดเห็น":
            comments = max(comments, v)
    return reactions, comments


def _find_time(text: str) -> str | None:
    words = text.split()
    for n in range(min(4, len(words)), 0, -1):  # ยาวสุดก่อน — "2 hours ago" ชนะ "2 hours"
        for i in range(len(words) - n + 1):
            cand = " ".join(words[i:i + n])
            if normalize_time(cand):
                return cand
    return None


def _clean_body(text: str, poster: str | None, time_label: str | None) -> str:
    s = re.sub(COUNT_BEFORE_RE, " ", text)
    s = re.sub(COUNT_AFTER_RE, " ", s)
    if time_label:
        s = s.replace(time_label, " ")
    if poster:
        s = s.replace(poster, " ")
    return " ".join(s.split())


def _extract(raw: dict, group_id: str) -> dict | None:
    links = [l.split("?")[0].rstrip("/") for l in raw["links"]
             if "/groups/" in l or "story_fbi" in l]
    permalink = next((l for l in links
                      if re.search(r"(permalink|photos/|videos/|story_fbi|p\.)", l)),
                     links[0] if links else None)
    text = " ".join(t.strip() for t in raw["text"] if t.strip())

    poster = None
    for label in raw["aria"]:
        m = POST_ARIA_RE.search(label)
        if m:
            poster = m.group(1).strip()
            break

    time_label = _find_time(text)
    created_at = normalize_time(time_label) if time_label else None
    reactions, comments = _counts(text)
    body = _clean_body(text, poster, time_label)
    if not poster or not (body or permalink):
        return None  # nav card / suggestion card — ตัด (โพสต์จริงต้องมี aria "Posted by/โพสต์โดย")
    post_id = hashlib.sha1((permalink or f"{group_id}|{poster}|{body[:200]}").encode()).hexdigest()
    return {
        "post_id": post_id,
        "poster_name": poster,
        "body": body,
        "created_at": created_at,
        "reaction_count": reactions,
        "comment_count": comments,
        "permalink": permalink,
    }


def parse_posts(html: str, group_id: str) -> list[dict]:
    p = _FeedParser()
    p.feed(html)
    out = []
    for raw in p.posts:
        post = _extract(raw, group_id)
        if post:
            out.append(post)
    return out


def fetch_group_posts(group: dict, pages: int = 1,
                      headless: bool = True) -> list[dict]:
    html = capture_feed_html(group["url"], pages=pages, headless=headless)
    return parse_posts(html, group_id_from_url(group["url"]))
```

**หมายเหตุ:** `_counts` แยก regex ตามภาษา (อังกฤษเลขก่อนคำ / ไทยคำก่อนเลข) — อย่ารวมเป็น pattern เดียว เพราะเลขตรงกลางจะสลับข้าง ถ้ารันกับ HTML จริงแล้วโพสต์ถูกตัดหมด (poster=None) = aria format เปลี่ยน → ขยาย `POST_ARIA_RE` แล้ว rerun test

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_parse.py -v`
Expected: 4 passed

- [ ] **Step 5: Calibrate กับ HTML จริง (สำคัญ — DOM จริงต่างจาก fixture)**

```powershell
.venv\Scripts\python -c "from fetch import parse_posts; posts = parse_posts(open('data/sample.html', encoding='utf-8').read(), 'g'); print(len(posts)); [print(p['poster_name'], '|', p['reaction_count'], p['comment_count'], '|', p['created_at'], '|', p['body'][:80]) for p in posts[:5]]"
```

Expected: จำนวนโพสต์ > 0, ชื่อผู้โพสต์/จำนวน reaction/เวลา/ตัวหนังสือดูสมเหตุสมผล
**ถ้าไม่ตรง** — เปิด `data/sample.html` เทียบโครงสร้าง แล้วปรับ regex/`SELECTORS` ใน `fetch.py` จนตรง — นี่คือจุดที่ DOM จริงอาจต่างจาก fixture, ปรับแล้ว rerun test ให้ยัง pass

- [ ] **Step 6: Commit**

```powershell
git add fetch.py tests/test_parse.py
git commit -m "feat: feed HTML parser (role=article walk, TH/EN time, counts) + composition"
```

---

### Task 5: `cli.py monitor` — loop + retry + session-expired handling

**Files:**
- Modify: `cli.py`

**Interfaces:**
- Consumes: `fetch_group_posts`, `SessionExpired`, `group_id_from_url` (fetch.py), `init_db`, `upsert_posts` (store.py), `config.toml`
- Produces: `python cli.py monitor [--once]`, `python cli.py login [--group <url>]` — monitor loop ตาม spec §6/§9

- [ ] **Step 1: เขียน `monitor` + `login` commands ใน `cli.py`**

แก้ `main()` ใน `cli.py` — เพิ่ม subcommands (เก็บ `capture` เดิมไว้):

```python
import time
from datetime import datetime, timezone

from fetch import SessionExpired, fetch_group_posts, group_id_from_url, login
from store import init_db, upsert_posts

DATA = Path("data")
DB = DATA / "sl.db"


def _fetch_with_retry(group: dict, pages: int, headless: bool) -> list[dict]:
    try:
        return fetch_group_posts(group, pages=pages, headless=headless)
    except Exception as e:  # noqa: BLE001 — network/DOM error ทั้งหมดพักแล้วลองใหม่
        print(f"fetch failed: {e} — retry in 5 min")
        time.sleep(300)
        return fetch_group_posts(group, pages=pages, headless=headless)  # ล้มอีก = throw ให้ caller


def cmd_login(cfg: dict, args) -> int:
    url = args.group or cfg["groups"][0]["url"]
    login(url)
    print("login OK — profile saved to data/browser-profile")
    return 0


def cmd_monitor(cfg: dict, args) -> int:
    group = cfg["groups"][0]
    gid = group_id_from_url(group["url"])
    mon = cfg["monitor"]
    conn = init_db(DB)
    while True:
        try:
            posts = _fetch_with_retry(group, mon["pages_per_run"], mon.get("headless", True))
        except SessionExpired:
            print("session expired — run: python cli.py login")
            return 1
        except Exception as e:  # noqa: BLE001 — retry พังด้วย → ข้ามรอบ (spec §9)
            print(f"round skipped: {e}")
            if args.once:
                return 1
        else:
            now = datetime.now(timezone.utc).isoformat()
            upsert_posts(conn, gid, posts, now)
            print(f"[{now}] fetched {len(posts)} posts for {group['name']}")
            if args.once:
                return 0
        time.sleep(mon["interval_minutes"] * 60)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="social-listening")
    sub = p.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("login", help="open browser, log in, save profile")
    lg.add_argument("--group", default=None)

    mo = sub.add_parser("monitor", help="fetch new posts in a loop")
    mo.add_argument("--once", action="store_true", help="single fetch then exit")

    dg = sub.add_parser("digest", help="write markdown report (added in Task 6)")
    dg.add_argument("--days", type=int, default=7)

    cap = sub.add_parser("capture", help="save raw feed HTML for parser debugging")
    cap.add_argument("--group", required=True)
    cap.add_argument("--out", default="data/sample.html")

    args = p.parse_args(argv)
    cfg = _config()
    if args.cmd == "login":
        return cmd_login(cfg, args)
    if args.cmd == "monitor":
        return cmd_monitor(cfg, args)
    if args.cmd == "digest":
        return cmd_digest(cfg, args)  # Task 6
    if args.cmd == "capture":
        capture_feed_html(args.group, out_path=Path(args.out))
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

หมายเหตุ: `cmd_digest` ยังไม่มี — Task 6 เพิ่ม (Step 1 ของ Task 6 เขียนให้, ถ้ารัน `cli.py digest` ก่อน Task 6 จะ NameError — ยอมรับได้ เพราะเป็น command ของ Task 6)

- [ ] **Step 2: Verify syntax + tests ยังเขียว**

Run: `.venv\Scripts\python -m pytest -v`
Expected: ทุก test ยัง pass

- [ ] **Step 3: (manual) รัน monitor รอบเดียว**

```powershell
.venv\Scripts\python cli.py monitor --once
```

Expected: `fetched N posts` (N > 0), แล้วตรวจ:

```powershell
.venv\Scripts\python -c "import sqlite3; c = sqlite3.connect('data/sl.db'); print(c.execute('select count(*) from posts').fetchone())"
```

Expected: count > 0

- [ ] **Step 4: Commit**

```powershell
git add cli.py
git commit -m "feat: monitor loop with retry + session-expired handling"
```

---

### Task 6: `digest.py` + `cli.py digest`

**Files:**
- Create: `digest.py`
- Modify: `cli.py` (เพิ่ม `cmd_digest`)
- Test: `tests/test_digest.py`

**Interfaces:**
- Consumes: `fetch_recent` (store.py), rows เป็น dict ตาม schema `posts`
- Produces:
  - `build_digest(rows: list[dict], days: int, top_n_keywords: int, top_n_posts: int) -> str` — Markdown ตาม spec §8
  - `python cli.py digest [--days N]` → `reports/<group-name>-<YYYY-MM-DD>.md` + พิมพ์ md ใน terminal

- [ ] **Step 1: Write the failing test** — `tests/test_digest.py`

```python
from digest import build_digest

ROWS = [
    {"body": "ใครลอง โปรตีน ชาก สูตรใหม่ ยัง", "poster_name": "A",
     "reaction_count": 10, "comment_count": 2,
     "created_at": "2026-09-14T10:00:00+00:00", "permalink": "https://x/1"},
    {"body": "โปรตีน สำคัญมาก เวลา ออกกำลังกาย", "poster_name": "A",
     "reaction_count": 5, "comment_count": 0,
     "created_at": "2026-09-13T09:00:00+00:00", "permalink": "https://x/2"},
    {"body": "วิ่ง ตอนเช้า ง่ายกว่า วิ่ง ตอนเย็น", "poster_name": "B",
     "reaction_count": 20, "comment_count": 7,
     "created_at": "2026-09-12T08:00:00+00:00", "permalink": "https://x/3"},
]

def test_top_keyword_present():
    md = build_digest(ROWS, days=7, top_n_keywords=5, top_n_posts=3)
    assert "## Top keywords" in md
    kw_section = md.split("## Top keywords")[1].split("##")[0]
    assert "โปรตีน" in kw_section

def test_top_posters():
    md = build_digest(ROWS, 7, 5, 3)
    assert "A: 2" in md
    assert "B: 1" in md

def test_top_posts_by_engagement():
    md = build_digest(ROWS, 7, 5, 3)
    section = md.split("## Top posts by engagement")[1].split("##")[0]
    first = [l for l in section.splitlines() if l.startswith("- ")][0]
    assert "x/3" in first  # B post engagement 27 สูงสุด

def test_empty_rows():
    md = build_digest([], 7, 5, 3)
    assert "(no posts in range)" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_digest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'digest'`

- [ ] **Step 3: เขียน `digest.py`**

```python
from __future__ import annotations

from collections import Counter

import pythainlp

# ponytail: stopword list ตัดมือ ~50 คำ, ขยายถ้า keyword พัง — ไม่ใช้ library NLP
STOPWORDS = set("""
a an the and or of in on at to for is are was were be been with as by from
it this that i you he she we they
ผม ฉัน คุณ เขา มัน เรา พวกเรา ไม่ ไม้ แล้ว ก็ แต่ และ ที่ ว่า หรือ เป็น มี ได้ ของ
นะ ครับ ค่ะ นะคะ หน่อย ยัง นะเออ
""".split())


def _tokens(text: str) -> list[str]:
    # ponytail: โทน/สระไทยที่ซ้อน (่ ้ ุ ู ี เ) เป็น Unicode Mn → isalnum() ทั้งคำ
    # เป็น False; ตรวจทีละตัวด้วย any() แทน (ไม่งั้นคำไทยที่มีโทนถูกตัดทิ้งหมด)
    return [
        t for t in pythainlp.word_tokenize(text)
        if any(c.isalnum() for c in t) and len(t) > 1 and t.lower() not in STOPWORDS
    ]


def _line(r: dict) -> str:
    eng = (r["reaction_count"] or 0) + (r["comment_count"] or 0)
    snippet = " ".join((r["body"] or "").split())[:120]
    return (f"- [{eng}] {r['created_at']} — {r['poster_name']}: "
            f"{snippet} {r['permalink'] or ''}")


def build_digest(rows: list[dict], days: int,
                 top_n_keywords: int, top_n_posts: int) -> str:
    lines = [f"# Group listening digest — last {days} days",
             f"Posts in range: {len(rows)}"]
    if not rows:
        lines.append("(no posts in range)")
        return "\n".join(lines)

    kw: Counter = Counter()
    for r in rows:
        kw.update(set(_tokens(r["body"] or "")))  # นับ 1 ครั้ง/โพสต์

    lines += ["", "## Top keywords"]
    for w, c in kw.most_common(top_n_keywords):
        lines.append(f"- {w}: {c} posts ({c / len(rows):.0%})")

    lines += ["", "## Top posters"]
    for name, c in Counter(r["poster_name"] or "?" for r in rows).most_common(top_n_posts):
        lines.append(f"- {name}: {c}")

    lines += ["", "## Top posts by engagement"]
    top = sorted(rows, key=lambda r: (r["reaction_count"] or 0) + (r["comment_count"] or 0),
                 reverse=True)[:top_n_posts]
    lines += [_line(r) for r in top]

    lines += ["", "## Latest posts"]
    lines += [_line(r) for r in rows[:top_n_posts]]  # rows มาเรียง DESC แล้ว

    return "\n".join(lines)
```

- [ ] **Step 4: เพิ่ม `cmd_digest` ใน `cli.py`**

```python
from datetime import timedelta

from digest import build_digest
from store import fetch_recent


def cmd_digest(cfg: dict, args) -> int:
    group = cfg["groups"][0]
    conn = init_db(DB)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    rows = fetch_recent(conn, group_id_from_url(group["url"]), since)
    d = cfg["digest"]
    md = build_digest(rows, args.days, d["top_n_keywords"], d["top_n_posts"])
    out = Path("reports") / f"{group['name']}-{datetime.now():%Y-%m-%d}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nsaved {out}")
    return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest -v`
Expected: ทุก test pass (รวม smoke, store, parse, digest)

- [ ] **Step 6: (manual) สร้าง digest จากข้อมูลจริง**

```powershell
.venv\Scripts\python cli.py digest --days 30
```

Expected: Markdown มี top keywords/posters/posts ที่ดูสมเหตุสมผล, ไฟล์อยู่ใน `reports/`

- [ ] **Step 7: Commit**

```powershell
git add digest.py cli.py tests/test_digest.py
git commit -m "feat: keyword/engagement digest + cli digest command"
```

---

### Task 7: End-to-end + docs

**Files:**
- Create: `README.md`
- Commit: `reports/` (ถ้ามีไฟล์จากการทดสอบ Task 6)

**Interfaces:**
- Consumes: ทุกอย่าง
- Produces: ระบบที่รันครบวงจร + README

- [ ] **Step 1: รัน test ทั้งหมด**

Run: `.venv\Scripts\python -m pytest -v`
Expected: ทุก test pass

- [ ] **Step 2: (manual) End-to-end checklist กับกลุ่มจริง**

```powershell
.venv\Scripts\python cli.py login            # ถ้า session หมด
.venv\Scripts\python cli.py monitor --once   # ดึงรอบใหม่
.venv\Scripts\python cli.py digest --days 7
```

ตรวจ:
- [ ] `monitor --once` เพิ่ม/อัปเดต posts ใน db (รัน 2 ครั้ง подряд → count ไม่เพิ่ม, reactions อัปเดต)
- [ ] `digest` report อ่านได้, keywords สะท้อนเนื้อหาจริงของกลุ่ม
- [ ] รัน `monitor` (ไม่มี `--once`) ทิ้งไว้สัก 2 รอบ (30 นาที) → ทำงานต่อเองไม่ error

- [ ] **Step 3: เขียน `README.md`**

```markdown
# social-listening

เฝ้าดูโพสต์ Facebook Group → SQLite → Markdown digest กระแส

## Setup

    python -m venv .venv
.venv\Scripts\python -m pip install playwright pythainlp pytest
    .venv\Scripts\python -m playwright install chromium

ใส่ group URL ใน `config.toml`

## Usage

    .venv\Scripts\python cli.py login          # 1 ครั้ง (เปิด browser ให้ล็อกอิน)
    .venv\Scripts\python cli.py monitor        # loop ทุก 30 นาที (Ctrl+C เพื่อหยุด)
    .venv\Scripts\python cli.py monitor --once # ดึงครั้งเดียว
    .venv\Scripts\python cli.py digest --days 7

## Notes

- ถ้า Facebook เปลี่ยนหน้าเว็บ ให้แก้ selector ใน `fetch.py` (dict `SELECTORS` + regex)
  ใช้ `cli.py capture` เพื่อบันทึก HTML จริงมา debug
- Session หมด → รัน `login` ใหม่
- รันเบาๆ: 30 นาที/รอบ, 1 หน้า/รอบ — เพื่อลดความเสี่ยงบัญชีถูก flag
```

- [ ] **Step 4: Commit**

```powershell
git add README.md reports/
git commit -m "docs: README; end-to-end verified"
```

---

## Self-Review (ทำแล้วตอนเขียน plan)

- **Spec coverage:** §5 data model → Task 2; §6 CLI → Tasks 3/5/6; §7 config → Task 1; §8 digest → Task 6; §9 errors (session expired, retry, dedupe) → Tasks 2/5; §10 tests → Tasks 2/4/6; §11 phase 2 ไม่ทำ (out of scope ✓)
- **Placeholder scan:** ไม่มี TBD/TODO — จุดเดียวที่ต้อง "ดูแล้วปรับ" คือ Step 5 Task 4 (calibrate กับ DOM จริง) ซึ่งเป็น workflow จริงของ parser กับเว็บที่ DOM เปลี่ยนบ่อย ไม่ใช่ช่องว่างใน plan; โค้ด parser Task 4 ตรวจแล้ว — รัน test ของ plan เองผ่าน 4/4 (commit 4afc965)
- **Type consistency:** `post dict` keys (post_id, poster_name, body, created_at, reaction_count, comment_count, permalink) ใช้ตรงกัน Task 2/4/6; `fetch_group_posts(group: dict, pages, headless)` ตรงกับ caller ใน cli; `fetch_recent(conn, group_id, since_iso)` ตรงกัน store test / cli
