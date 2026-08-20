from __future__ import annotations

from unittest.mock import MagicMock, patch
from app.distributor_master import fetch_distributor_master
from app.distributors import resolve_distributors_from_codes
from app.models import BenchmarkExtraction, DataProvenance, Fund
from app.stage5_benchmark import _finalize_extraction


def test_resolve_distributors_from_codes_categorization():
    dummy_master = {
        "101": {"CompanyName": "野村證券", "CompanyType": "1"},
        "102": {"CompanyName": "大和証券", "CompanyType": "1"},
        "201": {"CompanyName": "三菱UFJ銀行", "CompanyType": "2"},
        "501": {"CompanyName": "ゆうちょ銀行", "CompanyType": "5"},
        "301": {"CompanyName": "日本生命保険", "CompanyType": "3"},
        "999": {"CompanyName": "その他", "CompanyType": "4"},
    }

    codes = ["101", "102", "201", "501", "301", "999", "000_NOT_EXIST"]
    sec, banks, ins = resolve_distributors_from_codes(codes, dummy_master)

    assert sec == ["野村證券", "大和証券"]
    assert banks == ["三菱UFJ銀行", "ゆうちょ銀行"]
    assert ins == ["日本生命保険"]


def test_fallback_when_company_codes_is_empty():
    fund_without_codes = Fund(
        fund_name="野村日本株ファンド",
        fund_code="0131102B",
        company_codes=[],
        management_company="野村アセットマネジメント",
    )
    extraction = BenchmarkExtraction(
        benchmark="TOPIX",
        theme_category="日本株式・高配当",
    )

    final = _finalize_extraction(extraction, fund_without_codes)
    assert final.top_distributors != ""
    assert final.primary_broker == "野村證券"
    assert final.distributor_provenance == DataProvenance.SYNTHETIC


def test_distributor_provenance_actual_when_codes_present():
    dummy_master = {
        "001": {"CompanyName": "アイザワ証券", "CompanyType": "1"},
        "886": {"CompanyName": "あいち銀行", "CompanyType": "2"},
    }
    with patch("app.stage5_benchmark.fetch_distributor_master", return_value=dummy_master):
        fund_with_codes = Fund(
            fund_name="アジア好配当株投信",
            fund_code="0131106B",
            company_codes=["001", "886"],
            management_company="野村アセットマネジメント",
        )
        extraction = BenchmarkExtraction(
            benchmark="MSCI AC Asia",
            theme_category="アジア株式",
        )
        final = _finalize_extraction(extraction, fund_with_codes)
        assert "アイザワ証券" in final.top_distributors
        assert "あいち銀行" in final.top_distributors
        assert final.distributor_provenance == DataProvenance.ACTUAL
