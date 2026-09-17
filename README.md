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

## Dashboard (UI)

ต้องมี data ใน `data/sl.db` (รัน `monitor` แล้ว) — terminal 2 ตัว:

    .venv\Scripts\python -m uvicorn api:app --port 8000
    cd dashboard; npm run dev        # → http://localhost:3000

## Notes

- ถ้า Facebook เปลี่ยนหน้าเว็บ ให้แก้ selector ใน `fetch.py` (dict `SELECTORS` + regex)
  ใช้ `cli.py capture` เพื่อบันทึก HTML จริงมา debug
- Session หมด → รัน `login` ใหม่
- รันเบาๆ: 30 นาที/รอบ, 1 หน้า/รอบ — เพื่อลดความเสี่ยงบัญชีถูก flag
