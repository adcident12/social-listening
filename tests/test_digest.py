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
