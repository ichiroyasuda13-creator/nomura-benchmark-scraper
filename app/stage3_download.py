from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger

from app.config import FUNDS_JSON, MAX_WORKERS, PDF_DIR
from app.http_client import HttpClient, load_json
from app.models import Fund


def download_pdf(
    fund: Fund,
    client: HttpClient | None = None,
    *,
    force: bool = False,
) -> Path | None:
    if not fund.prospectus_pdf_url:
        logger.warning("Stage3: missing prospectus URL for {}", fund.fund_code)
        return None

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    target = PDF_DIR / f"{fund.fund_code}.pdf"
    if target.exists() and not force:
        logger.debug("Stage3: cache hit {}", target)
        return target

    client = client or HttpClient()
    response = client.get(fund.prospectus_pdf_url, timeout=120, stream=True)
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)
    logger.info("Stage3: downloaded {}", target.name)
    return target


def run_stage3(*, force: bool = False, max_workers: int = MAX_WORKERS) -> list[Path]:
    raw = load_json(FUNDS_JSON, [])
    if not raw:
        raise RuntimeError("Stage3 requires funds.json. Run stage1 first.")
    funds = [Fund.model_validate(item) for item in raw]
    downloaded: list[Path] = []

    def _worker(fund: Fund) -> Path | None:
        client = HttpClient()
        return download_pdf(fund, client, force=force)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, fund): fund for fund in funds}
        for future in as_completed(futures):
            path = future.result()
            if path:
                downloaded.append(path)

    logger.info("Stage3: {} PDFs available", len(downloaded))
    return downloaded

