from __future__ import annotations

from unittest.mock import patch
from app.distributor_extractor import (
    extract_distributors_from_text,
    extract_distributors_with_fallback,
)


def test_extract_distributors_from_text_explicit_table():
    sample_text = """
    【ファンドの概要】
    当ファンドは先進国の株式に投資します。

    【取扱販売会社】
    株式会社ＳＢＩ証券
    楽天証券株式会社
    マネックス証券株式会社
    株式会社三菱ＵＦＪ銀行

    【受託会社】
    三菱ＵＦＪ信託銀行株式会社
    """
    dists, conf = extract_distributors_from_text(sample_text)
    assert "ＳＢＩ証券" in dists
    assert "楽天証券" in dists
    assert "マネックス証券" in dists
    assert "三菱ＵＦＪ銀行" in dists
    assert conf > 0.5


def test_extract_distributors_from_text_daiwa_wrap():
    sample_text = """
    「ダイワファンドラップ セレクト・シリーズ」は、投資者と販売会社が締結する投資一任契約に基づいて運用されます。
    ダイワファンドラップ セレクト・シリーズの購入の申込みを行なう投資者は、販売会社と投資一任契約の資産運用を行ないます。
    """
    dists, conf = extract_distributors_from_text(sample_text)
    assert "大和証券" in dists
    assert conf > 0.5


def test_extract_distributors_from_text_empty_when_no_mention():
    sample_text = """
    ●ファンドに関する投資信託説明書（請求目論見書）を含む詳細な情報は、委託会社のホームページでご覧いただけます。
    ※販売会社により取扱いが異なる場合があります。くわしくは、販売会社にご確認ください。
    """
    dists, conf = extract_distributors_from_text(sample_text)
    assert dists == []
    assert conf == 0.0


def test_extract_distributors_with_fallback_rule():
    text = "取扱販売会社\n野村證券株式会社\n大和証券株式会社"
    dists, conf, prov = extract_distributors_with_fallback("テストファンド", text)
    assert dists == ["野村證券", "大和証券"]
    assert prov == "ACTUAL"


def test_extract_distributors_with_fallback_llm():
    text = "※販売会社により取扱いが異なる場合があります。"
    with patch("app.llm.llm_available", return_value=True), \
         patch("app.llm.extract_distributors_with_llm", return_value=(["松井証券"], 0.8)):
        dists, conf, prov = extract_distributors_with_fallback(
            "テストファンド",
            text,
            provider="gemini",
        )
        assert dists == ["松井証券"]
        assert prov == "DERIVED"
