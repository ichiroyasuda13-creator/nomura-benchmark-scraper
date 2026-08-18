from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz
from loguru import logger

from app.config import FUNDS_JSON, MAX_WORKERS, OCR_MIN_CHARS_PER_PAGE, PDF_DIR, TEXT_DIR
from app.http_client import load_json
from app.models import Fund


def _count_japanese_chars(text: str) -> int:
    return len(re.findall(r"[一-龥ぁ-んァ-ン]", text))


def _needs_ocr(text: str, page_count: int) -> bool:
    if page_count <= 0:
        return True
    stripped = text.strip()
    if len(stripped) < page_count * OCR_MIN_CHARS_PER_PAGE:
        return True
    if _count_japanese_chars(stripped) < max(20, page_count * 10):
        return True
    return False


def _extract_with_pymupdf(pdf_path: Path) -> tuple[str, int]:
    doc = fitz.open(pdf_path)
    try:
        pages = [page.get_text("text") for page in doc]
        return "\n".join(pages), doc.page_count
    finally:
        doc.close()


def _extract_with_ocr(
    pdf_path: Path,
    *,
    max_pages: int = 3,
    dpi: int = 150,
) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        logger.warning("OCR dependencies missing: {}", exc)
        return ""

    try:
        images = convert_from_path(
            str(pdf_path),
            first_page=1,
            last_page=max_pages,
            dpi=dpi,
        )
    except Exception as exc:
        logger.warning("Failed to render PDF for OCR: {}", exc)
        return ""

    chunks: list[str] = []
    for image in images:
        try:
            text = pytesseract.image_to_string(image, lang="jpn")
            chunks.append(text)
        except Exception as ocr_err:
            logger.warning("Tesseract OCR failed: {}", ocr_err)
    return "\n".join(chunks)



def extract_ocr_pages(
    pdf_path: Path,
    *,
    max_pages: int = 3,
    dpi: int = 300,
) -> str:
    """Force OCR on the first N pages regardless of embedded text quality."""
    logger.info("Stage4: forced OCR for {} (max_pages={})", pdf_path.name, max_pages)
    return _extract_with_ocr(pdf_path, max_pages=max_pages, dpi=dpi)


def extract_text_from_pdf(
    pdf_path: Path,
    *,
    allow_ocr: bool = True,
) -> tuple[str, bool]:
    text, page_count = _extract_with_pymupdf(pdf_path)
    if not _needs_ocr(text, page_count):
        return text, False
    if not allow_ocr:
        logger.warning("Low-quality text in {} and OCR disabled", pdf_path.name)
        return text, False
    logger.info("Stage4: OCR fallback for {}", pdf_path.name)
    return _extract_with_ocr(pdf_path), True


def extract_text_for_fund(
    fund: Fund,
    *,
    force: bool = False,
    allow_ocr: bool = True,
) -> Path | None:
    pdf_path = PDF_DIR / f"{fund.fund_code}.pdf"
    if not pdf_path.exists():
        logger.warning("Stage4: PDF missing for {}", fund.fund_code)
        return None

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_path = TEXT_DIR / f"{fund.fund_code}.txt"
    if text_path.exists() and not force:
        return text_path

    text, used_ocr = extract_text_from_pdf(pdf_path, allow_ocr=allow_ocr)
    header = f"# fund_code={fund.fund_code}\n# ocr={'yes' if used_ocr else 'no'}\n\n"
    text_path.write_text(header + text, encoding="utf-8")
    logger.info("Stage4: wrote text for {} (ocr={})", fund.fund_code, used_ocr)
    return text_path


def run_stage4(*, force: bool = False, allow_ocr: bool = True, max_workers: int = MAX_WORKERS) -> list[Path]:
    raw = load_json(FUNDS_JSON, [])
    if not raw:
        raise RuntimeError("Stage4 requires funds.json. Run stage1 first.")
    funds = [Fund.model_validate(item) for item in raw]
    outputs: list[Path] = []

    def _worker(fund: Fund) -> Path | None:
        return extract_text_for_fund(fund, force=force, allow_ocr=allow_ocr)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, fund): fund for fund in funds}
        for future in as_completed(futures):
            path = future.result()
            if path:
                outputs.append(path)

    logger.info("Stage4: {} text files available", len(outputs))
    return outputs

