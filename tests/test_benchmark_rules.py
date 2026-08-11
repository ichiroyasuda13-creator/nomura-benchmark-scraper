from __future__ import annotations

from app.models import Confidence, ExtractionMethod, Fund, FundType
from app.providers import extract_from_fund_name
from app.stage5_benchmark import (
    _build_name_fallback_extraction,
    _build_rule_extraction,
    _should_force_ocr,
    extract_relevant_sections,
)


def _fund(name: str = "テストファンド") -> Fund:
    return Fund(
        fund_name=name,
        fund_code="TEST001",
        nam_code="123456",
        detail_url="https://www.nomura-am.co.jp/fund/funddetail.php?fundcd=123456",
    )


def test_index_fund_rendou_without_benchmark_word() -> None:
    text = """
    ファンドの目的
    本ファンドは、MSCI エマージング・マーケット・インデックス（配当込み、円換算ベース）
    に連動する投資成果をめざします。
    ファンドの特色
    インデックス型ファンドです。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(_fund("MSCIエマージング連動ファンド"), sections)
    assert result.fund_type == FundType.INDEX
    assert result.benchmark is not None
    assert "MSCI" in result.benchmark
    assert "エマージング" in result.benchmark
    assert result.index_provider == "MSCI"
    assert result.is_msci is True
    assert result.confidence == Confidence.HIGH


def test_index_fund_kokusai_rendou() -> None:
    text = """
    ファンドの目的
    本ファンドは、MSCI-KOKUSAI（配当込み）に連動する投資成果を目指します。
    ファンドの特色
    インデックス型ファンドです。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(_fund("MSCI連動ファンド"), sections)
    assert result.fund_type == FundType.INDEX
    assert result.benchmark is not None
    assert "MSCI-KOKUSAI" in result.benchmark
    assert result.index_provider == "MSCI"
    assert result.confidence == Confidence.HIGH


def test_active_no_benchmark() -> None:
    text = """
    ファンドの目的
    本ファンドは、特定の指数をベンチマークとしません。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(_fund(), sections)
    assert result.fund_type == FundType.ACTIVE_NO_BM
    assert result.benchmark == "なし"
    assert result.confidence == Confidence.HIGH
    assert result.needs_review is False


def test_balance_composite() -> None:
    text = """
    ファンドの目的
    本ファンドは、国内株式25％×TOPIX（配当込み）、外国株式45％×MSCI-KOKUSAI（配当込み）、
    国内債券20％×NOMURA-BPI、外国債券10％×FTSE World Government Bond Index
    からなる複合ベンチマークに連動する投資成果を目指します。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(_fund("マイバランス70（確定拠出年金向け）"), sections)
    assert result.fund_type == FundType.BALANCE_COMPOSITE
    assert result.benchmark_detail is not None
    assert result.index_provider in {"複合", "MSCI", "JPX/東証", "野村", "FTSE Russell"}


def test_active_with_benchmark_and_reference() -> None:
    text = """
    ファンドの目的
    本ファンドは、ブルームバーグ・グローバル・アグリゲート（除く日本・円ヘッジなし）を
    ベンチマークとします。参考指数としてJP Morgan GBI Global TRを用いますが、
    連動対象ではありません。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(
        _fund("野村PIMCO・世界インカム戦略ファンド Bコース（野村SMA・EW向け）"),
        sections,
    )
    assert result.benchmark is not None
    assert "ブルームバーグ" in result.benchmark
    assert result.reference_index is not None


def test_target_index_definition_pattern() -> None:
    text = """
    ファンドの目的
    本ファンドは、TOPIX（配当込み）（以下「対象インデックス」といいます）に連動する
    投資成果をめざします。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(_fund("TOPIX連動ファンド"), sections)
    assert result.benchmark is not None
    assert "TOPIX" in result.benchmark
    assert result.index_provider == "JPX/東証"


def test_name_fallback_next_funds_topix() -> None:
    fund = _fund("NEXT FUNDS TOPIX連動型上場投信　愛称:NF・TOPIX ETF")
    result = _build_name_fallback_extraction(fund)
    assert result is not None
    assert result.benchmark == "TOPIX"
    assert result.extraction_method == ExtractionMethod.NAME_FALLBACK
    assert result.needs_review is True
    assert "名称から推定" in result.note


def test_name_fallback_from_parenthetical() -> None:
    fund = _fund("野村インデックスファンド・外国株式（MSCI-KOKUSAI）")
    matched = extract_from_fund_name(fund.fund_name)
    assert matched is not None
    benchmark, provider = matched
    assert "MSCI" in benchmark
    assert provider == "MSCI"


def test_should_force_ocr_for_index_like_fund_without_benchmark() -> None:
    fund = _fund("NEXT FUNDS TOPIX連動型上場投信")
    fund.is_etf = True
    text = "ファンドの目的\n本ファンドはインデックス型です。"
    extraction = _build_rule_extraction(fund, {"purpose": text})
    assert extraction.benchmark is None
    assert _should_force_ocr(fund, text, extraction) is True


def test_invalid_benchmark_triggers_name_fallback() -> None:
    fund = _fund("NEXT FUNDS 日経225連動型上場投信　愛称:NF・日経225 ETF")
    fund.is_etf = True
    text = """
    ファンドの目的
    本ファンドは、（対象株価指数）に連動する投資成果をめざします。
    """
    sections = extract_relevant_sections(text)
    result = _build_rule_extraction(fund, sections)
    if result.benchmark and "対象株価指数" in result.benchmark:
        fallback = _build_name_fallback_extraction(fund)
        assert fallback is not None
        assert fallback.benchmark == "日経225"


def test_reject_invalid_benchmark_candidate() -> None:
    from app.providers import is_valid_benchmark_name

    assert is_valid_benchmark_name("（対象株価指数）") is False
    assert is_valid_benchmark_name("TOPIX（配当込み）") is True
    assert is_valid_benchmark_name("連動する投資成果（基準価額") is False
