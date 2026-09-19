from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Provider-agnostic sentiment seam — เลือก active provider ผ่าน SENTIMENT_PROVIDER (.env).
# HTTP จริงแล้ว (stdlib urllib) — ใช้เมื่อ creds ครบ, analyze_text degrade เป็น NULL ถ้าดับ

PROMPT_VERSION = "1"
_TEXT_LIMIT = 2000  # cost control — โพสต์ยาวตัดตรง (summary ไม่แม่นขึ้นอีกแล้ว)
_LABELS = ("positive", "neutral", "negative")

PROMPT = (
    "Classify the social-media text below. Reply with ONLY minified JSON, no other words:\n"
    '{"label":"positive|neutral|negative","summary":"one short sentence in the text language",'
    '"theme":"price|product|promotion|other"}\n'
    "theme = what the text is mainly discussing.\n"
    "TEXT:\n"
)


@dataclass
class SentimentResult:
    label: str | None        # "positive" | "neutral" | "negative" | None
    summary: str | None = None
    theme: str | None = None  # "price" | "product" | "promotion" | "other" | None
    model_version: str | None = None   # model ที่วิเคราะห์ (track comparability)
    prompt_version: str | None = None  # PROMPT_VERSION ที่ใช้ (track comparability)


class SentimentProvider:
    """contract: classify(text) -> SentimentResult — raise ได้ถ้า transport/config error (caller จะ degrade เป็น NULL)"""
    name = "base"

    def classify(self, text: str) -> SentimentResult:
        raise NotImplementedError


def _post_json(url: str, headers: dict, body: dict, timeout: int = 30) -> dict:
    """HTTP seam — stdlib urllib · tests monkeypatch จุดนี้"""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={**headers, "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_content(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):  # LLM บางตัวห่อ code fence — ถอดออก
        raw = raw[3:]
        if raw[:4].lstrip().lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    data = json.loads(raw)  # raise ValueError ถ้าไม่ JSON → analyze_text degrade NULL
    label = data.get("label")
    if label not in _LABELS:
        raise ValueError(f"unexpected label: {label!r}")
    return data


def _result(content: str, model: str) -> SentimentResult:
    data = _parse_content(content)
    return SentimentResult(data["label"], data.get("summary"), data.get("theme"), model, PROMPT_VERSION)


class OpenAICompatibleProvider(SentimentProvider):
    """ใช้กับ llamacpp / Groq / OpenAI — endpoint แบบ OpenAI /chat/completions"""
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def classify(self, text: str) -> SentimentResult:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": PROMPT + text[:_TEXT_LIMIT]}],
            "temperature": 0,
        }
        resp = _post_json(f"{self.base_url}/chat/completions",
                          {"Authorization": f"Bearer {self.api_key}"}, body)
        return _result(resp["choices"][0]["message"]["content"], self.model)


class AnthropicProvider(SentimentProvider):
    """Claude API — /v1/messages format (แยก client จาก openai_compatible)"""
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def classify(self, text: str) -> SentimentResult:
        body = {
            "model": self.model,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": PROMPT + text[:_TEXT_LIMIT]}],
        }
        resp = _post_json("https://api.anthropic.com/v1/messages",
                          {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, body)
        content = "".join(block.get("text", "") for block in resp.get("content", []))
        return _result(content, self.model)


def load_dotenv(path: str = ".env") -> None:
    """reads KEY=VALUE from .env — setdefault เท่านั้น (os.environ ที่มีอยู่แล้วชนะเสมอ)
    ไม่มีไฟล์ = skip เงียบ · ไม่ print ค่า (อาจเป็น secret)"""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def get_provider() -> SentimentProvider | None:
    """SENTIMENT_PROVIDER → provider instance · None ถ้าไม่ตั้ง หรือ creds ไม่ครบ (ไม่ auto-fallback)"""
    name = os.environ.get("SENTIMENT_PROVIDER", "").strip()
    model = os.environ.get("SENTIMENT_MODEL", "").strip()
    if name == "openai_compatible":
        base_url = os.environ.get("SENTIMENT_BASE_URL", "").strip()
        api_key = os.environ.get("SENTIMENT_API_KEY", "").strip()
        if base_url and api_key and model:
            return OpenAICompatibleProvider(base_url, api_key, model)
    elif name == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if api_key and model:
            return AnthropicProvider(api_key, model)
    return None


def analyze_text(text: str, provider: SentimentProvider | None = None) -> SentimentResult:
    """Never raises — provider ไม่มี / ดับ / output พัง → NULL (skip เดิม) · ไม่ fallback ข้าม provider"""
    p = provider if provider is not None else get_provider()
    if p is None:
        return SentimentResult(None, None)
    try:
        return p.classify(text)
    except Exception as e:
        print(f"sentiment failed: {e}")  # เงียบไม่ได้ — ต้องเห็นเหตุผล (401 / timeout / output พัง)
        return SentimentResult(None, None)
