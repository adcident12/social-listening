from __future__ import annotations

import os
from dataclasses import dataclass

# Provider-agnostic sentiment seam — เลือก active provider ผ่าน SENTIMENT_PROVIDER (.env).
# ยังไม่ implement HTTP จริงจนกว่าจะมี credentials: provider เป็น stub → classify raise → caller degrade เป็น NULL (skip เดิม)


@dataclass
class SentimentResult:
    label: str | None      # "positive" | "neutral" | "negative" | None
    summary: str | None = None


class SentimentProvider:
    """contract: classify(text) -> SentimentResult — raise ได้ถ้า transport/config error (caller จะ degrade เป็น NULL)"""
    name = "base"

    def classify(self, text: str) -> SentimentResult:
        raise NotImplementedError


class OpenAICompatibleProvider(SentimentProvider):
    """ใช้กับ llamacpp / Groq / OpenAI — endpoint แบบ OpenAI /chat/completions"""
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def classify(self, text: str) -> SentimentResult:
        # ponytail: stub — implement HTTP (OpenAI-compatible /chat/completions) เมื่อมี credentials
        raise NotImplementedError("openai_compatible not implemented until credentials available")


class AnthropicProvider(SentimentProvider):
    """Claude API — /v1/messages format (แยก client จาก openai_compatible)"""
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def classify(self, text: str) -> SentimentResult:
        # ponytail: stub — implement HTTP (Anthropic /v1/messages) เมื่อมี credentials
        raise NotImplementedError("anthropic not implemented until credentials available")


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
    """Never raises — provider ไม่มี / ยังไม่ implement / ดับ → NULL (skip เดิม) · ไม่ fallback ข้าม provider"""
    p = provider if provider is not None else get_provider()
    if p is None:
        return SentimentResult(None, None)
    try:
        return p.classify(text)
    except Exception:
        return SentimentResult(None, None)
