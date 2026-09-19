from __future__ import annotations

from collections import Counter

import pythainlp

# ponytail: stopword list ตัดมือ ~50 คำ, ขยายถ้า keyword พัง — ไม่ใช้ library NLP
STOPWORDS = set("""
a an the and or of in on at to for is are was were be been with as by from
it this that i you he she we they
ผม ฉัน คุณ เขา มัน เรา พวกเรา ไม่ ไม้ แล้ว ก็ แต่ และ ที่ ว่า หรือ เป็น มี ได้ ของ
นะ ครับ ค่ะ นะคะ หน่อย ยัง นะเออ
""".split())


def _tokens(text: str) -> list[str]:
    # ponytail: โทน/สระไทยที่ซ้อน (่ ้ ุ ู ี เ) เป็น Unicode Mn → isalnum() ทั้งคำ
    # เป็น False; ตรวจทีละตัวด้วย any() แทน (ไม่งั้นคำไทยที่มีโทนถูกตัดทิ้งหมด)
    return [
        t for t in pythainlp.word_tokenize(text)
        if any(c.isalnum() for c in t) and len(t) > 1 and t.lower() not in STOPWORDS
    ]


SENTIMENT_ORDER = [("positive", "บวก"), ("neutral", "กลาง"),
                   ("negative", "ลบ"), ("unanalyzed", "ยังไม่ได้วิเคราะห์")]


def _engagement(r: dict) -> int:
    return (r["reaction_count"] or 0) + (r["comment_count"] or 0) + (r.get("share_count") or 0)


def _line(r: dict, with_summary: bool = False) -> str:
    eng = _engagement(r)
    snippet = " ".join((r["body"] or "").split())[:120]
    line = (f"- [{eng}] {r['created_at'] or '—'} — {r['poster_name']}: "
            f"{snippet} {r['permalink'] or ''}")
    if with_summary and r.get("summary"):
        line += f" (สรุป: {r['summary']})"
    return line


def build_digest(rows: list[dict], days: int,
                 top_n_keywords: int, top_n_posts: int) -> str:
    lines = [f"# Group listening digest — last {days} days",
             f"Posts in range: {len(rows)}"]
    if not rows:
        lines.append("(no posts in range)")
        return "\n".join(lines)

    kw: Counter = Counter()
    for r in rows:
        kw.update(set(_tokens(r["body"] or "")))  # นับ 1 ครั้ง/โพสต์

    lines += ["", "## Top keywords"]
    for w, c in kw.most_common(top_n_keywords):
        lines.append(f"- {w}: {c} posts ({c / len(rows):.0%})")

    lines += ["", "## Top posters"]
    for name, c in Counter(r["poster_name"] or "?" for r in rows).most_common(top_n_posts):
        lines.append(f"- {name}: {c}")

    lines += ["", "## Top posts by engagement"]
    top = sorted(rows, key=_engagement, reverse=True)[:top_n_posts]
    lines += [_line(r) for r in top]

    lines += ["", "## Latest posts"]
    lines += [_line(r) for r in rows[:top_n_posts]]  # rows มาเรียง DESC แล้ว

    sent: Counter = Counter(r.get("sentiment") or "unanalyzed" for r in rows)
    lines += ["", "## Sentiment"]
    for key, label in SENTIMENT_ORDER:
        c = sent.get(key, 0)
        lines.append(f"- {label}: {c} ({c / len(rows):.0%})")

    negatives = [r for r in rows if r.get("sentiment") == "negative"]
    if negatives:
        lines += ["", "## โพสต์ลบเด่น"]
        lines += [_line(r, with_summary=True) for r in
                  sorted(negatives, key=_engagement, reverse=True)[:top_n_posts]]

    return "\n".join(lines)
