from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.daiwa_stage1 import run_stage1_daiwa
from app.muam_stage1 import run_stage1_muam


@patch("httpx.Client.get")
def test_stage1_daiwa_mock(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "fund": [
            {
                "fund_code": "5170",
                "details": {
                    "fund_name": "iFreeNEXT FANG+インデックス",
                    "netasset_value": 300000000000,
                    "base_value": 45000,
                    "etf_flg": False,
                    "mokuromi_report": "/funds/doc_open/fund_doc_open.php?code=5170&type=1",
                },
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    funds = run_stage1_daiwa(max_funds=10)
    assert len(funds) == 1
    assert funds[0].fund_code == "5170"
    assert funds[0].fund_name == "iFreeNEXT FANG+インデックス"
    assert funds[0].aum == 300000000000
    assert "5170" in funds[0].prospectus_pdf_url


@patch("httpx.Client.get")
def test_stage1_muam_mock(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "datasets": {
            "api00001tmCmFndSearchDetailOutDto": [
                {
                    "cfsd_fund_cd": "253425",
                    "cfsd_fund_name": "eMAXIS Slim 全世界株式(オール・カントリー)",
                    "cfsd_net_asset_value": 13759967163566,
                    "cfsd_purchase_or_base_price": 25000,
                    "cfsd_isin_cd": "JP90C000HLP4",
                    "cfs_etc_type_etf": 0,
                }
            ]
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    funds = run_stage1_muam(max_funds=10)
    assert len(funds) == 1
    assert funds[0].fund_code == "253425"
    assert "eMAXIS Slim" in funds[0].fund_name
    assert funds[0].aum == 13759967163566
    assert "253425" in funds[0].prospectus_pdf_url


@patch("httpx.Client.get", side_effect=RuntimeError("network down"))
def test_daiwa_falls_back_to_bundled_master_by_default(mock_get: MagicMock) -> None:
    funds = run_stage1_daiwa(max_funds=5)
    assert funds, "bundled master should keep the app usable when the API is down"


@patch("httpx.Client.get", side_effect=RuntimeError("network down"))
def test_daiwa_refuses_stale_fallback_when_disabled(mock_get: MagicMock) -> None:
    """The daily snapshot job must fail rather than record stale AUM as today."""
    with pytest.raises(RuntimeError, match="fallback disabled"):
        run_stage1_daiwa(max_funds=5, allow_fallback=False)


@patch("httpx.Client.get", side_effect=RuntimeError("network down"))
def test_muam_refuses_stale_fallback_when_disabled(mock_get: MagicMock) -> None:
    with pytest.raises(RuntimeError, match="fallback disabled"):
        run_stage1_muam(max_funds=5, allow_fallback=False)


@patch("httpx.Client.get")
def test_muam_handles_empty_result_without_indexerror(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"datasets": {"api00001tmCmFndSearchDetailOutDto": []}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    assert run_stage1_muam(max_funds=5) == []
