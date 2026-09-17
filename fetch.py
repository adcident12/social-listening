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
        page.wait_for_timeout(5000)  # ponytail: FB ไม่เข้า networkidle (long-poll ตลอด) — fixed wait, เพิ่มเป็น 10s ถ้า cookie หลุด
    finally:
        ctx.close()
        pw.stop()

def _expand_collapsed(page, limit: int = 10) -> None:
    """คลิก "ดูเพิ่่มเติม" ของโพสต์ที่ถูก truncate — ไม่คลิกก็เก็บได้แค่ย่อหน้าแรก"""
    for label in ("\u0e14\u0e39\u0e40\u0e1e\u0e34\u0e48\u0e21\u0e40\u0e15\u0e34\u0e21",  # ดูเพิ่่มเติม (DOM ใช้ 0E39)
                  "\u0e14\u0e38\u0e40\u0e1e\u0e34\u0e48\u0e21\u0e40\u0e15\u0e34\u0e21",
                  "See more"):
        btns = page.locator(f'div[role="button"]:has-text("{label}")')
        for i in range(min(btns.count(), limit)):  # ponytail: cap 10/รอบ, เพิ่ม limit ถ้าโพสต์ยาวเยอะ
            try:
                btns.nth(i).click(timeout=3000)
                page.wait_for_timeout(300)
            except Exception:
                continue  # DOM re-render ระหว่างคลิก → ลองปุ่มถัดไป


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
        _expand_collapsed(page)
        page.wait_for_timeout(5000)  # ponytail: FB ไม่เข้า networkidle (long-poll ตลอด) — fixed wait, เพิ่มเป็น 10s ถ้าโพสต์หายไป
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
# DOM จริง (calibrate 2026-09-17): count แยกเดี่ยว "R C [S] ดู…เพิ่่มเติม"
# label เป็น token เดียว → ใช้ \S* tail หลีก codepoint variant; unit = K/M หรือ พัน (0E1B/0E1E); เลขมีทศนิยมได้
BARE_COUNT_RE = re.compile(
    r"(\d[\d,.]*)(?:\s*([KM]|[\u0e1b\u0e1e]\u0e31\u0e19))?\s+"
    r"(\d[\d,.]*)(?:\s*([KM]|[\u0e1b\u0e1e]\u0e31\u0e19))?\s+"
    r"(?:(\d[\d,.]*)(?:\s*([KM]|[\u0e1b\u0e1e]\u0e31\u0e19))?\s+)?"
    r"\u0e14[\u0e38\u0e39]\S*")
# ".... <see-more>" body ตัดบน feed / <show-less> เมื่อ expand แล้ว — DOM cps ตรวจแล้ว
SEE_MORE_RE = re.compile(r"\u0e14\u0e39\u0e40\u0e1e\u0e34\u0e48\u0e21\u0e40\u0e15\u0e34\u0e21")  # ดูเพิ่่มเติม
SHOW_LESS_RE = re.compile(r"\u0e14\u0e39\u0e19\u0e49\u0e2d\u0e22\u0e25\u0e07")  # ดูน่อยลง
# aria ของเมนูโพสต์: "การดำเนินการสำหรั บโพสต์นี้โดย <ชื่อ>" — แหล่งชื่อ poster ที่เชื่อถือได้
ACTION_ARIA_RE = re.compile(
    r"(?:การดำเนินการ\S+โดย|Actions for (?:this|the) post by)\s*(.+)$", re.S)
# post line ของจริง: "ชื่อ [badge] · เวลา · body" (fallback เท่านั้น — text layout สลับบ่อย)
POST_LINE_RE = re.compile(r"^(?P<poster>[^·]+?)\s*·\s*(?P<time>[^·]+?)\s*·\s*(?P<body>.*)$", re.S)
BADGE_RE = re.compile(
    r"\s*(ผู้ดูแล|ผู้เขียน|ผู้ก่อตั้ง|ผู้มีส่วนร่วมดาวเด่น|Member|Owner|Admin|Author)(,.*)?$")
LOADING_RE = re.compile(r"กำลังโหลด|Loading")

_MONTHS_EN = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MONTHS_TH = {m: i for i, m in enumerate(
    ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
     "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."], 1)}
_MONTHS_TH.update({m: i for i, m in enumerate(
    ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม",
     "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม",
     "พฤศจิกายน", "ธันวาคม"], 1)})  # ชื่อเต็ม map 1-12 เหมือนตัวย่อ


def normalize_time(raw: str, now: datetime | None = None) -> str | None:
    """label เวลาบน FB → ISO-8601 UTC หรือ None ถ้าตีความไม่ได้"""
    now = now or datetime.now(timezone.utc)
    s = " ".join(raw.split())
    s = re.sub(r"\s*เวลา\s+\d{1,2}:\d{2}(?:\s*น\.)?$", "", s)  # "9 กันยายน เวลา 11:50 น." → base label
    low = s.lower()
    d = None
    if low in ("now", "just now", "ตอนนี้"):
        d = now
    elif (m := re.match(r"^(\d+)\s*(?:m|min|mins|minutes|นาที|น)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(minutes=int(m.group(1)))
    elif (m := re.match(r"^(\d+)\s*(?:h|hr|hrs|hours|ชม|ชั่วโมง)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(hours=int(m.group(1)))
    elif (m := re.match(r"^(\d+)\s*(?:d|days?|วัน)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(days=int(m.group(1)))
    elif (m := re.match(r"^(\d+)\s*(?:w|weeks?|สัปดาห์)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(weeks=int(m.group(1)))
    elif (m := re.match(r"^(\d+)\s*(?:mo|months?|เดื\S*)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(days=30 * int(m.group(1)))  # ponytail: ~30 วัน/เดือน
    elif (m := re.match(r"^(\d+)\s*(?:y|yrs?|years?|ปี)\.?(?:\s*(?:ago|ที่แล้ว))?$", low)):
        d = now - timedelta(days=365 * int(m.group(1)))  # ponytail: ~365 วัน/ปี
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
    s = suffix or ""
    if s == "M":
        mult = 1_000_000
    elif s in ("K", "\u0e1b\u0e31\u0e19", "\u0e1e\u0e31\u0e19"):  # พัน (DOM 2 codepoint variants)
        mult = 1_000
    else:
        mult = 1
    return int(round(float(num.replace(",", "")) * mult))  # round: 1.4*1000 = 1399.999...


def _counts(text: str) -> tuple[int, int, int]:
    """(reactions, comments, shares) — หลาย pattern ใช้ค่า max; บล็อกแรก: R [C] [S] ถูกใจ"""
    reactions = comments = shares = 0
    m = REACTION_BLOCK_RE.search(text)  # DOM จริง: "ความรู้สึกทั้งหมด 117 6 2 ถูกใจ"
    if m:
        reactions = _val(m.group(1), m.group(2))
        if m.group(3):
            comments = _val(m.group(3), None)
        if m.group(4):
            shares = _val(m.group(4), None)
    for m in COUNT_BEFORE_RE.finditer(text):  # group(3) = คำอังกฤษ
        v = _val(m.group(1), m.group(2))
        if "react" in m.group(3).lower():
            reactions = max(reactions, v)
        elif "comment" in m.group(3).lower():
            comments = max(comments, v)
        elif "share" in m.group(3).lower():
            shares = max(shares, v)
    for m in COUNT_AFTER_RE.finditer(text):   # group(1) = คำไทย, group(2) = เลข
        v = _val(m.group(2), m.group(3))
        if m.group(1) == "ปฏิกิริยา":
            reactions = max(reactions, v)
        elif m.group(1) == "ความคิดเห็น":
            comments = max(comments, v)
        elif m.group(1) == "แชร์":
            shares = max(shares, v)
    for m in BARE_COUNT_RE.finditer(text):  # DOM: "51 6 18 ดูคำตอบเพิ่่มเติม"
        reactions = max(reactions, _val(m.group(1), m.group(2)))
        comments = max(comments, _val(m.group(3), m.group(4)))
        if m.group(5):
            shares = max(shares, _val(m.group(5), m.group(6)))
    return reactions, comments, shares


def _first_time(text: str) -> str | None:
    """ซ้ายสุด = เวลาโพสต์ (เวลาคอมเมนต์อยู่หลัง count block) — แต่ละตำแหน่งลองยาวสุดก่อน"""
    words = text.split()
    for i in range(len(words)):
        for n in range(min(4, len(words) - i), 0, -1):
            cand = " ".join(words[i:i + n])
            if normalize_time(cand):
                j = cand.find("\u0e40\u0e27\u0e25\u0e32")  # normalize_time ยอมรับ "… เวลา HH:MM" — คืน base label
                return cand[:j].strip() if j > 0 else cand
    return None


def _clean_body(text: str, poster: str | None, time_label: str | None) -> str:
    # ตัดที่จุดแรกสุดของ count block / ป้าย see-more, show-less / ป้ายท้ายโพสต์
    cuts = [m.start() for m in (REACTION_BLOCK_RE.search(text),
                                BARE_COUNT_RE.search(text),
                                SEE_MORE_RE.search(text),
                                SHOW_LESS_RE.search(text)) if m]
    for marker in ("แสดงความคิดเห็นในช", "ตอบในช", "ตอบกลับ แชร์"):
        i = text.find(marker)
        if i >= 0:
            cuts.append(i)
    if cuts:
        text = text[:min(cuts)]
    s = re.sub(COUNT_BEFORE_RE, " ", text)
    s = re.sub(COUNT_AFTER_RE, " ", s)
    if time_label:
        s = s.replace(time_label, " ")
    s = re.sub(r"\s*เวลา\s+\d{1,2}:\d{2}(?:\s*น\.)?", " ", s)  # เวลาเกิน base label
    if poster:
        s = s.replace(poster, " ")
    s = s.replace("\u0e15\u0e34\u0e14\u0e15\u0e32\u0e21", " ")  # ติดตาม
    s = s.replace("\u00b7", " ").replace("\u2022", " ")
    s = " ".join(s.split())
    if s.startswith("ตัวบ่งชี้สถานะออนไลน์ กำลังใช้งาน"):
        s = s[len("ตัวบ่งชี้สถานะออนไลน์ กำลังใช้งาน"):].lstrip()  # tooltip online-status หลุด
    s = s.lstrip(", ")
    s = re.sub(r"^(?:ผู้ดูแล|ผู้เขียน|ผู้ก่อตั้ง|ผู้มีส่วนร่วมดาวเด่น|Member|Owner|Admin|Author)\s+", " ", s)  # badge หลุดจาก header
    mid = (len(s) - 1) // 2  # FB ซ้ำ body 2 รอบในบางโพสต์ ("X X")
    if len(s) > 20 and len(s) % 2 == 1 and s[mid] == " " and s[:mid] == s[mid + 1:]:
        s = s[:mid]
    return s.rstrip(" .")


def _extract(raw: dict, group_id: str) -> dict | None:
    if any(LOADING_RE.search(a) for a in raw["aria"]):
        return None  # loading skeleton (role=article ด้วย แต่ไม่ใช่โพสต์)
    links = [l.split("?")[0].rstrip("/") for l in raw["links"]]
    links = ["https://www.facebook.com" + l if l.startswith("/") else l
             for l in links if "/groups/" in l or "story_fbi" in l]
    permalink = next((l for l in links
                      if re.search(r"(permalink|photos/|videos/|posts/|story_fbi|p\.)", l)),
                     None)  # ไม่เดา links[0] — เคยเลือกได้ลิงก์ /user/ ผิด
    text = " ".join(t.strip() for t in raw["text"] if t.strip())
    line = POST_LINE_RE.match(text)  # fallback poster เท่านั้น — text layout สลับบ่อย
    time_label = _first_time(text)  # ซ้ายสุดของข้อความเต็ม = เวลาโพสต์

    poster = None
    for a in raw["aria"]:  # aria เมนูโพสต์: "การดำเนินการ...โดย <ชื่อ>" — แม่นสุด
        m = ACTION_ARIA_RE.search(a)
        if m:
            poster = m.group(1).strip()
            break
    if not poster:
        for a in raw["aria"]:  # aria "Posted by X in Y"
            m = POST_ARIA_RE.search(a)
            if m:
                poster = m.group(1).strip()
                break
    if not poster and line:
        poster = BADGE_RE.sub("", line.group("poster")).strip()
    if not poster:  # fallback: ชื่อ poster ซ้ำเป็น aria-label ≥2 (avatar + name link)
        from collections import Counter
        cand = Counter(a.strip() for a in raw["aria"][1:]
                       if 2 <= len(a.strip()) <= 40 and not normalize_time(a)
                       and not re.search(r"ความคิดเห็น|ผู้ดูแล|กำลังโหลด|ถูกใจ|แชร์|แสดง|ดำเนินการ", a))
        if cand:
            poster = cand.most_common(1)[0][0]

    sm = SEE_MORE_RE.search(text)
    sl = SHOW_LESS_RE.search(text)
    if sl:  # expand แล้ว: teaser + full body — full body อยู่ระหว่าง 2 ป้าย
        head = text[sm.end():sl.start()] if sm else text[:sl.start()]
    else:  # sm หรือครบแล้ว — _clean_body ตัดเอง: BARE start ≤ sm start (ตัดที่ count ก่อน see-more), ไม่อย่างนั้นตัดที่ see-more
        head = text

    created_at = normalize_time(time_label) if time_label else None
    reactions, comments, shares = _counts(text)  # count อยู่ท้ายข้อความเต็ม
    body = _clean_body(head, poster, time_label)
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
        "share_count": shares,
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
