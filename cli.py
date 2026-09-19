from __future__ import annotations

import argparse
import sys
import time
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alerts import check_alerts
from digest import build_digest
from fetch import SessionExpired, capture_feed_html, fetch_group_posts, group_id_from_url, login
from sentiment import analyze_text, get_provider, load_dotenv
from store import fetch_recent, init_db, pending_sentiment, save_sentiment, upsert_comments, upsert_posts

DATA = Path("data")
DB = DATA / "sl.db"

def _config() -> dict:
    with open("config.toml", "rb") as f:
        return tomllib.load(f)

def _fetch_with_retry(group: dict, pages: int, headless: bool) -> list[dict]:
    try:
        return fetch_group_posts(group, pages=pages, headless=headless)
    except Exception as e:  # network/DOM error ทั้งหมดพักแล้วลองใหม่
        print(f"fetch failed: {e} — retry in 5 min")
        time.sleep(300)
        return fetch_group_posts(group, pages=pages, headless=headless)  # ล้มอีก = throw ให้ caller

def cmd_login(cfg: dict, args) -> int:
    url = args.group or cfg["groups"][0]["url"]
    login(url)
    print("login OK — profile saved to data/browser-profile")
    return 0

def _monitor_group(conn, cfg: dict, group: dict, mon: dict) -> bool:
    """fetch+save 1 กลุ่ม — True = round พัง (SessionExpired ยัง raise ผ่านไปให้ caller)"""
    gid = group_id_from_url(group["url"])
    try:
        posts = _fetch_with_retry(group, mon["pages_per_run"], mon.get("headless", True))
    except SessionExpired:
        raise
    except Exception as e:  # retry พังด้วย → ข้ามกลุ่มนี้ (spec §9)
        print(f"round skipped for {group['name']}: {e}")
        return True
    now = datetime.now(timezone.utc).isoformat()
    upsert_posts(conn, gid, posts, now)
    upsert_comments(conn, gid, posts, now)
    ok = sum(len(p.get("comments") or []) for p in posts)
    failed_c = sum(p.get("comments_seen") or 0 for p in posts) - ok
    print(f"[{now}] fetched {len(posts)} posts for {group['name']}")
    print(f"[{now}] comments: {ok} parsed / {failed_c} failed")
    provider = get_provider()
    if provider is not None:
        pending = pending_sentiment(conn, gid)
        for row in pending:
            save_sentiment(conn, gid, row["post_id"], analyze_text(row["body"], provider))
        if pending:
            print(f"[{now}] analyzed {len(pending)} posts")
    n = check_alerts(conn, gid, group["name"], cfg)
    if n:
        print(f"[{now}] alerts: {n} sent")
    return False

def cmd_monitor(cfg: dict, args) -> int:
    mon = cfg["monitor"]
    conn = init_db(DB)
    while True:
        failed = False
        for group in cfg["groups"]:
            try:
                if _monitor_group(conn, cfg, group, mon):
                    failed = True
            except SessionExpired:
                print("session expired — run: python cli.py login")
                return 1
        if args.once:
            return 1 if failed else 0
        time.sleep(mon["interval_minutes"] * 60)

def cmd_digest(cfg: dict, args) -> int:
    conn = init_db(DB)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    d = cfg["digest"]
    words = cfg.get("watch", {}).get("words", [])  # ไม่มี [watch] = ปิด feature
    for group in cfg["groups"]:
        rows = fetch_recent(conn, group_id_from_url(group["url"]), since)
        md = build_digest(rows, args.days, d["top_n_keywords"], d["top_n_posts"], words)
        out = Path("reports") / f"{group['name']}-{datetime.now():%Y-%m-%d}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(md)
        print(f"\nsaved {out}")
    return 0

def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # entrypoint — ก่อน get_provider() ทุก path (real env ชนะ .env เสมอ)
    p = argparse.ArgumentParser(prog="social-listening")
    sub = p.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("login", help="open browser, log in, save profile")
    lg.add_argument("--group", default=None)

    mo = sub.add_parser("monitor", help="fetch new posts in a loop")
    mo.add_argument("--once", action="store_true", help="single fetch then exit")

    dg = sub.add_parser("digest", help="write markdown report (added in Task 6)")
    dg.add_argument("--days", type=int, default=7)

    cap = sub.add_parser("capture", help="save raw feed HTML for parser debugging")
    cap.add_argument("--group", required=True)
    cap.add_argument("--out", default="data/sample.html")

    sys.stdout.reconfigure(errors="replace")  # console cp874 + ตัวอักษรแปลกในโพสต์ = print พังไม่คุ้ม
    args = p.parse_args(argv)
    cfg = _config()
    if args.cmd == "login":
        return cmd_login(cfg, args)
    if args.cmd == "monitor":
        return cmd_monitor(cfg, args)
    if args.cmd == "digest":
        return cmd_digest(cfg, args)  # Task 6
    if args.cmd == "capture":
        capture_feed_html(args.group, out_path=Path(args.out))
        print(f"saved {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
