"""Nomura Distributor Master Data Ingestion & Caching.

Fetches and caches the official distributor code-to-name master list from Nomura AM API:
https://fund.nomura-am.co.jp/nomura/cgi/wrap/qjsonp.aspx?F=ctl/fund_company
"""

from __future__ import annotations

import re
from typing import Any
from loguru import logger

from app.config import DATA_DIR
from app.http_client import HttpClient, load_json, save_json

DISTRIBUTOR_MASTER_URL = "https://fund.nomura-am.co.jp/nomura/cgi/wrap/qjsonp.aspx?F=ctl/fund_company"
DISTRIBUTOR_MASTER_CACHE = DATA_DIR / "distributor_master.json"


def _parse_jsonp(text: str) -> dict[str, Any]:
    import json
    match = re.match(r"^[^(]+\((.*)\)\s*$", text, re.S)
    if not match:
        raise ValueError("Unexpected JSONP response format")
    return json.loads(match.group(1))


def fetch_distributor_master(force: bool = False) -> dict[str, dict[str, Any]]:
    """Fetch and return the distributor master dictionary mapping CompanyCode to company metadata."""
    if DISTRIBUTOR_MASTER_CACHE.exists() and not force:
        cached = load_json(DISTRIBUTOR_MASTER_CACHE, {})
        if cached:
            return cached

    logger.info("Fetching distributor master from Nomura API")
    client = HttpClient()
    try:
        response = client.get(DISTRIBUTOR_MASTER_URL, timeout=30)
        payload = _parse_jsonp(response.text)
        data_list = payload.get("section1", {}).get("data", []) or payload.get("data", [])
        master: dict[str, dict[str, Any]] = {}
        for item in data_list:
            code = str(item.get("CompanyCode", "")).strip()
            if code:
                master[code] = {
                    "CompanyCode": code,
                    "CompanyName": str(item.get("CompanyName", "")).strip(),
                    "CompanyNameKana": str(item.get("CompanyNameKana", "")).strip(),
                    "CompanyType": str(item.get("CompanyType", "")).strip(),
                }
        if master:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            save_json(DISTRIBUTOR_MASTER_CACHE, master)
            logger.info("Saved {} distributors to {}", len(master), DISTRIBUTOR_MASTER_CACHE)
            return master
    except Exception as exc:
        logger.warning("Failed to fetch distributor master: {}. Attempting cache fallback.", exc)

    if DISTRIBUTOR_MASTER_CACHE.exists():
        return load_json(DISTRIBUTOR_MASTER_CACHE, {})

    return {}
