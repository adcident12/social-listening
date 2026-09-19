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

def test_sentiment_all_unanalyzed():
    md = build_digest(ROWS, 7, 5, 3)
    section = md.split("## Sentiment")[1].split("##")[0]
    assert "ยังไม่ได้วิเคราะห์: 3 (100%)" in section
    assert "## โพสต์ลบเด่น" not in md


SENT_ROWS = [
    {**ROWS[0], "sentiment": "positive", "summary": "ชมสินค้า"},
    {**ROWS[1], "sentiment": "neutral"},
    {**ROWS[2], "sentiment": "negative", "summary": "บ่นเรื่องโค้ด"},
]


def test_sentiment_breakdown():
    md = build_digest(SENT_ROWS, 7, 5, 3)
    section = md.split("## Sentiment")[1].split("##")[0]
    assert "บวก: 1 (33%)" in section
    assert "กลาง: 1 (33%)" in section
    assert "ลบ: 1 (33%)" in section
    assert "ยังไม่ได้วิเคราะห์: 0 (0%)" in section


def test_notable_negative_section():
    md = build_digest(SENT_ROWS, 7, 5, 3)
    section = md.split("## โพสต์ลบเด่น")[1].split("##")[0]
    line = [l for l in section.splitlines() if l.startswith("- ")][0]
    assert "x/3" in line  # B post engagement 27 สูงสุด
    assert "(สรุป: บ่นเรื่องโค้ด)" in line


WATCH_ROWS = [
    {"body": "ใช้ Claude เขียนโค้ด แล้วส่ง AI ตรวจ", "poster_name": "C",
     "reaction_count": 1, "comment_count": 0,
     "created_at": "2026-09-14T11:00:00+00:00", "permalink": "https://x/4"},
    {"body": "I said no to that", "poster_name": "D",
     "reaction_count": 0, "comment_count": 0,
     "created_at": "2026-09-13T10:00:00+00:00", "permalink": "https://x/5"},
]


def test_watch_word_section():
    md = build_digest(WATCH_ROWS, 7, 5, 3, ["AI", "Claude"])
    section = md.split("## Brand mentions")[1].split("##")[0]
    assert "(ตรง: AI, Claude)" in section  # คำใน order ของ config
    assert "x/4" in section
    assert "x/5" not in section  # "said" มี "ai" แทรก — word boundary กัน


def test_watch_ascii_attached_to_thai_matches():
    rows = [{"body": "สั่งกาแฟ AI มาหนึ่งแก้ว", "poster_name": "E",
             "reaction_count": 0, "comment_count": 0,
             "created_at": "2026-09-13T10:00:00+00:00", "permalink": "https://x/6"}]
    md = build_digest(rows, 7, 5, 3, ["ai"])
    assert "## Brand mentions" in md  # ไม่มี space ระหว่างไทย-ASCII → ยังต้อง match


def test_watch_no_match_no_section():
    md = build_digest(ROWS, 7, 5, 3, ["กาแฟ"])
    assert "Brand mentions" not in md


def test_watch_no_words_no_section():
    md = build_digest(ROWS, 7, 5, 3)  # ไม่ส่ง watch_words — backward compatible
    assert "Brand mentions" not in md
