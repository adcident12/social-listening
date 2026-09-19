"""cli.py — sentiment provider ดับ → streak นับ → Discord alert"""
import pytest

import cli
from cli import _monitor_group
from store import init_db


@pytest.fixture(autouse=True)
def _streak_reset():
    cli._sentiment_fail_streak = 0
    cli._sentiment_alerted = False
    yield


def _cfg(**over):
    al = {"enabled": True, "webhook_url": "https://discord.example/hook",
          "rules": ["negative"], "cooldown_minutes": 60}
    al.update(over)
    return {"alerts": al}


def test_sentiment_streak_alerts_once_at_threshold(monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "_discord_post", lambda url, payload: sent.append(payload) or True)
    cfg = _cfg()
    for n in (2, 2):
        cli._note_sentiment_failures(n, cfg, "2026-09-19T00:00:00+00:00")
        assert not sent  # ยังไม่ถึง threshold
    cli._note_sentiment_failures(1, cfg, "2026-09-19T00:00:00+00:00")
    assert len(sent) == 1  # 5 ติดกัน → ยิง 1 ครั้ง
    assert "sentiment provider" in sent[0]["embeds"][0]["title"]
    cli._note_sentiment_failures(3, cfg, "2026-09-19T01:00:00+00:00")
    assert len(sent) == 1  # incident เดิม — ไม่ยิงซ้ำ
    cli._note_sentiment_failures(0, cfg, "2026-09-19T02:00:00+00:00")  # หาย
    cli._note_sentiment_failures(5, cfg, "2026-09-19T03:00:00+00:00")
    assert len(sent) == 2  # incident ใหม่ → ยิงได้อีก


def test_sentiment_streak_no_webhook_silent(monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "_discord_post", lambda url, payload: sent.append(1) or True)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    cli._note_sentiment_failures(5, {"alerts": {}}, "2026-09-19T00:00:00+00:00")
    assert not sent  # ไม่มี webhook = ไม่ crash, เงียบ


def _monitor_rounds(tmp_path, monkeypatch, rounds=5, provider=None):
    conn = init_db(tmp_path / "t.db")
    posts = [{"post_id": "p1", "poster_name": "A", "body": "สวัสดีครับ",
              "created_at": "2026-09-19T00:00:00+00:00",
              "reaction_count": 0, "comment_count": 0, "permalink": "https://x/p1"}]
    monkeypatch.setattr(cli, "fetch_group_posts", lambda group, pages, headless: posts)
    monkeypatch.setattr(cli, "get_provider", lambda: provider)
    sent = []
    monkeypatch.setattr(cli, "_discord_post", lambda url, payload: sent.append(payload) or True)
    group = {"name": "T", "url": "https://www.facebook.com/groups/1234567890"}
    mon = {"pages_per_run": 1, "headless": True}
    for _ in range(rounds):
        assert _monitor_group(conn, _cfg(), group, mon) is False  # round ไม่พัง
    return conn, sent


class _Down:
    def classify(self, text):
        raise RuntimeError("401 invalid api key")


def test_monitor_group_provider_down_alerts_after_threshold(tmp_path, monkeypatch):
    conn, sent = _monitor_rounds(tmp_path, monkeypatch, provider=_Down())
    assert conn.execute("SELECT sentiment FROM posts WHERE post_id='p1'").fetchone()[0] is None
    assert len(sent) == 1  # 5 รอบ × 1 post NULL = 5 → alert 1 ครั้ง
    assert "5" in sent[0]["embeds"][0]["description"]


def test_monitor_group_no_provider_counts_failures(tmp_path, monkeypatch):
    conn, sent = _monitor_rounds(tmp_path, monkeypatch, provider=None)
    assert cli._sentiment_fail_streak == 5
    assert len(sent) == 1  # key หาย = provider ไม่มี — นับเหมือนกัน
