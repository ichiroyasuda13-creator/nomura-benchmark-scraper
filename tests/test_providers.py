from __future__ import annotations

from datetime import date

from app.models import parse_aum_yen, parse_japanese_date
from app.providers import detect_index_provider, extract_from_fund_name, is_msci_benchmark


def test_parse_japanese_date() -> None:
    assert parse_japanese_date("2026年07月21日") == date(2026, 7, 21)


def test_parse_aum_yen() -> None:
    assert parse_aum_yen("322.8") == 322.8
    assert parse_aum_yen(32283737184.0) == 32283737184.0


def test_detect_index_provider_msci() -> None:
    assert detect_index_provider("MSCI-KOKUSAI（配当込み）") == "MSCI"
    assert is_msci_benchmark("MSCI-KOKUSAI（配当込み）", "MSCI") is True


def test_detect_index_provider_topix() -> None:
    assert detect_index_provider("TOPIX（配当込み）") == "JPX/東証"


def test_detect_index_provider_composite() -> None:
    assert detect_index_provider("TOPIX + MSCI-KOKUSAI", composite=True) == "複合"


def test_detect_index_provider_bloomberg() -> None:
    assert detect_index_provider("ブルームバーグ・グローバル・アグリゲート（除く日本）") == "ブルームバーグ"


def test_detect_index_provider_ice() -> None:
    assert detect_index_provider("ICE BofA US High Yield Index") == "ICE Data Indices"


def test_detect_index_provider_solactive() -> None:
    assert detect_index_provider("Solactive Global AI & Semiconductor Index") == "Solactive"


def test_detect_index_provider_stoxx() -> None:
    assert detect_index_provider("EURO STOXX 50 Index") == "STOXX"


def test_detect_index_provider_morningstar() -> None:
    assert detect_index_provider("Morningstar US Target Market Exposure Index") == "Morningstar"


def test_extract_from_fund_name_nikkei225() -> None:
    matched = extract_from_fund_name("NEXT FUNDS 日経225連動型上場投信")
    assert matched is not None
    benchmark, provider = matched
    assert benchmark == "日経225"
    assert provider == "日本経済新聞社"


def test_clean_index_name_strips_trailing_parenthetical_noise() -> None:
    from app.providers import clean_index_name

    raw = "TOPIX（配当込み）（対象株価指数）"
    assert clean_index_name(raw) == "TOPIX（配当込み）"

    raw2 = "MSCI エマージング・マーケット・インデックス（配当込み、円換算ベース）（以下「対象インデックス」といいます）"
    assert clean_index_name(raw2) == "MSCI エマージング・マーケット・インデックス（配当込み、円換算ベース）"


def test_is_money_market_fund() -> None:
    from app.providers import is_money_market_fund

    assert is_money_market_fund("野村MRF (マネー・リザーブ・ファンド)") is True
    assert is_money_market_fund("野村公社債投信") is True
    assert is_money_market_fund("NEXT FUNDS TOPIX連動型上場投信") is False

