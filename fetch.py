from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path("data/browser-profile")
SESSION_WAIT_TIMEOUT_MS = 300_000  # 5 นาทีให้คนล็อกอิน

class SessionExpired(RuntimeError):
    pass

def group_id_from_url(url: str) -> str:
    m = re.search(r"/groups/([0-9A-Za-z._-]+)", url)
    if not m:
        raise ValueError(f"no group id in url: {url}")
    return m.group(1)

def _is_login_url(url: str) -> bool:
    return "login" in url or "checkpoint" in url

def _open(profile_dir: Path, headless: bool):
    profile_dir.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(str(profile_dir), headless=headless)
    return pw, ctx

def login(group_url: str, profile_dir: Path = PROFILE_DIR) -> None:
    pw, ctx = _open(profile_dir, headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(group_url)
        page.wait_for_url(
            lambda u: not _is_login_url(u),
            timeout=SESSION_WAIT_TIMEOUT_MS,
        )
        page.wait_for_load_state("networkidle")
    finally:
        ctx.close()
        pw.stop()

def capture_feed_html(group_url: str, profile_dir: Path = PROFILE_DIR,
                      out_path: Path | None = None, pages: int = 1,
                      headless: bool = True) -> str:
    pw, ctx = _open(profile_dir, headless=headless)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(group_url, wait_until="domcontentloaded")
        if _is_login_url(page.url):
            raise SessionExpired(
                "session not logged in — run: python cli.py login")
        for _ in range(max(1, pages)):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)
        page.wait_for_load_state("networkidle")
        html = page.content()
    finally:
        ctx.close()
        pw.stop()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
    return html
