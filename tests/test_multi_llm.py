from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.llm import (
    _extract_json,
    extract_with_llm,
    get_available_providers,
    llm_available,
    resolve_active_provider,
)
from app.models import Confidence, ExtractionMethod, FundType


def test_extract_json_from_clean_text() -> None:
    raw = '{"fund_type": "インデックス", "benchmark": "TOPIX", "is_msci": false, "confidence": "high", "needs_review": false}'
    result = _extract_json(raw)
    assert result["benchmark"] == "TOPIX"


def test_extract_json_from_markdown_code_fence() -> None:
    raw = '```json\n{"fund_type": "インデックス", "benchmark": "MSCI ACWI", "is_msci": true, "confidence": "high", "needs_review": false}\n```'
    result = _extract_json(raw)
    assert result["benchmark"] == "MSCI ACWI"
    assert result["is_msci"] is True


def test_extract_json_with_surrounding_commentary() -> None:
    raw = 'Here is the extracted benchmark:\n{"fund_type": "アクティブ", "benchmark": "S&P 500", "is_msci": false, "confidence": "high", "needs_review": false}\nHope this helps!'
    result = _extract_json(raw)
    assert result["benchmark"] == "S&P 500"


def test_get_available_providers_structure() -> None:
    providers = get_available_providers()
    assert isinstance(providers, list)
    # Ollama is always listed
    assert any(p["id"] == "ollama" for p in providers)


def test_resolve_active_provider_fallback() -> None:
    with patch("app.llm.ANTHROPIC_API_KEY", "test_key"), patch("app.llm.GEMINI_API_KEY", ""), patch("app.llm.OPENAI_API_KEY", ""):
        assert resolve_active_provider("auto") == "anthropic"
        assert resolve_active_provider("anthropic") == "anthropic"

    with patch("app.llm.ANTHROPIC_API_KEY", ""), patch("app.llm.GEMINI_API_KEY", "test_gemini"), patch("app.llm.OPENAI_API_KEY", ""):
        assert resolve_active_provider("auto") == "gemini"


@patch("app.llm._call_anthropic")
def test_extract_with_llm_anthropic(mock_call: MagicMock) -> None:
    mock_call.return_value = json.dumps({
        "fund_type": "インデックス",
        "benchmark": "MSCI-KOKUSAI指数（配当込み）",
        "index_provider": "MSCI",
        "is_msci": True,
        "confidence": "high",
        "needs_review": False,
        "note": "目論見書より抽出",
    })

    with patch("app.llm.ANTHROPIC_API_KEY", "fake_key"):
        result = extract_with_llm(
            fund_name="テストファンド",
            section_text="MSCI-KOKUSAIに連動する投資成果をめざします",
            rule_hint={},
            provider="anthropic",
        )
        assert result is not None
        assert result.benchmark == "MSCI-KOKUSAI指数（配当込み）"
        assert result.is_msci is True
        assert result.confidence == Confidence.HIGH
