# social-listening

ระบบเฝ้าดูโพสต์ใน Facebook Group หลายกลุ่มพร้อมกัน — scrape ด้วย Playwright → เก็บลง SQLite → วิเคราะห์ sentiment ด้วย LLM → ใช้งาน 3 ทาง: **Markdown digest**, **Dashboard (FastAPI + Next.js)**, และ **แจ้งเตือน Discord อัตโนมัติ**

## ภาพรวมระบบ (Data Flow)

```
FB Groups (config.toml)
      │  cli.py monitor  (Playwright + shared browser profile, headless)
      ▼
  data/sl.db  (SQLite: posts + comments + alerts, แยกตาม group_id)
      │
      ├─► digest.py      → reports/<group>-<date>.md  (สรุปกระแส + brand mentions)
      ├─► api.py         → FastAPI :8000  →  dashboard/ (Next.js :3000)  ดู/กรอง/เทียบ/ส่งออก CSV
      └─► alerts.py      → Discord webhook  (negative / brand / high-engagement, dedup + cooldown)
```

ทุกองค์ประกอบอ่าน `config.toml` (รายการกลุ่ม + พารามิเตอร์) และ `.env` (secret: LLM keys, Discord webhook)

---

## 1. ติดตั้ง (Prerequisites + Install)

ต้องการ **Python 3.12+** และ **Node.js 20+** (สำหรับ dashboard)

```bash
# Python
python -m venv .venv
.venv\Scripts\python -m pip install playwright fastapi "uvicorn[standard]" pythainlp pytest
.venv\Scripts\python -m playwright install chromium

# Dashboard (ครั้งเดียว)
cd dashboard
npm install
cd ..
```

> ไม่มี `requirements.txt` — dependency ที่ระบบใช้จริง: `playwright`, `fastapi`, `uvicorn`, `pythainlp` (+ `pytest` สำหรับเทสต์)

## 2. จัดการไฟล์ config

### `config.toml` (คอมมิตได้ — ไม่ใช่ secret)

```toml
[[groups]]                          # เพิ่ม/ลบกลุ่มได้ตามนี้ — ระบบ monitor/digest/API
name = "OMSK PC MARKET"             #   สวมกลุ่มทั้งหมดอัตโนมัติ
url  = "https://www.facebook.com/groups/791806120973629/"

[[groups]]
name = "Extreme IT"
url  = "https://www.facebook.com/groups/2371881352829083/"

[monitor]
interval_minutes = 30               # ระยะเวลาแต่ละรอบ
pages_per_run    = 1                # จำนวนหน้า feed ต่อรอบ (มาก = หนัก/เสี่ยง flag)
headless         = true             # true = ไม่มีหน้าต่าง browser (run ใน background)

[digest]
top_n_keywords = 15                 # คำหลักสูงสุดที่แสดงใน digest
top_n_posts    = 10                 # โพสต์เด่นสูงสุดที่แสดงใน digest

[watch]
words = []                          # คำที่ต้องเฝ้า (brand/product) — ว่าง = ปิดฟีเจอร์
                                    # ใส่อัตโนมัติ: ["RTX", "จอ", "ขาย", ...]

[alerts]
enabled = true
webhook_url = ""                    # ว่าง = ใช้ DISCORD_WEBHOOK_URL จาก .env
rules = ["negative", "brand_mention", "high_engagement"]
min_engagement = 100                # high_engagement ต้องถึงจำนวนนี้ (reaction+comment+share)
cooldown_minutes = 60               # หน่วงเวลาแจ้งเตือน (global ทั้งกลุ่ม — ดูข้อจำกัดท้ายไฟล์)
```

### `.env` (secret — **ห้ามคอมมิต**, มี `.env.example` ให้คัดลอก)

```bash
cp .env.example .env    # แล้วเติมค่า
```

| ตัวแปร | ใช้เมื่อ | หมายเหต |
|---|---|---|
| `SENTIMENT_PROVIDER` | `openai_compatible` หรือ `anthropic` (ว่าง = ไม่วิเคราะห์) | เลือก provider |
| `SENTIMENT_BASE_URL` | provider = `openai_compatible` | เช่น `http://localhost:8080/v1` (llamacpp/Groq/OpenAI) |
| `SENTIMENT_API_KEY` | provider = `openai_compatible` | key ของ endpoint นั้น |
| `ANTHROPIC_API_KEY` | provider = `anthropic` | **ชื่อต่าง**จาก `SENTIMENT_API_KEY` |
| `SENTIMENT_MODEL` | ทั้ง 2 provider | ชื่อ model |
| `DISCORD_WEBHOOK_URL` | alerts | ใช้เมื่อ `webhook_url` ใน config ว่าง |

> Sentiment provider **ไม่มี auto-fallback** — creds ไม่ครบ = โพสต์ถูกเก็บแต่ `sentiment` เป็น NULL (ยังดู/ส่งออกได้ปกติ)

## 3. เริ่มใช้ครั้งแรก (Login)

```bash
.venv\Scripts\python cli.py login
```

- เปิด browser ให้ล็อกอิน Facebook **ครั้งเดียว** — profile ถูกเก็บที่ `data/browser-profile`
- ใช้ profile เดียวร่วมกันทุกกลุ่ม · session หมดเมื่อไหร่ รัน `login` ใหม่

## 4. CLI — การใช้งานหลัก

ทุกคำสั่งรันด้วย interpreter ของ venv:

```bash
# ดึงโพสต์ + วิเคราะห์ sentiment + ส่ง alert ในลูป (ทุก interval_minutes)
.venv\Scripts\python cli.py monitor

# ดึงครั้งเดียวแล้วจบ (ทดสอบ / รันตาม schedule)
.venv\Scripts\python cli.py monitor --once

# สร้าง Markdown digest ล่าสุด (แต่ละกลุ่มได้ไฟล์ 1 ตัว)
.venv\Scripts\python cli.py digest --days 7
.venv\Scripts\python cli.py digest --days 30   # → reports/<กลุ่ม>-<YYYY-MM-DD>.md

# บันทึก HTML feed จริงมา debug parser (เมื่อ FB เปลี่ยนหน้า)
.venv\Scripts\python cli.py capture --group <group_name> --out data/sample.html
```

ลูป `monitor` ทำงานทีละกลุ่ม: fetch → upsert → ดึงคอมเมนต์ → วิเคราะห์ sentiment → ตรวจ alert · กลุ่มไหนพลาดชั่วคราวจะ skip แล้วไปกลุ่มถัดไป (ไม่ทำให้ทั้งรอบพัง)

## 5. Dashboard (UI)

ต้องมีข้อมูลใน `data/sl.db` แล้ว (รัน `monitor` ก่อน)

```bash
.\dev.ps1        # รัน API (:8000) + UI (:3000) พร้อมกัน — Ctrl+C เพื่อหยุดทั้งคู่
```

วิธีรันแยก (ถ้าอยากดู log แยกกัน):

```bash
# เทอร์มินัล 1 — API
.venv\Scripts\python -m uvicorn api:app --port 8000

# เทอร์มินัล 2 — UI
cd dashboard
npm run dev        # → http://localhost:3000
```

| หน้า | URL | เนื้อหา |
|---|---|---|
| Overview | `/` | จำนวนโพสต์ใหม่, sentiment breakdown (pos/neu/neg), top keywords, top posters (ตาม influence), โพสต์เด่น |
| Posts | `/posts` | รายการโพสต์ + กรอง (ค้นคำ / ผู้โพสต์ / ช่วงเวลา / เรียง date หรือ engagement) + ปุ่ม **Export CSV** |
| Post Detail | `/posts/<id>` | เนื้อหาเต็ม, sentiment, สรุป, keywords, ลิงก์ permalink |
| Timeline | `/timeline` | กราฟ posts/engagement ต่อวัน + top keyword ของแต่ละวัน (เลือกกลุ่ม + ช่วงวันได้) |
| Compare | `/compare` | เปรียบเทียบทุกกลุ่ม: share of voice, avg engagement, keyword delta (ครึ่งแรก vs ครึ่งหลัง), shared keywords |

> UI เรียก API ที่ `API_URL` (default `http://localhost:8000`) — เปลี่ยนได้ผ่าน env `API_URL`

## 6. API Reference (FastAPI :8000)

ทุก endpoint รับ `group_id` (ว่าง = กลุ่มแรกของ config) เว้นแต่จะระบุว่าเป็น all-groups · เวลาเป็น UTC, timeline เป็น `Asia/Bangkok`

| Method & Path | พารามิเตอร์ | คำตอบ |
|---|---|---|
| `GET /health` | — | `{ok, last_fetched}` |
| `GET /groups` | — | `{groups:[{name, group_id}]}` ทุกกลุ่มใน config |
| `GET /posts` | `q, poster, since, until, sort=date\|engagement, limit(≤200), offset, group_id` | `{total, posts:[...]}` |
| `GET /posts/{id}` | `group_id` | โพสต์เดียว หรือ 404 |
| `GET /export` | `q, poster, sort, group_id` | CSV attachment (UTF-8 BOM — เปิด Excel ไทยไม่เพี้ยน) |
| `GET /stats` | `days(1–90), group_id` | total, new_since_yesterday, sentiment[], top_keywords[], top_posters[], top_posts[] |
| `GET /stats/compare` | `days(1–90)` | เปรียบเทียบทุกกลุ่ม + shared_keywords |
| `GET /stats/timeline` | `days(1–90), group_id` | buckets ต่อวัน: posts, engagement, top_keyword |

ตัวอย่าง:

```bash
curl "http://localhost:8000/stats?days=30&group_id=791806120973629"
curl "http://localhost:8000/posts?q=RTX&sort=engagement&limit=20"
curl "http://localhost:8000/export?sort=engagement" -o posts.csv
```

## 7. Alert Discord

- เปิด/ปิด + rules ที่ `[alerts]` ใน `config.toml` · webhook จาก config หรือ `DISCORD_WEBHOOK_URL`
- **rules:**
  - `negative` — โพสต์ที่ sentiment = negative
  - `brand_mention` — โพสต์ที่ตรงกับ `[watch] words` (ถ้า `words` ว่าง rule นี้ไม่ fire)
  - `high_engagement` — engagement ≥ `min_engagement`
- **dedup:** แจ้งแต่ละ `(post_id, rule)` แค่ครั้งเดียว (เก็บในตาราง `alerts`)
- **cooldown:** หน่วง `cooldown_minutes` (ดูข้อจำกัดเรื่อง global ใต้หัวข้อ Notes)
- ระบบส่ง request ด้วย User-Agent แบบ browser (กัน Cloudflare block HTTP 1010)

## 8. Watch Words (Brand mentions)

ตั้ง `[watch] words = ["RTX", "จอ", "ขาย"]` แล้ว:
- Digest เพิ่ม section `## Brand mentions` (โพสต์ที่ตรง + แสดงคำว่าตรงอันไหน)
- Alert rule `brand_mention` ทำงาน

การจับคู่: **คำไทย = substring** (จับทุกที่ในข้อความ — อาจ false positive เช่น "จอ" ในคำว่าอื่น) · **คำอังกฤษ/ตัวเลข = word-boundary** (เช่น `AI` ตรง "ใช้AI" แต่ไม่ตรง "AIAInsurance")

## 9. ทดสอบ

```bash
.venv\Scripts\python -m pytest        # 78 tests — ครอบคลุม store/sentiment/digest/alerts/api
```

## 10. โครงสร้างโปรเจกต์

```
cli.py          CLI entry (login / monitor / digest / capture)
fetch.py        Playwright scrape — SELECTORS + regex อยู่ที่นี่ (แก้เมื่อ FB เปลี่ยนหน้า)
store.py        SQLite schema + upsert + queries
sentiment.py    LLM sentiment providers (openai_compatible / anthropic) + .env loader
digest.py       สร้าง Markdown report + brand-mention matching
alerts.py       Discord webhook + dedup + cooldown
api.py          FastAPI endpoints (:8000)
config.toml     กลุ่ม + พารามิเตอร์ (คอมมิตได้)
.env            secret (ห้ามคอมมิต) · .env.example เป็น template
data/sl.db      ฐานข้อมูล (สร้างอัตโนมัติ)
data/browser-profile/  FB session (ห้ามคอมมิต)
reports/        Markdown digest ที่สร้างแล้ว
dashboard/      Next.js UI (:3000)
tests/          pytest suite
```

## 11. เมื่อระบบ "หลุด" / หยุดทำงาน (Troubleshooting)

| อาการ | สาเหตุที่พบบ่อย | แก้ |
|---|---|---|
| monitor หยุด / ไม่มีโพสต์ใหม่ | **Session หมดอายุ** | รัน `cli.py login` ใหม่ |
| FB ไม่ยอมดึง (เลือกโพสต์ไม่พบ) | **FB เปลี่ยนหน้าเว็บ** | แก้ `SELECTORS`/regex ใน `fetch.py` · ใช้ `cli.py capture` เพื่อบันทึก HTML จริงมาเทียบ |
| `sentiment` เป็น NULL หมด | `SENTIMENT_*` ใน `.env` ไม่ครบ / provider ดับ | เติม creds ถูก provider · provider ไม่มี fallback — ครบแล้วถึงทำงาน |
| Dashboard ไม่ขึ้นข้อมูล | API (:8000) ยังไม่รัน / `data/sl.db` ว่าง | รัน uvicorn ก่อน · รัน `monitor` ให้มีข้อมูล |
| API ตอบ 503 `db busy` | DB ถูก lock (monitor กำลังเขียน) | ชั่วคราว — ลองใหม่ / ตรวจสอบว่า monitor ไม่ค้าง |
| Discord ไม่ได้รับ alert | webhook ผิด / cooldown ยังไม่ครบ / rule ไม่ตรง | ตรวจ `DISCORD_WEBHOOK_URL` · rule `brand_mention` ต้องมี `[watch] words` |
| ตัวเลขใน console ยับ (ภาษาไทยเพี้ยน) | console Windows (cp874) | แก้แล้ว — `cli.py` ตั้ง `sys.stdout` เป็น `errors="replace"` แล้ว · ถ้ายังเพี้ยน ให้รันผ่าน terminal ที่ UTF-8 |

**ตรวจสอบระบบว่ายังวิ่งอยู่:**

```bash
.venv\Scripts\python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/health',timeout=5).read().decode())"
# ดูรอบล่าสุด: data/monitor.out.log · DB: SELECT MAX(fetched_at) FROM posts
```

## Notes

- **รันเบาๆ เพื่อความปลอดภัยของบัญชี:** `interval_minutes=30` + `pages_per_run=1` — อย่าเร่งสูงจนเกินไป (เสี่ยงถูก Facebook flag)
- **cooldown alerts เป็น global ทั้งระบบ** (นับจาก `MAX(fired_at)` ร่วมกันทุกกลุ่ม) — ในรอบเดียว กลุ่มที่ fire ก่อนจะทำให้กลุ่มอื่นเงียบไป `cooldown_minutes` · ถ้าต้องการ cooldown แยกกลุ่ม ต้องเพิ่มคอลัมน์ `group_id` ในตาราง `alerts`
- **group เดิม** (44 โพสต์) ยังอยู่ใน DB แต่ไม่ถูก monitor anymore — dashboard/compare จะแสดงเฉพาะกลุ่มใน config ปัจจุบัน
- ระบบออกแบบมาให้ขยายจำนวนกลุ่มได้โดยแก้ `config.toml` อย่างเดียว (API/dashboard/monitor/digest ตามอัตโนมัติ)
