from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.config import FUND_SEARCH_API, FUNDS_JSON, MAX_FUNDS
from app.http_client import HttpClient, load_json, save_json
from app.models import Fund, parse_aum_yen, parse_japanese_date


def _parse_jsonp(text: str) -> dict[str, Any]:
    match = re.match(r"^[^(]+\((.*)\)\s*$", text, re.S)
    if not match:
        raise ValueError("Unexpected JSONP response format")
    return json.loads(match.group(1))


def _is_etf(raw: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(raw.get(key, ""))
        for key in ("FundName", "CategoryName", "CNDKeyword")
    )
    return "ETF" in haystack.upper() or "ＥＴＦ" in haystack


def _normalize_detail_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def _extract_nam_code(raw: dict[str, Any]) -> str:
    if raw.get("NAMCode"):
        return str(raw["NAMCode"])
    detail_url = _normalize_detail_url(str(raw.get("DetailUrl", "")))
    match = re.search(r"fundcd=(\d+)", detail_url)
    return match.group(1) if match else ""


def fetch_all_funds(client: HttpClient | None = None) -> list[dict[str, Any]]:
    client = client or HttpClient()
    response = client.get(
        FUND_SEARCH_API,
        params={"KEY1": "", "KEY2": ""},
        timeout=120,
    )
    payload = _parse_jsonp(response.text)
    section = payload.get("section1", {})
    if section.get("status") != 0:
        raise RuntimeError(f"Fund search API failed: status={section.get('status')}")
    return section.get("data") or []


def raw_to_fund(raw: dict[str, Any], rank: int) -> Fund:
    aum = parse_aum_yen(raw.get("SRTTotalNetAsset"))
    return Fund(
        fund_name=str(raw.get("FundName", "")).strip(),
        fund_code=str(raw.get("FundCode", "")).strip(),
        nam_code=_extract_nam_code(raw),
        aum=aum,
        aum_display=str(raw.get("TotalNetAsset", "")).strip(),
        aum_date=parse_japanese_date(str(raw.get("ReferenceDate", ""))),
        detail_url=_normalize_detail_url(str(raw.get("DetailUrl", ""))),
        is_etf=_is_etf(raw),
        rank=rank,
    )


def run_stage1(*, force: bool = False, max_funds: int = MAX_FUNDS) -> list[Fund]:
    if FUNDS_JSON.exists() and not force:
        cached = load_json(FUNDS_JSON, [])
        if cached:
            logger.info("Stage1: using cached {}", FUNDS_JSON)
            return [Fund.model_validate(item) for item in cached]

    logger.info("Stage1: fetching fund list from Nomura API")
    client = HttpClient()
    raw_funds = fetch_all_funds(client)
    sorted_funds = sorted(
        raw_funds,
        key=lambda item: parse_aum_yen(item.get("SRTTotalNetAsset")),
        reverse=True,
    )
    top = sorted_funds[:max_funds]
    funds = [raw_to_fund(raw, rank=index + 1) for index, raw in enumerate(top)]
    save_json(FUNDS_JSON, [fund.model_dump(mode="json") for fund in funds])
    logger.info("Stage1: saved {} funds to {}", len(funds), FUNDS_JSON)
    return funds
