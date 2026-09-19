from datetime import datetime, timezone

from fetch import _parse_comment_teaser, normalize_time, parse_posts

FIXTURE = """
<html><body>
<div role="article">
  <span>Thannob Aribarg ผู้ดูแล</span><span> · </span><span>8 ชั่วโมง</span><span> · </span>
  <span>ใครลองโปรตีนชากสูตรใหม่ยัง อร่อยดี</span>
  <a href="https://www.facebook.com/groups/123/posts/99/?comment_id=1"></a>
  <span>ความรู้สึกทั้งหมด 117 6 2 ถูกใจ แสดงความคิดเห็น แชร์</span>
  <span>ดูความคิดเห็นเพิ่มเติม Nattapon Yongpaiboon · 8 ชั่วโมง ตัวเลขเกิดขึ้นจริงครับ 2 ดู</span>
</div>
<div role="article" aria-label="โพสต์โดย Bob ใน Test Group.">
  <div>เมื่อวานนี้</div>
  <a href="https://www.facebook.com/groups/123/photos/p.88/">Bob</a>
  <div>ออกกำลังกายตอนเช้าดีกว่าตอนไหน</div>
  <div>ปฏิกิริยา 5 ความคิดเห็น 2</div>
</div>
<div role="article">
  <span aria-label="Charlie">Charlie</span><span aria-label="Charlie">C</span>
  <span aria-label="8 ชั่วโมง">8 ชั่วโมง</span>
  <span aria-label="ผู้ดูแล, ดูรายละเอียดเครื่องหมาย">ผู้ดูแล</span>
  <span>โพสต์ไม่มีไม้กระเดื่องแต่มี aria เวลา</span>
  <a href="https://www.facebook.com/groups/123/posts/77/"></a>
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
    assert len(posts) == 3  # loading skeleton + nav card ถูกตัด
    a = posts[0]
    assert a["poster_name"] == "Thannob Aribarg"
    assert a["permalink"] == "https://www.facebook.com/groups/123/posts/99"
    assert a["reaction_count"] == 117
    assert a["comment_count"] == 6
    assert a["share_count"] == 2  # "117 6 2 ถูกใจ" → เลขที่ 3 คือ shares
    assert "โปรตีน" in a["body"]
    assert "ความรู้สึกทั้งหมด" not in a["body"]  # reaction block ตัดออก
    assert "Nattapon" not in a["body"]  # comment teaser ตัดออก
    assert a["created_at"] is not None
    b = posts[1]
    assert b["poster_name"] == "Bob"
    assert b["reaction_count"] == 5
    assert b["comment_count"] == 2
    assert b["share_count"] == 0
    assert "ออกกำลังกาย" in b["body"]
    c = posts[2]
    assert c["poster_name"] == "Charlie"
    assert c["created_at"] is not None  # เวลาจาก aria "8 ชั่วโมง" (fallback 2)

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
    assert normalize_time("2 วัน", now=now) == "2026-09-13T12:00:00+00:00"
    assert normalize_time("16 สัปดาห์", now=now) == "2026-05-26T12:00:00+00:00"
    assert normalize_time("3 เดือน", now=now) == "2026-06-17T12:00:00+00:00"
    assert normalize_time("อะไรก็ไม่รู้", now=now) is None
    assert normalize_time("23 พฤษภาคม", now=now) == "2026-05-23T00:00:00+00:00"
    assert normalize_time("9 กันยายน เวลา 11:50 น.", now=now) == "2026-09-09T00:00:00+00:00"

def test_thai_unit_counts_and_see_more_cut():
    # "พัน" unit (decimal) + full month + เวลา suffix + body ตัดที่ see-more
    html = """
    <html><body>
    <div role="article">
      <span>สมชาย ใจดี</span><span> · </span><span>9 กันยายน เวลา 11:50 น.</span><span> · </span>
      <span>ข่าวดีวันนี้</span>
      <a href="https://www.facebook.com/groups/123/posts/55/"></a>
      <span>1.4 พัน 5.1 พัน 1.4 พัน \u0e14\u0e39\u0e40\u0e1e\u0e34\u0e48\u0e21\u0e40\u0e15\u0e34\u0e21</span>  # ดูเพิ่่มเติม — DOM cps (calibrate 2026-09-17)
    </div>
    </body></html>
    """
    posts = parse_posts(html, "123")
    assert len(posts) == 1
    p = posts[0]
    assert (p["reaction_count"], p["comment_count"], p["share_count"]) == (1400, 5100, 1400)
    assert p["created_at"] == "2026-09-09T00:00:00+00:00"
    assert p["body"] == "ข่าวดีวันนี้"
    assert "ติดตาม" not in p["body"]

def test_comment_teaser_parsed():
    posts = parse_posts(FIXTURE, "123")
    a = posts[0]
    assert a["comments_seen"] == 1
    assert len(a["comments"]) == 1
    c = a["comments"][0]
    assert c["poster_name"] == "Nattapon Yongpaiboon"
    assert c["body"] == "ตัวเลขเกิดขึ้นจริงครับ"
    assert c["reaction_count"] == 2  # trailing "N ดู" = comment reactions
    assert c["created_at"] is not None  # comment time
    assert "Nattapon" not in a["body"]  # teaser must not leak into post body

def test_comment_teaser_multi_comment():
    now = datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc)
    seg = ("ดูความคิดเห็นเพิ่มเติม "
           "Nattapon Yongpaiboon · 15 ชั่วโมง สวัสดีครับ "
           "ตอบกลับ แชร์ ดูการตอบกลับ 1 รายการ "
           "สมชาย ใจดี · 2 ชั่วโมง เป็นประโยชน์มากครับ "
           "ตอบกลับ แชร์ ดูการตอบกลับ 1 รายการ 3 ดู")
    seen, comments = _parse_comment_teaser(seg, now=now)
    assert seen == 2
    assert comments[0]["poster_name"] == "Nattapon Yongpaiboon"
    assert comments[0]["created_at"] == "2026-09-17T16:00:00+00:00"
    assert comments[0]["body"] == "สวัสดีครับ"
    assert comments[1]["poster_name"] == "สมชาย ใจดี"
    assert comments[1]["created_at"] == "2026-09-18T05:00:00+00:00"
    assert comments[1]["body"] == "เป็นประโยชน์มากครับ"
    assert comments[1]["reaction_count"] == 3  # trailing "N ดู" → comment สุดท้าย

def test_posts_without_teaser_have_no_comments():
    posts = parse_posts(FIXTURE, "123")
    for p in posts[1:]:
        assert p["comments"] == []
        assert p["comments_seen"] == 0
