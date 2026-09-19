import sqlite3
from datetime import datetime, timezone

import alerts
from store import init_db, upsert_posts


def _seeded_conn(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_posts(conn, "g1", [
        {"post_id": "n1", "poster_name": "A", "body": "บริการนี่แย่มาก ไม่ค่อยพอใจ",
         "created_at": "2026-09-19T00:00:00+00:00",
         "reaction_count": 1, "comment_count": 0, "permalink": "https://x/n1"},
        {"post_id": "b1", "poster_name": "B", "body": "ผมใช้ Claude สร้างบอทครับ",
         "created_at": "2026-09-19T01:00:00+00:00",
         "reaction_count": 2, "comment_count": 1, "permalink": "https://x/b1"},
        {"post_id": "e1", "poster_name": "C", "body": "มาแชร์โปรเจกต์",
         "created_at": "2026-09-19T02:00:00+00:00",
         "reaction_count": 500, "comment_count": 300, "share_count": 200,
         "permalink": "https://x/e1"},
    ], "2026-09-19T03:00:00+00:00")
    conn.execute("UPDATE posts SET sentiment='negative' WHERE post_id='n1'")
    conn.execute("UPDATE posts SET sentiment='neutral' WHERE post_id='b1'")
    conn.commit()
    return conn


def _cfg(**over):
    al = {"enabled": True, "webhook_url": "https://discord.example/hook",
          "rules": ["negative", "brand_mention", "high_engagement"],
          "min_engagement": 100, "cooldown_minutes": 60}
    al.update(over)
    return {"alerts": al, "watch": {"words": ["Claude"]}}


def _rows(conn):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT * FROM posts WHERE group_id='g1'").fetchall()]


def test_evaluate_rules_pairs(tmp_path):
    conn = _seeded_conn(tmp_path)
    pairs = alerts.evaluate_rules(_rows(conn), _cfg()["alerts"], ["Claude"])
    assert sorted((p["post_id"], r) for p, r in pairs) == [
        ("b1", "brand_mention"), ("e1", "high_engagement"), ("n1", "negative"),
    ]


def test_evaluate_rules_only_enabled_rules(tmp_path):
    conn = _seeded_conn(tmp_path)
    cfg = _cfg()
    cfg["alerts"]["rules"] = ["high_engagement"]
    pairs = alerts.evaluate_rules(_rows(conn), cfg["alerts"], ["Claude"])
    assert [(p["post_id"], r) for p, r in pairs] == [("e1", "high_engagement")]


def test_check_alerts_fires_and_dedupes(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path)
    sent = []
    monkeypatch.setattr(alerts, "_post", lambda url, payload: sent.append((url, payload)) or True)
    assert alerts.check_alerts(conn, "g1", "กลุ่ม", _cfg()) == 3
    assert alerts.check_alerts(conn, "g1", "กลุ่ม", _cfg()) == 0  # dedup — ไม่ยิงซ้ำ
    assert len(conn.execute("SELECT * FROM alerts").fetchall()) == 3
    assert all(u == "https://discord.example/hook" for u, _ in sent)


def test_check_alerts_disabled_noop(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path)
    sent = []
    monkeypatch.setattr(alerts, "_post", lambda url, payload: sent.append(1) or True)
    assert alerts.check_alerts(conn, "g1", "กลุ่ม", _cfg(enabled=False)) == 0
    assert not sent


def test_check_alerts_post_fail_not_logged(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path)
    monkeypatch.setattr(alerts, "_post", lambda url, payload: False)
    assert alerts.check_alerts(conn, "g1", "กลุ่ม", _cfg()) == 0
    assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0  # retry รอบหน้า
    monkeypatch.setattr(alerts, "_post", lambda url, payload: True)
    assert alerts.check_alerts(conn, "g1", "กลุ่ม", _cfg()) == 3  # รอบถัดไปยิงได้


def test_check_alerts_cooldown_skips(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path)
    sent = []
    monkeypatch.setattr(alerts, "_post", lambda url, payload: sent.append(1) or True)
    conn.execute("INSERT INTO alerts (post_id, rule, fired_at, group_id)"
                 " VALUES ('n1','negative',?,'g1')",
                 (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    assert alerts.check_alerts(conn, "g1", "กลุ่ม", _cfg()) == 0
    assert not sent


def test_check_alerts_cooldown_is_per_group(tmp_path, monkeypatch):
    conn = _seeded_conn(tmp_path)
    upsert_posts(conn, "g2", [
        {"post_id": "n2", "poster_name": "D", "body": "บริการแย่มากอีกกลุ่ม",
         "created_at": "2026-09-19T04:00:00+00:00",
         "reaction_count": 1, "comment_count": 0, "permalink": "https://x/n2"},
    ], "2026-09-19T05:00:00+00:00")
    conn.execute("UPDATE posts SET sentiment='negative' WHERE post_id='n2'")
    conn.commit()
    monkeypatch.setattr(alerts, "_post", lambda url, payload: True)
    assert alerts.check_alerts(conn, "g1", "กลุ่ม1", _cfg()) == 3
    assert alerts.check_alerts(conn, "g2", "กลุ่ม2", _cfg()) == 1  # g1 ยิงแล้ว — g2 ต้องไม่โดนปิดเสียง
    assert alerts.check_alerts(conn, "g2", "กลุ่ม2", _cfg()) == 0  # dedup + cooldown ของ g2 เอง


def test_discord_payload_embed_shape():
    row = {"post_id": "n1", "poster_name": "A", "body": "   บริการนี่   แย่มาก  ",
           "permalink": "https://x/n1", "sentiment": "negative",
           "reaction_count": 1, "comment_count": 0, "share_count": 0,
           "created_at": "2026-09-19T00:00:00+00:00"}
    p = alerts.discord_payload("กลุ่ม", row, "negative")
    e = p["embeds"][0]
    assert e["title"] == "negative — กลุ่ม"
    assert e["description"] == "บริการนี่ แย่มาก"
    assert e["url"] == "https://x/n1"
    assert e["color"] == alerts.RULE_COLORS["negative"]
    assert e["timestamp"] == "2026-09-19T00:00:00+00:00"
    assert len(p["embeds"]) == 1


def test_discord_payload_brand_lists_matched_words():
    row = {"post_id": "b1", "poster_name": "B", "body": "ผมใช้ Claude สร้างบอทครับ",
           "permalink": "https://x/b1", "sentiment": "neutral",
           "reaction_count": 2, "comment_count": 1, "share_count": 0,
           "created_at": "2026-09-19T01:00:00+00:00"}
    p = alerts.discord_payload("กลุ่ม", row, "brand_mention", ["Claude", "GPT"])
    assert "Claude" in p["embeds"][0]["title"]
    assert "GPT" not in p["embeds"][0]["title"]
