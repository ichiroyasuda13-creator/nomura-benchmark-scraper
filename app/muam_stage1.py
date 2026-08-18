"""Stage 1 for Mitsubishi UFJ Asset Management (MUAM): Fetch funds list sorted by AUM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import httpx
from loguru import logger

from app.config import DATA_DIR, FUNDS_JSON
from app.http_client import load_json, save_json
from app.models import Fund

MUAM_SEARCH_API = "https://www.am.mufg.jp/mukamapi/fund_search/?site_type=1"
MUAM_MASTER_FALLBACK = DATA_DIR / "muam_funds_master.json"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.am.mufg.jp/fund/list.html",
    "Origin": "https://www.am.mufg.jp",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def run_stage1_muam(
    force: bool = False,
    max_funds: int = 100,
    output_path: Optional[Path] = None,
) -> list[Fund]:
    """三菱UFJアセットマネジメントの公式APIからAUM降順でファンド一覧を取得."""
    target_out = output_path or FUNDS_JSON
    logger.info("Stage1 (MUAM): Fetching funds from {}", MUAM_SEARCH_API)

    raw_funds = []
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=15.0) as client:
            resp = client.get(MUAM_SEARCH_API)
            resp.raise_for_status()
            data = resp.json()
            raw_funds = data.get("datasets", {}).get("api00001tmCmFndSearchDetailOutDto", [])
            logger.info("Stage1 (MUAM): Successfully fetched {} funds from live API", len(raw_funds))
    except Exception as exc:
        logger.warning("Stage1 (MUAM): Live API request failed ({}). Attempting local fallback...", exc)
        if MUAM_MASTER_FALLBACK.exists():
            data = load_json(MUAM_MASTER_FALLBACK, {})
            raw_funds = data.get("datasets", {}).get("api00001tmCmFndSearchDetailOutDto", [])
            logger.info("Stage1 (MUAM): Loaded {} funds from bundled master database", len(raw_funds))
        else:
            raise RuntimeError(f"MUAM API access failed ({exc}) and no local database found.") from exc

    funds: list[Fund] = []
    for item in raw_funds:
        fund_code = str(item.get("cfsd_fund_cd", "")).strip()
        fund_name = str(item.get("cfsd_fund_name", "")).strip()
        if not fund_code or not fund_name:
            continue

        net_asset = float(item.get("cfsd_net_asset_value") or 0.0)
        nav = float(item.get("cfsd_purchase_or_base_price") or 0.0)
        isin = item.get("cfsd_isin_cd")
        is_etf = bool(item.get("cfs_etc_type_etf") == 1) or ("ETF" in fund_name) or ("MAXIS" in fund_name)
        detail_url = f"https://www.am.mufg.jp/fund/{fund_code}.html"
        prospectus_url = f"https://www.am.mufg.jp/pdf/koumokuromi/{fund_code}.pdf"

        funds.append(Fund(
            fund_name=fund_name,
            fund_code=fund_code,
            nam_code=fund_code,
            isin_code=isin,
            aum=net_asset,
            nav=nav,
            is_etf=is_etf,
            detail_url=detail_url,
            prospectus_pdf_url=prospectus_url,
        ))

    # AUM降順ソート
    funds.sort(key=lambda x: x.aum or 0.0, reverse=True)
    selected = funds[:max_funds]
    logger.info("Stage1 (MUAM): Selected top {} funds (Max AUM: {:.1f}億円)", len(selected), (selected[0].aum or 0) / 1e8)

    save_json(target_out, [f.model_dump(mode="json") for f in selected])
    return selected
