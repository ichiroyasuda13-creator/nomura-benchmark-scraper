from __future__ import annotations

import json
import re
from unittest.mock import MagicMock, patch

from app.stage1_list import _parse_jsonp, raw_to_fund


def test_parse_jsonp() -> None:
    payload = {"section1": {"status": 0, "data": []}}
    text = f"callback({json.dumps(payload, ensure_ascii=False)})"
    assert _parse_jsonp(text) == payload


def test_raw_to_fund_maps_fields() -> None:
    raw = {
        "FundName": "テストファンド",
        "FundCode": "0131106B",
        "NAMCode": "140380",
        "SRTTotalNetAsset": 32283737184.0,
        "TotalNetAsset": "322.8",
        "ReferenceDate": "2026年07月21日",
        "DetailUrl": "//www.nomura-am.co.jp/fund/funddetail.php?fundcd=140380",
        "CategoryName": "追加型投信 / 海外 / 株式",
    }
    fund = raw_to_fund(raw, rank=1)
    assert fund.fund_name == "テストファンド"
    assert fund.nam_code == "140380"
    assert fund.aum == 32283737184.0
    assert fund.detail_url.startswith("https://")
    assert fund.rank == 1


@patch("app.stage2_pdf_url.HttpClient")
def test_prospectus_url_template(mock_client_cls: MagicMock) -> None:
    from app.stage2_pdf_url import resolve_prospectus_url

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    def head_side_effect(url: str, **kwargs):
        response = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Type": "application/pdf"}
        if "Y1140380" in url:
            return response
        response.status_code = 404
        return response

    mock_client.head.side_effect = head_side_effect

    fund = raw_to_fund(
        {
            "FundName": "アジア好配当株投信",
            "FundCode": "0131106B",
            "NAMCode": "140380",
            "SRTTotalNetAsset": 1,
            "DetailUrl": "//www.nomura-am.co.jp/fund/funddetail.php?fundcd=140380",
        },
        rank=1,
    )
    url = resolve_prospectus_url(fund, mock_client)
    assert url == "https://www.nomura-am.co.jp/fund/pros_gen/Y1140380.pdf"
