# Facebook Group Social Listening — Design

Date: 2026-09-15
Status: Approved (in chat, pending spec review)

## 1. Background & Goal

เฝ้าดูโพสต์ใน Facebook Group ที่สนใจ บันทึกสะสมเป็น archive แล้วรายงาน
"ช่วงนี้กระแสเรื่องอะไร" ออกมาเป็น digest

## 2. Settled Decisions

| เรื่อง | ตัดสินใจแล้ว |
|---|---|
| กลุ่มเป้าหมาย | Private group, ผู้ใช้เป็นผู้member |
| แหล่งข้อมูล | Browser automation (Playwright) + บัญชี FB ของผู้ใช้เอง |
| ทำไมไม่ใช้ Official API | Graph API v26 (ตรวจสอบ 2026-09) ไม่เปิดให้ developer อ่าน feed ของ group ได้ |
| สิ่งที่ต้องบันทึก | โพสต์หลัก: ชื่อผู้โพสต์, body, เวลา, จำนวน reaction, จำนวน comment, permalink — ยังไม่รวมถึงเนื้อหา comment |
| ผลลัพธ์ | Markdown digest (รายวัน/รายสัปดาห์) |
| จำนวนกลุ่ม | เริ่ม 1 กลุ่ม, config รองรับหลายกลุ่ม |
| Tech stack | Python 3.11+, Playwright, SQLite, thai2fit — ไม่เพิ่ม dependency อื่นที่ไม่จำเป็น |

## 3. Architecture / Data Flow

```
login (1 ครั้ง, headed browser, บันทึก storage state)
  → monitor loop (ทุก 30 นาที, ดึงโพสต์หน้าแรก ~50 โพสต์)
  → SQLite (dedupe ด้วย post_id)
  → digest (keyword/engagement analysis) → reports/*.md
```

## 4. Components (files)

| File | หน้าที่ |
|---|---|
| `cli.py` | Entry point: `login` / `monitor [--once]` / `digest [--days N]` |
| `fetch.py` | Playwright เปิดหน้ากลุ่ม, scroll, parse โพสต์ — **selector ของ FB รวมอยู่ใน dict เดียวในไฟล์นี้** (DOM FB เปลี่ยนบ่อย แก้จุดเดียวจบ) |
| `store.py` | SQLite: schema, upsert, query ตามช่วงวัน, dedupe ด้วย post_id |
| `digest.py` | thai2fit แยกคำไทย → top keywords, top posters, top posts โดย engagement → Markdown |
| `config.toml` | ข้อมูลกลุ่ม, ระยะเวลารัน, ค่า digest |
| `tests/` | Parser test (จาก HTML fixture), dedupe test, digest test |
| `data/` | `sl.db`, `auth/` (storage state) — gitignore |
| `reports/` | Digest Markdown ที่สร้างแล้ว — commit ได้ |

## 5. Data Model

ตาราง `posts` (SQLite):

| Column | Type | หมายเหตุ |
|---|---|---|
| `post_id` | TEXT PK | stable id จาก DOM (fallback: hash ของ permalink) |
| `group_id` | TEXT | index, รองรับหลายกลุ่ม |
| `poster_name` | TEXT | |
| `body` | TEXT | |
| `created_at` | TEXT | ISO 8601, ตามที่ FB แสดง |
| `fetched_at` | TEXT | ISO 8601, เวลาที่เราดึง |
| `reaction_count` | INTEGER | |
| `comment_count` | INTEGER | |
| `permalink` | TEXT | |

Index: `(group_id, created_at)`

## 6. CLI Contract

```
python cli.py login    [--group <url>]   # headed, ล็อกอินเอง, เก็บ storage state
python cli.py monitor  [--once]          # --once: ดึงครั้งเดียวจบ (ใช้ทดสอบ/รันมือ)
python cli.py digest   [--days 7]        # สร้าง reports/<date>.md
```

- `monitor` โดยไม่มี `--once` = loop ตาม `interval_minutes` ใน config
- digest ออกผลเป็นไฟล์ + พิมพ์สรุปสั้นๆ ใน terminal

## 7. Config (`config.toml`)

```toml
[[groups]]
name = "กลุ่มตัวอย่าง"
url  = "https://www.facebook.com/groups/..."

[monitor]
interval_minutes = 30
pages_per_run    = 1        # จำนวนหน้า scroll ต่อรอบ (1 = ~50 โพสต์)

[digest]
top_n_keywords = 15
top_n_posts    = 10
```

เพิ่มกลุ่ม = เพิ่ม `[[groups]]` block — โครงสร้าง code รองรับแล้ว,
แต่ยังไม่ทดสอบ multi-group ใน phase นี้ (v1 รันกลุ่มแรกใน list)

## 8. Digest Content

1. ช่วงเวลา + จำนวนโพสต์ทั้งหมดใน archive / ในช่วง
2. Top keywords (thai2fit tokenization, ตัด stopword ไทย+อังกฤษ,
   แสดง count + % ต่อโพสต์)
3. Top posters (โพสต์มากสุด)
4. Top posts โดย engagement (reactions + comments) พร้อม permalink
5. โพสต์ล่าสุด `top_n_posts` รายการ (ใช้ค่าเดียวกับ config `[digest].top_n_posts`)

## 9. Error Handling & Risks

- **DOM ของ FB เปลี่ยน** → selector รวมใน `fetch.py` เท่านั้น;
  parser ต้อง fail loudly (throw + ข้อความชัด) ไม่ใช่ parse ได้แต่ได้ข้อมูลผิดเงียบๆ
- **Session หมดอายุ** → monitor ตรวจหน้า login, ถ้าเจอ log ชัดแจ้งให้
  รัน `login` ใหม่, loop หยุด (ไม่ retry บังคับ)
- **บัญชีถูก flag** → ความถี่ต่ำ (30 นาที/รอบ, 1 หน้า/รอบ, ไม่ click เพิ่ม);
  ความเสี่ยงลดแล้วแต่ไม่ศูนย์ — ยอมรับโดยแจ้งผู้ใช้แล้ว
- **Rate limit / CAPTCHA** → retry 1 ครั้งหลังพัก 5 นาที, ยังไม่ได้ → หยุดรอบ, รอบถัดไปต่อเอง
- **โพสต์ที่ดึงซ้ำ** → dedupe ด้วย post_id (upsert)

## 10. Testing

- `tests/test_parse.py` — feed HTML fixture (บันทึกจริงจากหน้ากลุ่ม 1 ชุด) →
  assert fields ทุกคอลัมน์
- `tests/test_store.py` — insert ซ้ำ post_id เดิม → count ไม่เพิ่ม
- `tests/test_digest.py` — โพสต์ตัวอย่าง ~20 โพสต์ → digest มี top keyword ที่ถูกต้อง
- รัน test: `python -m pytest`

## 11. Phase 2 (out of scope, ไม่ทำใน spec นี้)

- Web dashboard (charts, ค้นหา)
- เก็บเนื้อหา comment
- Semantic analysis ด้วย LLM (digest v1 เป็น keyword-based)
- รัน multi-group พร้อมกัน
