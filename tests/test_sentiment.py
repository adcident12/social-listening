"""sentiment.py — provider-agnostic interface + HTTP scaffold (mocked, no live calls)"""
import json

import sentiment
from sentiment import PROMPT_VERSION, SentimentResult, analyze_text, get_provider


def _openai_env(monkeypatch):
    monkeypatch.setenv("SENTIMENT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("SENTIMENT_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("SENTIMENT_API_KEY", "k")
    monkeypatch.setenv("SENTIMENT_MODEL", "m")


def test_no_provider_when_env_unset(monkeypatch):
    monkeypatch.delenv("SENTIMENT_PROVIDER", raising=False)
    assert get_provider() is None
    assert analyze_text("hello") == SentimentResult(None, None)


def test_openai_compatible_selected(monkeypatch):
    _openai_env(monkeypatch)
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


def test_sentiment_result_extended_fields():
    r = SentimentResult("positive", "good", "price", "m", PROMPT_VERSION)
    assert r.label == "positive"
    assert r.summary == "good"
    assert r.theme == "price"
    assert r.model_version == "m"
    assert r.prompt_version == PROMPT_VERSION
    assert SentimentResult(None, None) == SentimentResult(None, None, None, None, None)


def test_openai_classify_request_and_parse(monkeypatch):
    calls = {}

    def fake_post(url, headers, body):
        calls.update(url=url, headers=headers, body=body)
        content = json.dumps({"label": "negative", "summary": "bad service", "theme": "product"})
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(sentiment, "_post_json", fake_post)
    _openai_env(monkeypatch)
    r = get_provider().classify("hello world")
    assert calls["url"] == "http://localhost:8080/v1/chat/completions"
    assert calls["headers"]["Authorization"] == "Bearer k"
    assert calls["body"]["model"] == "m"
    assert "hello world" in calls["body"]["messages"][0]["content"]
    assert r == SentimentResult("negative", "bad service", "product", "m", PROMPT_VERSION)


def test_anthropic_classify_request_and_parse(monkeypatch):
    calls = {}

    def fake_post(url, headers, body):
        calls.update(url=url, headers=headers, body=body)
        content = json.dumps({"label": "neutral", "summary": "ปกติ", "theme": "other"})
        return {"content": [{"type": "text", "text": content}]}

    monkeypatch.setattr(sentiment, "_post_json", fake_post)
    monkeypatch.setenv("SENTIMENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    monkeypatch.setenv("SENTIMENT_MODEL", "claude-x")
    r = get_provider().classify("สวัสดีครับ")
    assert calls["url"] == "https://api.anthropic.com/v1/messages"
    assert calls["headers"]["x-api-key"] == "ak"
    assert calls["headers"]["anthropic-version"] == "2023-06-01"
    assert calls["body"]["model"] == "claude-x"
    assert r == SentimentResult("neutral", "ปกติ", "other", "claude-x", PROMPT_VERSION)


def test_classify_tolerates_code_fenced_json(monkeypatch):
    def fake_post(url, headers, body):
        return {"choices": [{"message": {"content": '```json\n{"label":"positive","summary":"ok","theme":"price"}\n```'}}]}
    monkeypatch.setattr(sentiment, "_post_json", fake_post)
    r = sentiment.OpenAICompatibleProvider("http://x/v1", "k", "m").classify("cheap!")
    assert r.label == "positive"
    assert r.theme == "price"


def test_long_text_truncated(monkeypatch):
    calls = {}

    def fake_post(url, headers, body):
        calls["body"] = body
        return {"choices": [{"message": {"content": '{"label":"neutral","summary":"s","theme":"other"}'}}]}

    monkeypatch.setattr(sentiment, "_post_json", fake_post)
    p = sentiment.OpenAICompatibleProvider("http://x/v1", "k", "m")
    p.classify("x" * 5000)
    msg = calls["body"]["messages"][0]["content"]
    assert "x" * 2000 in msg
    assert "x" * 2500 not in msg  # capped, cost control


def test_provider_down_returns_null():
    class Down:
        def classify(self, text):
            raise RuntimeError("connection refused")
    assert analyze_text("hello", provider=Down()) == SentimentResult(None, None)


def test_selected_provider_down_returns_null(monkeypatch):
    # provider ถูกเลือกแล้ว, transport ดับ → NULL ไม่ crash, ไม่ fallback
    _openai_env(monkeypatch)

    def boom(url, headers, body):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(sentiment, "_post_json", boom)
    assert analyze_text("hello") == SentimentResult(None, None, None, None, None)


def test_malformed_llm_output_returns_null(monkeypatch):
    _openai_env(monkeypatch)

    def bad(url, headers, body):
        return {"choices": [{"message": {"content": "not json at all"}}]}

    monkeypatch.setattr(sentiment, "_post_json", bad)
    assert analyze_text("hello") == SentimentResult(None, None)


def test_provider_ok_returns_result():
    class Fake:
        def classify(self, text):
            return SentimentResult("positive", "good")
    assert analyze_text("hello", provider=Fake()) == SentimentResult("positive", "good")
