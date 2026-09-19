from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import tomllib
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from store import fetch_recent, init_db

# Asia/Bangkok — UTC+7 ไม่เปลี่ยน DST (หยุดใช้ 1978) → fixed offset ถูกถาวร
BKK = timezone(timedelta(hours=7))

# ponytail: SL_DB env สำหรับ test — default คือ db ของระบบ
DB = Path(os.environ.get("SL_DB", "data/sl.db"))
init_db(DB)  # สร้างตารางถ้ายังไม่มี (ตอน import) — DB ว่าง = zero state ไม่ใช่ 500

app = FastAPI(title="social-listening")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# S8415 — document HTTPException ที่แต่ละ route raise ได้
R_500 = {500: {"description": "no group id in config url"}}
R_503 = {503: {"description": "db busy"}}
R_ERR = {**R_500, **R_503}
R_NOT_FOUND = {404: {"description": "post not found"}, **R_ERR}


def _gid_from_url(url: str) -> str:
    # pattern เดียวกับ fetch.group_id_from_url — ไม่ import fetch เพราะลาก playwright มาด้วย
    m = re.search(r"/groups/([0-9A-Za-z._-]+)", url)
    if not m:
        raise HTTPException(500, f"no group id in config url: {url}")
    return m.group(1)


def _group_info(gid: str | None) -> tuple[str, str]:
    """(name, group_id) จาก config.toml — ไม่ส่ง gid = groups[0] · gid อื่นที่ไม่ได้อยู่ใน config ใช้ตามนั้น (schema รองรับ)"""
    with open("config.toml", "rb") as f:
        groups = tomllib.load(f)["groups"]
    if gid is None:
        g = groups[0]
        return g.get("name", "group"), _gid_from_url(g["url"])
    for g in groups:
        if _gid_from_url(g["url"]) == gid:
            return g.get("name", gid), gid
    return "group", gid


def _all_groups() -> list[tuple[str, str]]:
    """(name, group_id) ทุกกลุ่มใน config.toml — สำหรับ compare"""
    with open("config.toml", "rb") as f:
        groups = tomllib.load(f)["groups"]
    out = []
    for g in groups:
        gid = _gid_from_url(g["url"])
        out.append((g.get("name", gid), gid))
    return out


def _poster_influence(rows: list[dict]) -> list[tuple[str, int, float]]:
    """[(name, count, avg_engagement)] เรียงตาม avg engagement ต่อโพสต์ (influence) — tie → count มากก่อน"""
    agg: dict[str, list] = {}
    for r in rows:
        e = (r["reaction_count"] or 0) + (r["comment_count"] or 0) + (r["share_count"] or 0)
        a = agg.setdefault(r["poster_name"] or "?", [0, 0])
        a[0] += 1
        a[1] += e
    ranked = sorted(agg.items(), key=lambda kv: (-(kv[1][1] / kv[1][0]), -kv[1][0]))
    return [(n, c, round(t / c, 2)) for n, (c, t) in ranked[:10]]


@app.get("/groups", responses=R_500)
def groups():
    return {"groups": [{"name": n, "group_id": g} for n, g in _all_groups()]}


@contextmanager
def _ro():
    # connection ใหม่ต่อ request (กัน cross-thread) · timeout=5 → DB busy = 503 (spec §7)
    conn = None
    try:
        conn = sqlite3.connect(str(DB), timeout=5)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.OperationalError as e:
        raise HTTPException(503, "db busy") from e
    finally:
        if conn:
            conn.close()


def _row_to_post(r) -> dict:
    return {
        "post_id": r["post_id"],
        "group_id": r["group_id"],
        "poster_name": r["poster_name"],
        "body": r["body"],
        "created_at": r["created_at"],
        "fetched_at": r["fetched_at"],
        "reaction_count": r["reaction_count"] or 0,
        "comment_count": r["comment_count"] or 0,
        "share_count": r["share_count"] or 0,
        "permalink": r["permalink"],
        "keywords": json.loads(r["keywords"]) if r["keywords"] else [],
        "sentiment": r["sentiment"],
        "summary": r["summary"],
    }


@app.get("/health", responses=R_503)
def health():
    with _ro() as conn:
        row = conn.execute("SELECT MAX(fetched_at) FROM posts").fetchone()
    return {"ok": True, "last_fetched": row[0]}


def _posts_where(gid: str, q: str | None, poster: str | None,
                 since: str | None, until: str | None, sort: str) -> tuple[str, list, str]:
    """(where_sql, params, order) — /posts กับ /export ใช้ filter เดียวกัน"""
    where, params = ["group_id = ?"], [gid]
    if q:
        where.append("body LIKE ?")
        params.append(f"%{q}%")
    if poster:
        where.append("poster_name LIKE ?")
        params.append(f"%{poster}%")
    if since:
        where.append("(created_at IS NULL OR created_at >= ?)")
        params.append(since)
    if until:
        where.append("(created_at IS NULL OR created_at <= ?)")
        params.append(until)
    if sort == "engagement":
        order = ("(COALESCE(reaction_count,0)+COALESCE(comment_count,0)"
                 "+COALESCE(share_count,0)) DESC, created_at DESC")
    else:
        order = "created_at DESC"
    return " AND ".join(where), params, order


@app.get("/posts", responses=R_ERR)
def list_posts(
    q: str | None = None,
    poster: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort: str = Query("date", pattern="^(date|engagement)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    group_id: str | None = None,
):
    _, gid = _group_info(group_id)
    where_sql, params, order = _posts_where(gid, q, poster, since, until, sort)
    with _ro() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM posts WHERE {where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM posts WHERE {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
    return {"total": total, "posts": [_row_to_post(r) for r in rows]}


@app.get("/export", responses=R_ERR)
def export_csv(
    q: str | None = None,
    poster: str | None = None,
    sort: str = Query("date", pattern="^(date|engagement)$"),
    group_id: str | None = None,
):
    """CSV ทุกแถวที่ match filter UI — BOM (utf-8-sig) ให้ Excel เปิดไทยไม่เพี้ยน"""
    _, gid = _group_info(group_id)
    where_sql, params, order = _posts_where(gid, q, poster, None, None, sort)
    with _ro() as conn:
        rows = conn.execute(
            f"SELECT * FROM posts WHERE {where_sql} ORDER BY {order}", params).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["post_id", "created_at", "poster_name", "body", "permalink",
                "reactions", "comments", "shares", "sentiment", "summary", "keywords"])
    for r in rows:
        kws = json.loads(r["keywords"]) if r["keywords"] else []
        w.writerow([r["post_id"], r["created_at"], r["poster_name"], r["body"],
                    r["permalink"], r["reaction_count"] or 0, r["comment_count"] or 0,
                    r["share_count"] or 0, r["sentiment"] or "", r["summary"] or "",
                    "; ".join(kws)])
    return Response(
        content=b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="posts-{datetime.now():%Y-%m-%d}.csv"'},
    )


@app.get("/posts/{post_id}", responses=R_NOT_FOUND)
def get_post(post_id: str, group_id: str | None = None):
    _, gid = _group_info(group_id)
    with _ro() as conn:
        r = conn.execute("SELECT * FROM posts WHERE post_id=? AND group_id=?",
                         (post_id, gid)).fetchone()
    if not r:
        raise HTTPException(404, "post not found")
    return _row_to_post(r)


@app.get("/stats", responses=R_ERR)
def stats(days: int = Query(7, ge=1, le=90), group_id: str | None = None):
    name, gid = _group_info(group_id)
    now = datetime.now(timezone.utc)
    with _ro() as conn:
        rows = fetch_recent(conn, gid, (now - timedelta(days=days)).isoformat())
        new24 = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE group_id=? AND"
            " (created_at IS NULL OR created_at >= ?)",
            (gid, (now - timedelta(days=1)).isoformat())).fetchone()[0]
        last = conn.execute("SELECT MAX(fetched_at) FROM posts").fetchone()[0]
    # fetch_recent return list[dict] — r["col"] ได้เลย
    kw: Counter = Counter()
    sent: Counter = Counter()
    for r in rows:
        if r["keywords"]:  # NULL (row ก่อน migration) = skip
            kw.update(json.loads(r["keywords"]))
        sent[r["sentiment"] or "unanalyzed"] += 1  # NULL = ยังไม่ได้วิเคราะห์
    total = len(rows)
    return {
        "group": name,
        "days": days,
        "total_posts": total,
        "new_since_yesterday": new24,
        "last_fetched": last,
        "sentiment": [
            # 4 entries เสมอ — total=0 (window ว่าง) → count/pct 0 ทั้งหมด ไม่ crash
            {"label": lab, "count": sent[lab],
             "pct": sent[lab] / total if total else 0.0}
            for lab in ("positive", "neutral", "negative", "unanalyzed")
        ],
        "top_keywords": [
            {"word": w, "count": c, "pct": c / total} for w, c in kw.most_common(15)
        ],
        "top_posters": [
            {"name": n, "count": c, "avg_engagement": avg}
            for n, c, avg in _poster_influence(rows)
        ],
        "top_posts": [
            {
                "post_id": r["post_id"],
                "poster_name": r["poster_name"],
                "snippet": " ".join((r["body"] or "").split())[:120],
                "created_at": r["created_at"],
                "engagement": (r["reaction_count"] or 0) + (r["comment_count"] or 0)
                              + (r["share_count"] or 0),
                "permalink": r["permalink"],
            }
            for r in sorted(rows, key=lambda r: (r["reaction_count"] or 0)
                            + (r["comment_count"] or 0) + (r["share_count"] or 0),
                            reverse=True)[:10]
        ],
    }


def _compare_block(name: str, gid: str, rows: list[dict],
                   since: datetime, now: datetime, total: int) -> dict:
    n = len(rows)
    kw: Counter = Counter()
    first_kw: Counter = Counter()   # ครึ่งแรกของ window
    second_kw: Counter = Counter()  # ครึ่งหลัง
    mid = since + (now - since) / 2
    n_first = 0
    eng = 0
    for r in rows:
        eng += (r["reaction_count"] or 0) + (r["comment_count"] or 0) + (r["share_count"] or 0)
        kws = json.loads(r["keywords"]) if r["keywords"] else []
        kw.update(kws)
        half = first_kw if datetime.fromisoformat(r["created_at"] or r["fetched_at"]) < mid else second_kw
        half.update(kws)
        n_first += half is first_kw
    words = sorted(set(first_kw) | set(second_kw), key=lambda w: -(first_kw[w] + second_kw[w]))[:10]
    return {
        "name": name,
        "group_id": gid,
        "sample_size": n,
        "share_of_voice": n / total if total else 0.0,
        "avg_engagement": round(eng / n, 2) if n else 0.0,
        "top_keywords": [{"word": w, "count": c, "pct": c / n}
                         for w, c in kw.most_common(5)] if n else [],
        "keyword_delta": {
            "sample_size": {"first_half": n_first, "second_half": n - n_first},
            "items": [{"word": w, "first_half": first_kw[w], "second_half": second_kw[w]}
                      for w in words],
        },
    }


@app.get("/stats/compare", responses=R_ERR)
def stats_compare(days: int = Query(7, ge=1, le=90)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    with _ro() as conn:
        raw = [(name, gid, fetch_recent(conn, gid, since.isoformat()))
               for name, gid in _all_groups()]
    total = sum(len(rows) for _, _, rows in raw)
    kw_by_group = []
    for _, _, rows in raw:
        c: Counter = Counter()
        for r in rows:
            if r["keywords"]:
                c.update(json.loads(r["keywords"]))
        kw_by_group.append(c)
    presence: Counter = Counter()
    totals: Counter = Counter()
    for c in kw_by_group:
        for w, n in c.items():
            presence[w] += 1
            totals[w] += n
    shared = []
    for w in sorted(presence, key=lambda w: (-presence[w], -totals[w])):
        if presence[w] < 2:
            break
        shared.append({"word": w, "count": totals[w], "in_groups": presence[w]})
        if len(shared) == 10:
            break
    return {
        "days": days,
        "total_posts": total,
        "groups": [_compare_block(name, gid, rows, since, now, total)
                   for name, gid, rows in raw],
        "shared_keywords": shared,
    }


def _ago(iso: str | None) -> str:
    """ISO UTC → Thai time-ago — 1 string ที่ใช้ทั้ง /summary และ frontend badge"""
    if not iso:
        return "—"
    mins = max(0, int((datetime.now(timezone.utc)
                       - datetime.fromisoformat(iso)).total_seconds() // 60))
    if mins < 60:
        return f"{mins} นาทีที่แล้ว"
    if mins < 60 * 24:
        return f"{mins // 60} ชม.ที่แล้ว"
    return f"{mins // 60 // 24} วันที่แล้ว"


@app.get("/summary", responses=R_ERR)
def summary(days: int = Query(7, ge=1, le=90)):
    # rule-based "สรุปวันนี้" — ประโยคสำเร็จรูป + severity, ไร้ LLM (spec item 4)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    with _ro() as conn:
        last = conn.execute("SELECT MAX(fetched_at) FROM posts").fetchone()[0]
        last_analyzed = conn.execute(
            "SELECT MAX(created_at) FROM posts WHERE sentiment IS NOT NULL").fetchone()[0]
        oldest_pending = conn.execute(
            "SELECT MIN(created_at) FROM posts WHERE sentiment IS NULL").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE sentiment IS NULL").fetchone()[0]
        raw = [(name, gid, fetch_recent(conn, gid, since.isoformat()))
               for name, gid in _all_groups()]

    items: list[dict] = []
    # 1) monitor freshness — last_fetched เด่นสุด (item 3)
    if last is None:
        items.append({"type": "system", "severity": "alert",
                      "text": "🔴 ยังไม่มีข้อมูลในระบบ — monitor ยังไม่ได้ run", "href": None})
    else:
        age = (now - datetime.fromisoformat(last)).total_seconds()
        if age <= 3600:
            items.append({"type": "system", "severity": "ok",
                          "text": f"✅ ระบบทำงานปกติ อัปเดตล่าสุด {_ago(last)}", "href": None})
        elif age <= 86400:
            items.append({"type": "system", "severity": "warn",
                          "text": f"🟡 Monitor ไม่ได้อัปเดต {_ago(last)} — ควรเช็ค", "href": None})
        else:
            items.append({"type": "system", "severity": "alert",
                          "text": f"🔴 Monitor หยุดอัปเดต {_ago(last)}", "href": None})

    win = "สัปดาห์นี้" if days == 7 else f"ในช่วง {days} วันล่าสุด"
    mid = since + (now - since) / 2
    for name, gid, rows in raw:
        # 2) โพสต์เชิงลบ — รวม theme, top 3 themes, href = permalink engagement สูงสุด
        by_theme: dict[str, list[dict]] = {}
        for r in rows:
            if r["sentiment"] == "negative":
                by_theme.setdefault(r["theme"] or "other", []).append(r)
        for theme, posts in sorted(by_theme.items(), key=lambda kv: -len(kv[1]))[:3]:
            top = max(posts, key=lambda r: (r["reaction_count"] or 0)
                      + (r["comment_count"] or 0) + (r["share_count"] or 0))
            items.append({"type": "negative", "severity": "high",
                          "text": f"🔴 {name}: มี {len(posts)} โพสต์เชิงลบเกี่ยวกับ "
                                  f"{theme} — ควรเข้าไปดู",
                          "href": top["permalink"]})
        # 3) keyword พุ่ง — half-window (สูตรเดียวกับ _compare_block): ครึ่งหลัง ≥3 ครั้ง และ ≥2× ครึ่งแรก
        first_kw: Counter = Counter()
        second_kw: Counter = Counter()
        for r in rows:
            kws = json.loads(r["keywords"]) if r["keywords"] else []
            half = first_kw if datetime.fromisoformat(
                r["created_at"] or r["fetched_at"]) < mid else second_kw
            half.update(kws)
        for w, s in second_kw.most_common(15):
            f = first_kw[w]
            if s < 3 or s < 2 * f:
                continue
            if f:
                text = f"📈 {name}: '{w}' ถูกพูดถึงเพิ่มขึ้น {round((s - f) / f * 100)}% {win}"
            else:
                text = f"📈 {name}: '{w}' เป็นคำใหม่ที่กำลังร้อน ({s} ครั้ง)"
            items.append({"type": "keyword", "severity": "info", "text": text, "href": None})

    # 4) AI สถานะ — DB-only (API process แยกจาก monitor) · grace 1h สำหรับโพสต์ใหม่ระหว่างรอบ
    if pending and oldest_pending and \
            (now - datetime.fromisoformat(oldest_pending)).total_seconds() > 3600:
        if last_analyzed is None:
            items.append({"type": "ai", "severity": "warn",
                          "text": f"⚠️ AI วิเคราะห์อารมณ์ยังไม่เคย run — "
                                  f"มี {pending} โพสต์รอวิเคราะห์", "href": None})
        elif (now - datetime.fromisoformat(last_analyzed)).total_seconds() > 86400:
            items.append({"type": "ai", "severity": "warn",
                          "text": f"⚠️ AI วิเคราะห์อารมณ์หยุดทำงาน {_ago(last_analyzed)} — "
                                  f"มี {pending} โพสต์รอวิเคราะห์", "href": None})
        else:
            items.append({"type": "ai", "severity": "info",
                          "text": f"ℹ️ มี {pending} โพสต์ยังไม่ได้วิเคราะห์", "href": None})

    return {"days": days, "last_fetched": last, "items": items}


@app.get("/stats/timeline", responses=R_ERR)
def stats_timeline(days: int = Query(30, ge=1, le=90), group_id: str | None = None):
    name, gid = _group_info(group_id)
    now = datetime.now(timezone.utc)
    with _ro() as conn:
        rows = fetch_recent(conn, gid, (now - timedelta(days=days)).isoformat())
    today0 = now.astimezone(BKK).replace(hour=0, minute=0, second=0, microsecond=0)
    # ponytail: buckets = days วันล่าสุดของ BKK — โพสต์ช่วง ~1 วันแรกของ window อาจหลุด
    # เมื่อ BKK ล่วงหน้า UTC (UTC หลัง 17:00) — ยอมรับได้สำหรับ trend
    buckets: dict = {}
    for i in range(days):
        d = (today0 - timedelta(days=days - 1 - i)).date()
        buckets[d] = {"date": d.isoformat(), "posts": 0, "engagement": 0, "top_keyword": None}
    kw_by_day: dict = {}
    for r in rows:
        d = datetime.fromisoformat(r["created_at"] or r["fetched_at"]).astimezone(BKK).date()
        if d not in buckets:
            continue
        b = buckets[d]
        b["posts"] += 1
        b["engagement"] += ((r["reaction_count"] or 0) + (r["comment_count"] or 0)
                            + (r["share_count"] or 0))
        if r["keywords"]:
            kw_by_day.setdefault(d, Counter()).update(json.loads(r["keywords"]))
    for d, c in kw_by_day.items():
        if c:
            buckets[d]["top_keyword"] = c.most_common(1)[0][0]
    return {
        "group": name,
        "days": days,
        "timezone": "Asia/Bangkok",
        "buckets": [buckets[d] for d in sorted(buckets)],
    }
