from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from app.config import BENCHMARKS_JSON, OUTPUT_DIR
from app.http_client import load_json
from app.models import BenchmarkRecord


OUTPUT_COLUMNS = [
    "rank",
    "fund_name",
    "fund_code",
    "aum",
    "aum_date",
    "is_etf",
    "fund_type",
    "benchmark",
    "benchmark_detail",
    "index_provider",
    "is_msci",
    "reference_index",
    "confidence",
    "extraction_method",
    "prospectus_pdf_url",
    "source_page_detail_url",
    "note",
    "needs_review",
]


def records_to_dataframe(records: list[BenchmarkRecord]) -> pd.DataFrame:
    rows = [record.model_dump(mode="json") for record in records]
    frame = pd.DataFrame(rows)
    for column in OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[OUTPUT_COLUMNS]


def run_stage6(records: list[BenchmarkRecord] | None = None) -> tuple[Path, Path]:
    if records is None:
        raw = load_json(BENCHMARKS_JSON, [])
        records = [BenchmarkRecord.model_validate(item) for item in raw]
    if not records:
        raise RuntimeError("Stage6 requires benchmark records. Run stage5 first.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = records_to_dataframe(records)
    csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"
    xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"

    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    frame.to_excel(xlsx_path, index=False, sheet_name="benchmarks")
    logger.info("Stage6: wrote {} and {}", csv_path, xlsx_path)
    return csv_path, xlsx_path
