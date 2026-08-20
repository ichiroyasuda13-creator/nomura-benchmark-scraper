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

def _get_secret(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


USER_AGENT = _get_secret(
    "NOMURA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
REQUEST_DELAY_SEC = float(_get_secret("NOMURA_REQUEST_DELAY_SEC", "0.5"))
MAX_FUNDS = int(_get_secret("NOMURA_MAX_FUNDS", "100"))
MAX_WORKERS = int(_get_secret("NOMURA_MAX_WORKERS", "5"))

# LLM Configurations
LLM_PROVIDER = _get_secret("LLM_PROVIDER", "auto").lower()  # auto, anthropic, openai, gemini, ollama

# Anthropic Claude
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = _get_secret("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

# OpenAI
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY", "")
OPENAI_MODEL = _get_secret("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = _get_secret("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Google Gemini
GEMINI_API_KEY = _get_secret("GEMINI_API_KEY", "")
GEMINI_MODEL = _get_secret("GEMINI_MODEL", "gemini-2.0-flash")

# Ollama / Local LLM
OLLAMA_BASE_URL = _get_secret("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _get_secret("OLLAMA_MODEL", "llama3.2")


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

