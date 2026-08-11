from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
TEXT_DIR = DATA_DIR / "text"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = PROJECT_ROOT / "logs"
FUNDS_JSON = DATA_DIR / "funds.json"
BENCHMARKS_JSON = DATA_DIR / "benchmarks.json"

USER_AGENT = os.getenv(
    "NOMURA_USER_AGENT",
    "NomuraBenchmarkScraper/1.0 (internal research; contact: internal)",
)
REQUEST_DELAY_SEC = float(os.getenv("NOMURA_REQUEST_DELAY_SEC", "1.5"))
MAX_FUNDS = int(os.getenv("NOMURA_MAX_FUNDS", "100"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

FUND_SEARCH_API = (
    "https://fund.nomura-am.co.jp/nomura/cgi/wrap/qjsonp.aspx?F=ctl/fund_search"
)
FUND_DETAIL_BASE = "https://www.nomura-am.co.jp"
PROSPECTUS_URL_TEMPLATE = (
    "https://www.nomura-am.co.jp/fund/pros_gen/Y1{nam_code}.pdf"
)

OCR_MIN_CHARS_PER_PAGE = int(os.getenv("NOMURA_OCR_MIN_CHARS_PER_PAGE", "80"))


def ensure_dirs() -> None:
    for path in (DATA_DIR, PDF_DIR, TEXT_DIR, OUTPUT_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
