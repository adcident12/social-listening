"""sentiment.py — provider-agnostic interface (no real HTTP until credentials land)"""
import sentiment
from sentiment import SentimentResult, analyze_text, get_provider


def test_no_provider_when_env_unset(monkeypatch):
    monkeypatch.delenv("SENTIMENT_PROVIDER", raising=False)
    assert get_provider() is None
    assert analyze_text("hello") == SentimentResult(None, None)


def test_openai_compatible_selected(monkeypatch):
    monkeypatch.setenv("SENTIMENT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("SENTIMENT_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("SENTIMENT_API_KEY", "k")
    monkeypatch.setenv("SENTIMENT_MODEL", "m")
    assert isinstance(get_provider(), sentiment.OpenAICompatibleProvider)


def test_openai_compatible_missing_creds_not_constructed(monkeypatch):
    monkeypatch.setenv("SENTIMENT_PROVIDER", "openai_compatible")
    monkeypatch.delenv("SENTIMENT_BASE_URL", raising=False)
    monkeypatch.delenv("SENTIMENT_API_KEY", raising=False)
    monkeypatch.setenv("SENTIMENT_MODEL", "m")
    assert get_provider() is None  # creds ไม่ครบ → ไม่สร้าง provider (ไม่ crash)


def test_anthropic_selected(monkeypatch):
    monkeypatch.setenv("SENTIMENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    monkeypatch.setenv("SENTIMENT_MODEL", "claude-x")
    assert isinstance(get_provider(), sentiment.AnthropicProvider)


def test_anthropic_missing_key_not_constructed(monkeypatch):
    monkeypatch.setenv("SENTIMENT_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SENTIMENT_MODEL", "claude-x")
    assert get_provider() is None


def test_unknown_provider_is_none(monkeypatch):
    monkeypatch.setenv("SENTIMENT_PROVIDER", "bogus")
    assert get_provider() is None


def test_selected_but_unimplemented_returns_null(monkeypatch):
    # เลือก provider แล้ว แต่ implementation ยังเป็น stub → NULL ไม่ crash, ไม่ fallback
    monkeypatch.setenv("SENTIMENT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("SENTIMENT_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("SENTIMENT_API_KEY", "k")
    monkeypatch.setenv("SENTIMENT_MODEL", "m")
    assert analyze_text("hello") == SentimentResult(None, None)


def test_provider_down_returns_null():
    class Down:
        def classify(self, text):
            raise RuntimeError("connection refused")
    assert analyze_text("hello", provider=Down()) == SentimentResult(None, None)


def test_provider_ok_returns_result():
    class Fake:
        def classify(self, text):
            return SentimentResult("positive", "good")
    assert analyze_text("hello", provider=Fake()) == SentimentResult("positive", "good")
