from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from digest import _engagement, _watch_matches
from store import fetch_recent

RULE_COLORS = {"negative": 0xE53E3E, "brand_mention": 0x4287F5, "high_engagement": 0xFAA61A}
RULE_TITLES = {
    "negative": "⚠️ มีคนพูดถึงแบรนด์คุณในแง่ลบ — ลองเข้าไปตอบดู",
    "high_engagement": "🔥 โพสต์นี้ engagement สูง — เหมาะจะตอบกลับหรือดันต่อ",
}


def _post(url: str, payload: dict) -> bool:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 # Cloudflare/Discord บล็อก UA "Python-urllib" (HTTP 1010) → ใช้ UA มาตรฐาน
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except Exception:  # network/429 → ไม่ log, retry รอบ monitor ถัดไป
        return False


def discord_payload(group_name: str, row: dict, rule: str, watch_words=()) -> dict:
    hits = _watch_matches(row["body"] or "", watch_words) if rule == "brand_mention" else []
    title = ("📣 แบรนด์คุณถูกพูดถึง" + (f" ({', '.join(hits)})" if hits else "") + " — เข้าไปตอบขอบคุณได้เลย"
             if rule == "brand_mention" else RULE_TITLES.get(rule, f"{rule} — {group_name}"))
    return {"embeds": [{
        "title": title,
        "description": " ".join((row["body"] or "").split())[:300],
        "url": row.get("permalink") or None,
        "color": RULE_COLORS.get(rule, 0x95A5A6),
        "timestamp": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"name": "กลุ่ม", "value": group_name, "inline": True},
            {"name": "ผู้โพสต์", "value": row.get("poster_name") or "—", "inline": True},
            {"name": "engagement", "value": str(_engagement(row)), "inline": True},
            {"name": "sentiment", "value": row.get("sentiment") or "—", "inline": True},
        ],
    }]}


def evaluate_rules(rows: list[dict], al: dict, watch_words) -> list[tuple[dict, str]]:
    out = []
    min_eng = al.get("min_engagement", 0)
    for row in rows:
        for rule in al.get("rules", []):
            if rule == "negative" and row.get("sentiment") == "negative":
                out.append((row, rule))
            elif rule == "brand_mention" and _watch_matches(row["body"] or "", watch_words):
                out.append((row, rule))
            elif rule == "high_engagement" and _engagement(row) >= min_eng:
                out.append((row, rule))
    return out


def check_alerts(conn, gid: str, group_name: str, cfg: dict) -> int:
    al = cfg.get("alerts") or {}
    url = al.get("webhook_url") or os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not al.get("enabled") or not url:
        return 0
    now = datetime.now(timezone.utc)
    last = conn.execute("SELECT MAX(fired_at) FROM alerts WHERE group_id=?", (gid,)).fetchone()[0]
    if last and now - datetime.fromisoformat(last) < timedelta(minutes=al.get("cooldown_minutes", 60)):
        return 0  # cooldown ต่อกลุ่ม — 1 query, ไม่ใช้ timer state
    words = (cfg.get("watch") or {}).get("words", [])
    sent = 0
    for row, rule in evaluate_rules(fetch_recent(conn, gid, "1970-01-01T00:00:00+00:00"), al, words):
        if conn.execute("SELECT 1 FROM alerts WHERE post_id=? AND rule=?",
                        (row["post_id"], rule)).fetchone():
            continue
        payload = discord_payload(group_name, row, rule, words)
        if not _post(url, payload) and not _post(url, payload):
            continue  # ponytail: ไม่ queue/backoff — 429/พัง = retry รอบหน้า (row ยังไม่ log)
        conn.execute("INSERT INTO alerts (post_id, rule, fired_at, group_id) VALUES (?,?,?,?)",
                     (row["post_id"], rule, now.isoformat(), gid))
        sent += 1
    conn.commit()
    return sent
