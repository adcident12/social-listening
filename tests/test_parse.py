from datetime import datetime, timezone

from fetch import normalize_time, parse_posts

FIXTURE = """
<html><body>
<div role="article">
  <span>Thannob Aribarg ผู้ดูแล</span><span> · </span><span>8 ชั่วโมง</span><span> · </span>
  <span>ใครลองโปรตีนชากสูตรใหม่ยัง อร่อยดี</span>
  <a href="https://www.facebook.com/groups/123/posts/99/?comment_id=1"></a>
  <span>ความรู้สึกทั้งหมด 117 6 2 ถูกใจ แสดงความคิดเห็น แชร์</span>
  <span>ดูความคิดเห็นเพิ่มเติม Nattapon Yongpaiboon ตัวเลขเกิดขึ้นจริงครับ 8 ชั่วโมง 2 ดู</span>
</div>
<div role="article" aria-label="โพสต์โดย Bob ใน Test Group.">
  <div>เมื่อวานนี้</div>
  <a href="https://www.facebook.com/groups/123/photos/p.88/">Bob</a>
  <div>ออกกำลังกายตอนเช้าดีกว่าตอนไหน</div>
  <div>ปฏิกิริยา 5 ความคิดเห็น 2</div>
</div>
<div role="article" aria-label="กำลังโหลด…">
  <div></div>
</div>
<div role="article" aria-label="Some nav card.">
  <a href="https://www.facebook.com/groups/123/members/">members</a>
</div>
<script>var x = "role=article trick";</script>
</body></html>
"""

def test_parse_posts_fields():
    posts = parse_posts(FIXTURE, "123")
    assert len(posts) == 2  # loading skeleton + nav card ถูกตัด
    a = posts[0]
    assert a["poster_name"] == "Thannob Aribarg"
    assert a["permalink"] == "https://www.facebook.com/groups/123/posts/99"
    assert a["reaction_count"] == 117
    assert a["comment_count"] == 6
    assert "โปรตีน" in a["body"]
    assert "ความรู้สึกทั้งหมด" not in a["body"]  # reaction block ตัดออก
    assert "Nattapon" not in a["body"]  # comment teaser ตัดออก
    assert a["created_at"] is not None
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
