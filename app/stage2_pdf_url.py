from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from loguru import logger

from app.config import FUND_DETAIL_BASE, FUNDS_JSON, MAX_WORKERS, PROSPECTUS_URL_TEMPLATE
from app.http_client import HttpClient, load_json, save_json
from app.models import Fund


def _candidate_urls(nam_code: str) -> list[str]:
    return [
        PROSPECTUS_URL_TEMPLATE.format(nam_code=nam_code),
        f"https://www.nomura-am.co.jp/fund/pros_gen/Y2{nam_code}.pdf",
    ]


def _url_exists(client: HttpClient, url: str) -> bool:
    response = client.head(url)
    if response.status_code >= 400:
        return False
    content_type = response.headers.get("Content-Type", "").lower()
    return "pdf" in content_type or url.lower().endswith(".pdf")


def _scrape_detail_page(client: HttpClient, detail_url: str) -> str | None:
    response = client.get(detail_url, timeout=30)
    matches = re.findall(
        r'href="([^"]+\.pdf)"[^>]*>\s*(?:<[^>]+>\s*)*交付目論見書',
        response.text,
        flags=re.I,
    )
    if not matches:
        matches = re.findall(
            r'href="(\./pros_gen/Y1\d+\.pdf)"',
            response.text,
            flags=re.I,
        )
    if not matches:
        return None
    href = matches[0]
    return urljoin(detail_url, href)


def resolve_prospectus_url(
    fund: Fund,
    client: HttpClient | None = None,
) -> str | None:
    client = client or HttpClient()
    if fund.nam_code:
        for url in _candidate_urls(fund.nam_code):
            try:
                if _url_exists(client, url):
                    return url
            except Exception as exc:
                logger.debug("HEAD failed for {}: {}", url, exc)

    if fund.detail_url:
        try:
            return _scrape_detail_page(client, fund.detail_url)
        except Exception as exc:
            logger.warning("Failed to scrape detail page for {}: {}", fund.fund_code, exc)
    return None


def _resolve_single_worker(fund: Fund, force: bool) -> tuple[Fund, str | None]:
    if fund.prospectus_pdf_url and not force:
        return fund, fund.prospectus_pdf_url
    client = HttpClient()
    url = resolve_prospectus_url(fund, client)
    return fund, url


def run_stage2(*, force: bool = False, max_workers: int = MAX_WORKERS) -> list[Fund]:
    raw = load_json(FUNDS_JSON, [])
    if not raw:
        raise RuntimeError("Stage2 requires funds.json. Run stage1 first.")
    funds = [Fund.model_validate(item) for item in raw]

    updated = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_resolve_single_worker, fund, force): fund
            for fund in funds
        }
        for future in as_completed(futures):
            fund, url = future.result()
            fund.prospectus_pdf_url = url
            if url:
                updated += 1
                logger.info("Stage2: {} -> {}", fund.fund_code, url)
            else:
                logger.warning("Stage2: prospectus URL not found for {}", fund.fund_name)

    save_json(FUNDS_JSON, [fund.model_dump(mode="json") for fund in funds])
    logger.info("Stage2: resolved {} / {} prospectus URLs", updated, len(funds))
    return funds

