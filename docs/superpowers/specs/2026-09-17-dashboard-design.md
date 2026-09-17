# Social Listening Dashboard — Design Spec

Date: 2026-09-17 · Status: approved (in-chat) · Approach: B (FastAPI + Next.js)

## 1. Background

Pipeline ดึงโพสต์ Facebook Group → SQLite (`data/sl.db`) เสร็จแล้ว (fetch/store/digest/monitor,
auto-refresh ทุก 30 นาที) งานนี้เพิ่มชั้นให้คนดู: dashboard ส่วนตัวรันบนเครื่องนี้
(localhost เท่านั้น, ไม่มี auth) เห็นเทรนด์เร็วกว่า + ค้นหาโพสต์ + ดู full text

## 2. Scope

**v1 (spec นี้):**
- Trends: top keywords, top posters, top posts by engagement, จำนวนโพสต์ใหม่ 24 ชม., เวลา fetch ล่าสุด
- Post list: ค้นหา keyword (LIKE `body`), filter poster + ช่วงวันที่, sort date/engagement, pagination
- Post detail: full text, engagement, keyword chips, ปุ่มเปิด permalink
- Auto-refresh ทุก 60 วินาที

**เพิ่มทีหลัง (ไม่ทำใน v1):**
- Alert เมื่อ keyword ที่ watch ปรากฏ
- Sentiment analysis
- เปรียบเทียบคู่แข่ง
- Multi-group (schema รองรับอยู่แล้ว via `group_id`, API รับ param, UI v1 ใช้ `groups[0]` จาก config)
- Deploy ออกนอกเครื่อง / auth

## 3. Architecture

```
monitor (30 นาที) → data/sl.db → api.py (FastAPI :8000) → browser (Next.js :3000, poll 60s)
```

- `api.py` — ไฟล์เดียว (~120 บรรทัด), FastAPI, เปิด sqlite3 connection ใหม่ต่อ request
  (กันปัญหา cross-thread + file lock), read-only ทุก endpoint
- CORS middleware 1 บรรทัด อนุญาต `http://localhost:3000` — browser fetch API ตรง
  ไม่ผ่าน proxy
- `dashboard/` — Next.js 15 App Router + TypeScript + Tailwind, อยู่ใน repo เดียวกัน
  ไม่ใช้ component library / chart library (bars ใช้ CSS)
- Thai fonts: ใช้ system fonts (Windows มี Thai fonts ครบ) — ไม่ embed font

## 4. Data model change (store.py)

- เพิ่ม column `keywords TEXT` (JSON array of str) ที่ `posts`
- migration ตาม pattern เดิมใน `init_db` (ALTER TABLE ถ้ายังไม่มี)
- `upsert_posts` คำนวณ `json.dumps(set(digest._tokens(body)))` per post
  (reuse tokenizer ที่ calibrate แล้ว — ไม่ทำ Thai tokenization ฝั่ง JS)
- row เดิมที่ migrate มา: `keywords` เป็น NULL → API/aggregate ต้องทน NULL

## 5. API (api.py)

Base: `http://localhost:8000` · ทุก response JSON · error = HTTP status + `{"detail": ...}`

### GET /health
```json
{"ok": true, "last_fetched": "2026-09-17T07:29:56+00:00"}
```

### GET /posts
Params:
| param | type | default | note |
|---|---|---|---|
| q | str | — | `body LIKE %q%` (SQLite LIKE) |
| poster | str | — | `poster_name LIKE %poster%` |
| since / until | ISO date | — | เปรียบ `created_at` · `created_at` NULL ถูกนับในเสมอ (สอดคล้อง `fetch_recent`) |
| sort | `date`\|`engagement` | `date` | engagement = reaction+comment+share |
| limit / offset | int | 50 / 0 | limit max 200 |
| group_id | str | `groups[0]` จาก config | |

Response:
```json
{"total": 42, "posts": [{"post_id": "...", "group_id": "...", "poster_name": "...",
  "body": "...", "created_at": "...", "fetched_at": "...",
  "reaction_count": 0, "comment_count": 0, "share_count": 0,
  "permalink": "...", "keywords": ["..."] }]}
```

### GET /posts/{post_id}
Param `group_id` (default `groups[0]`) — 404 ถ้าไม่มี · body = object เดียว

### GET /stats
Params: `days` (default 7, max 90), `group_id` (default `groups[0]`)

Window = `created_at >= now - days` (post ที่ `created_at` NULL นับใน —
สอดคล้อง `fetch_recent` · ponytail: created_at NULL เป็น minority, เดี๋ยวเต็มเอง)

```json
{"days": 7, "total_posts": 42, "new_since_yesterday": 5, "last_fetched": "...",
 "top_keywords": [{"word": "ลดราคา", "count": 8, "pct": 0.19}],
 "top_posters": [{"name": "สมชาย", "count": 9}],
 "top_posts": [{"post_id": "...", "poster_name": "...", "snippet": "...120 chars...",
   "created_at": "...", "engagement": 12, "permalink": "..."}]}
```
- top_keywords 15 · top_posters 10 · top_posts 10 (sort engagement desc)
- keyword count: 1 ครั้ง/โพสต์ (dedupe — สอดคล้อง digest) · keywords NULL = ไม่ count

## 6. Frontend (dashboard/)

Files (~8):
- `app/layout.tsx` — nav "Trends | Posts" + group name
- `app/page.tsx` — shell → `components/Trends.tsx` (client)
- `app/posts/page.tsx` — shell → `components/PostList.tsx` (client: filter bar + ตาราง + pagination)
- `app/posts/[id]/page.tsx` — shell → `components/PostDetail.tsx` (client)
- `lib/api.ts` — base URL จาก `process.env.API_URL ?? "http://localhost:8000"` + typed fetch helpers
- `lib/usePoll.ts` — `usePoll(url, 60_000)` → {data, error, stale}
- `components/Trends.tsx`, `PostList.tsx`, `PostDetail.tsx`

พฤติกรรม:
- ทุก 60 วิ refetch (ใช้ `usePoll`) · ระหว่าง stale แสดงข้อมูลเดิม + badge "ล่าสุด HH:MM"
- API ตอบ 503 → banner "DB occupied กำลัง retry" (ข้อมูลเดิมยังแสดงอยู่)
- fetch พัง (API ปิด) → banner "เชื่อมต่อ API ไม่ได้ — รัน `python -m uvicorn api:app`"
- DB ว่าง → zero-state ทุก view ("ยังไม่มีโพสต์ใน range นี้")
- ตาราง: คอลัมน์ เวลา · poster · snippet (120 ตัว) · R/C/S · engagement · เปิด (link detail)

## 7. Error handling (สรุป)

| สถานการณ์ | behavior |
|---|---|
| DB locked ตอน monitor เขียน | `sqlite3.connect(timeout=5)` → พังจริง = 503 + `{"detail":"db busy"}` |
| API ปิด | UI banner (ข้อ 6) |
| param พัง (pydantic) | 422 |
| post_id ไม่พบ | 404 |
| `created_at` / `keywords` NULL | นับใน window · skip keyword count · UI แสดง `—` |

## 8. Testing

Python (pytest, 1 runnable check):
- `tests/test_api.py` — FastAPI `TestClient` + temp DB:
  - `/posts` filter q / poster / since / sort / pagination
  - `/posts/{id}` found + 404
  - `/stats` window + keyword dedupe + NULL keywords
  - `/health`
- `tests/test_store.py` +1 — `upsert_posts` populate `keywords` (JSON, dedupe)

JS: ไม่ตั้ง test suite (logic ฝั่ง client = formatting + polling เท่านั้น) —
verify e2e ใน browser ตอนจบ (chrome-devtools: 3 pages + poll + error banner)

## 9. Running

```powershell
# terminal 1 (monitor อยู่แล้ว)
.venv\Scripts\python -m uvicorn api:app --port 8000
# terminal 2
cd dashboard; npm run dev   # → http://localhost:3000
```
dep ใหม่: Python `fastapi` + `uvicorn` (เข้า venv เดิม) · Node: `create-next-app` (TS + Tailwind)
README เพิ่ม section "Dashboard" 2 บรรทัดนี้

## 10. Non-goals

ดูข้อ 2 "เพิ่มทีหลัง" · ไม่ทำ auth/deploy · ไม่ทำ realtime (websocket) · ไม่แตะ fetch.py/cli.py
