from __future__ import annotations

import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FundType(str, Enum):
    INDEX = "インデックス"
    ACTIVE = "アクティブ"
    ACTIVE_NO_BM = "アクティブ（BMなし）"
    BALANCE_COMPOSITE = "バランス（複合BM）"
    UNKNOWN = "不明"


class ExtractionMethod(str, Enum):
    RULE = "rule"
    LLM = "llm"
    OCR = "ocr"
    OCR_LLM = "ocr+llm"
    RULE_LLM = "rule+llm"
    NAME_FALLBACK = "name_fallback"


class Fund(BaseModel):
    fund_name: str
    fund_code: str
    nam_code: str = ""
    aum: float = 0.0
    aum_display: str = ""
    aum_date: Optional[date] = None
    detail_url: str = ""
    is_etf: bool = False
    prospectus_pdf_url: Optional[str] = None
    rank: Optional[int] = None

    @field_validator("detail_url")
    @classmethod
    def normalize_detail_url(cls, value: str) -> str:
        if value.startswith("//"):
            return "https:" + value
        return value


class BenchmarkExtraction(BaseModel):
    fund_type: FundType = FundType.UNKNOWN
    benchmark: Optional[str] = None
    benchmark_detail: Optional[str | dict[str, Any]] = None
    index_provider: str = "なし"
    is_msci: bool = False
    reference_index: Optional[str] = None
    confidence: Confidence = Confidence.LOW
    extraction_method: ExtractionMethod = ExtractionMethod.RULE
    note: str = ""
    needs_review: bool = True

    @field_validator("benchmark_detail", mode="before")
    @classmethod
    def normalize_benchmark_detail(cls, value: Any) -> Optional[str | dict[str, Any]]:
        if value is None or value == "":
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("{"):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
            return text
        return str(value)


class BenchmarkRecord(BaseModel):
    rank: int
    fund_name: str
    fund_code: str
    aum: float
    aum_date: Optional[date] = None
    is_etf: bool = False
    fund_type: FundType = FundType.UNKNOWN
    benchmark: Optional[str] = None
    benchmark_detail: Optional[str] = None
    index_provider: str = "なし"
    is_msci: bool = False
    reference_index: Optional[str] = None
    confidence: Confidence = Confidence.LOW
    extraction_method: ExtractionMethod = ExtractionMethod.RULE
    prospectus_pdf_url: Optional[str] = None
    source_page_detail_url: str = ""
    note: str = ""
    needs_review: bool = True

    @classmethod
    def from_fund(
        cls,
        fund: Fund,
        extraction: BenchmarkExtraction,
    ) -> "BenchmarkRecord":
        detail = extraction.benchmark_detail
        if isinstance(detail, dict):
            detail_str = json.dumps(detail, ensure_ascii=False)
        else:
            detail_str = detail

        benchmark = extraction.benchmark
        if benchmark is None and extraction.fund_type == FundType.ACTIVE_NO_BM:
            benchmark = "なし"

        return cls(
            rank=fund.rank or 0,
            fund_name=fund.fund_name,
            fund_code=fund.fund_code,
            aum=fund.aum,
            aum_date=fund.aum_date,
            is_etf=fund.is_etf,
            fund_type=extraction.fund_type,
            benchmark=benchmark,
            benchmark_detail=detail_str,
            index_provider=extraction.index_provider,
            is_msci=extraction.is_msci,
            reference_index=extraction.reference_index,
            confidence=extraction.confidence,
            extraction_method=extraction.extraction_method,
            prospectus_pdf_url=fund.prospectus_pdf_url,
            source_page_detail_url=fund.detail_url,
            note=extraction.note,
            needs_review=extraction.needs_review,
        )


def parse_japanese_date(value: str) -> Optional[date]:
    if not value:
        return None
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    return date(year, month, day)


def parse_aum_yen(raw: float | int | str | None) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).replace(",", "").strip()
    if not text:
        return 0.0
    return float(text)
