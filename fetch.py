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

import hashlib
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

# DOM จริง (calibrate 2026-09-16): "ความรู้สึกทั้งหมด N [cm] [sh] ถูกใจ" — เลขมาก่อน label
REACTION_BLOCK_RE = re.compile(
    r"ความรู้สึกทั้งหมด\s*(\d[\d,.]*)([KM])?\s*([0-9][0-9,]*)?\s*([0-9][0-9,]*)?\s*ถูกใจ")
# post line ของจริง: "ชื่อ [badge] · เวลา · body" (ไม่มี aria "Posted by")
POST_LINE_RE = re.compile(r"^(?P<poster>[^·]+?)\s*·\s*(?P<time>[^·]+?)\s*·\s*(?P<body>.*)$", re.S)
BADGE_RE = re.compile(r"\s*(ผู้ดูแล|ผู้เขียน|ผู้ก่อตั้ง|Owner|Admin|Author)(,.*)?$")
LOADING_RE = re.compile(r"กำลังโหลด|Loading")

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
    """(reactions, comments) — หลาย pattern ใช้ค่า max; เลขบล็อกแรกคือ reactions"""
    reactions = comments = 0
    m = REACTION_BLOCK_RE.search(text)  # DOM จริง: "ความรู้สึกทั้งหมด 117 6 2 ถูกใจ"
    if m:
        reactions = _val(m.group(1), m.group(2))
        if m.group(3):
            comments = _val(m.group(3), None)
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
    if any(LOADING_RE.search(a) for a in raw["aria"]):
        return None  # loading skeleton (role=article ด้วย แต่ไม่ใช่โพสต์)
    links = [l.split("?")[0].rstrip("/") for l in raw["links"]
             if "/groups/" in l or "story_fbi" in l]
    permalink = next((l for l in links
                      if re.search(r"(permalink|photos/|videos/|story_fbi|p\.)", l)),
                     links[0] if links else None)
    text = " ".join(t.strip() for t in raw["text"] if t.strip())

    poster = None
    time_label = None
    body = text
    m = POST_LINE_RE.match(text)  # DOM จริง: "ชื่อ [badge] · เวลา · body"
    if m:
        poster = BADGE_RE.sub("", m.group("poster")).strip()
        time_label = m.group("time").strip()
        body = m.group("body")
    else:
        for label in raw["aria"]:  # fallback: aria "Posted by X in Y"
            m2 = POST_ARIA_RE.search(label)
            if m2:
                poster = m2.group(1).strip()
                break
        time_label = _find_time(text)

    created_at = normalize_time(time_label) if time_label else None
    reactions, comments = _counts(body)
    body = re.split(r"ความรู้สึกทั้งหมด", body)[0]  # หลังบล็อกนี้คือ comments → ตัด
    body = _clean_body(body, poster, time_label)
    if not poster or not (body or permalink):
        return None  # nav card / suggestion card — ตัด
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
