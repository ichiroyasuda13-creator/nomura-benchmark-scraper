"""Stage 1 for Daiwa Asset Management: Fetch funds list sorted by AUM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import httpx
from loguru import logger

from app.config import DATA_DIR, FUNDS_JSON
from app.http_client import load_json, save_json
from app.models import Fund

DAIWA_SEARCH_API = "https://www.daiwa-am.co.jp/include/fund_search.json"
DAIWA_MASTER_FALLBACK = DATA_DIR / "daiwa_funds_master.json"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.daiwa-am.co.jp/funds/search/index.html",
    "Origin": "https://www.daiwa-am.co.jp",
}


def run_stage1_daiwa(
    force: bool = False,
    max_funds: int = 100,
    output_path: Optional[Path] = None,
) -> list[Fund]:
    """大和アセットマネジメントの公式JSONからAUM降順でファンド一覧を取得."""
    target_out = output_path or FUNDS_JSON
    logger.info("Stage1 (Daiwa): Fetching funds from {}", DAIWA_SEARCH_API)

    raw_funds = []
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=15.0) as client:
            resp = client.get(DAIWA_SEARCH_API)
            resp.raise_for_status()
            data = resp.json()
            raw_funds = data.get("fund", [])
            logger.info("Stage1 (Daiwa): Successfully fetched {} funds from live API", len(raw_funds))
    except Exception as exc:
        logger.warning("Stage1 (Daiwa): Live API request failed ({}). Attempting local fallback...", exc)
        if DAIWA_MASTER_FALLBACK.exists():
            data = load_json(DAIWA_MASTER_FALLBACK, {})
            raw_funds = data.get("fund", [])
            logger.info("Stage1 (Daiwa): Loaded {} funds from bundled master database", len(raw_funds))
        else:
            raise RuntimeError(f"Daiwa AM API access failed ({exc}) and no local database found.") from exc

    funds: list[Fund] = []
    for item in raw_funds:
        fund_code = str(item.get("fund_code", "")).strip()
        details = item.get("details", {})
        if not fund_code or not details:
            continue

        fund_name = details.get("fund_name", "").strip()
        net_asset = float(details.get("netasset_value") or 0.0)
        nav = float(details.get("base_value") or 0.0)
        is_etf = bool(details.get("etf_flg", False)) or ("ETF" in fund_name) or ("上場投信" in fund_name)
        detail_link = details.get("fund_detail_link") or f"/funds/detail/{fund_code}/detail_top.html"
        detail_url = f"https://www.daiwa-am.co.jp{detail_link}"

        doc_link = details.get("mokuromi_report")
        prospectus_url = (
            f"https://www.daiwa-am.co.jp{doc_link}"
            if doc_link
            else f"https://www.daiwa-am.co.jp/funds/doc_open/fund_doc_open.php?code={fund_code}&type=1"
        )

        def _to_float(val: Any) -> float | None:
            if val is None or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        funds.append(Fund(
            fund_name=fund_name,
            fund_code=fund_code,
            nam_code=fund_code,
            management_company="大和アセットマネジメント",
            aum=net_asset,
            nav=nav,
            is_etf=is_etf,
            detail_url=detail_url,
            prospectus_pdf_url=prospectus_url,
            return_1m=_to_float(details.get("rate_1month")),
            return_3m=_to_float(details.get("rate_3month")),
            return_6m=_to_float(details.get("rate_6month")),
            return_1y=_to_float(details.get("rate_1year")),
        ))

    # AUM降順ソート
    funds.sort(key=lambda x: x.aum or 0.0, reverse=True)
    selected = funds[:max_funds]
    logger.info("Stage1 (Daiwa): Selected top {} funds", len(selected))

    save_json(target_out, [f.model_dump(mode="json") for f in selected])

    from app.timeseries_store import append_snapshot
    from datetime import date as dt_date
    today_str = dt_date.today().isoformat()
    for f in selected:
        append_snapshot(
            fund_code=f.fund_code,
            date=today_str,
            aum=f.aum,
            nav=f.nav,
        )

    return selected

