from __future__ import annotations

import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseModel, Field, validator
    _PYDANTIC_V2 = False

    def field_validator(*fields: str, mode: str = "after", **kwargs: Any):
        pre = (mode == "before")
        return validator(*fields, pre=pre, allow_reuse=True, **kwargs)


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


class CompatibleBaseModel(BaseModel):
    """Base model with dual Pydantic v1/v2 compatibility."""

    @classmethod
    def model_validate(cls, obj: Any) -> Any:
        if hasattr(cls, "parse_obj") and not _PYDANTIC_V2:
            return cls.parse_obj(obj)
        try:
            return super().model_validate(obj)
        except AttributeError:
            return cls.parse_obj(obj)

    def model_dump(self, mode: str = "python", **kwargs: Any) -> dict[str, Any]:
        if hasattr(super(), "model_dump") and _PYDANTIC_V2:
            return super().model_dump(mode=mode, **kwargs)
        return self.dict(**kwargs)


class Fund(CompatibleBaseModel):
    fund_name: str
    fund_code: str
    nam_code: str = ""
    management_company: str = "野村アセットマネジメント"
    aum: float = 0.0
    aum_display: str = ""
    aum_date: Optional[date] = None
    nav: float = 0.0
    detail_url: str = ""
    is_etf: bool = False
    prospectus_pdf_url: Optional[str] = None
    rank: Optional[int] = None
    isin_code: Optional[str] = None

    @field_validator("detail_url")
    @classmethod
    def normalize_detail_url(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("//"):
            return "https:" + value
        return value or ""


class BenchmarkExtraction(CompatibleBaseModel):
    fund_type: FundType = FundType.UNKNOWN
    benchmark: Optional[str] = None
    benchmark_detail: Optional[str | dict[str, Any]] = None
    index_provider: str = "なし"
    is_msci: bool = False
    reference_index: Optional[str] = None
    confidence: Confidence = Confidence.LOW
    extraction_method: ExtractionMethod = ExtractionMethod.RULE
    theme_category: str = "全世界・先進国株式"
    top_distributors: str = ""
    primary_broker: str = ""
    estimated_net_inflow: float = 0.0
    performance_effect: float = 0.0
    aum_change: float = 0.0
    sales_pitch_action: str = ""
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


class BenchmarkRecord(CompatibleBaseModel):
    rank: int
    management_company: str = "野村アセットマネジメント"
    fund_name: str
    fund_code: str
    nam_code: str = ""
    isin_code: Optional[str] = None
    aum: float = 0.0
    aum_date: Optional[date] = None
    nav: float = 0.0
    is_etf: bool = False
    fund_type: FundType = FundType.UNKNOWN
    theme_category: str = "全世界・先進国株式"
    benchmark: Optional[str] = None
    benchmark_detail: Optional[str] = None
    index_provider: str = "なし"
    is_msci: bool = False
    reference_index: Optional[str] = None
    confidence: Confidence = Confidence.LOW
    extraction_method: ExtractionMethod = ExtractionMethod.RULE
    estimated_net_inflow: float = 0.0
    performance_effect: float = 0.0
    aum_change: float = 0.0
    top_distributors: str = ""
    primary_broker: str = ""
    sales_pitch_action: str = ""
    prospectus_pdf_url: Optional[str] = None
    source_page_detail_url: str = ""
    note: str = ""
    needs_review: bool = True
    manual_override: bool = False
    review_comment: str = ""
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None

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
            management_company=fund.management_company or "野村アセットマネジメント",
            fund_name=fund.fund_name,
            fund_code=fund.fund_code,
            nam_code=fund.nam_code,
            isin_code=fund.isin_code,
            aum=fund.aum,
            aum_date=fund.aum_date,
            nav=fund.nav,
            is_etf=fund.is_etf,
            fund_type=extraction.fund_type,
            theme_category=extraction.theme_category or "全世界・先進国株式",
            benchmark=benchmark,
            benchmark_detail=detail_str,
            index_provider=extraction.index_provider,
            is_msci=extraction.is_msci,
            reference_index=extraction.reference_index,
            confidence=extraction.confidence,
            extraction_method=extraction.extraction_method,
            estimated_net_inflow=extraction.estimated_net_inflow,
            performance_effect=extraction.performance_effect,
            aum_change=extraction.aum_change,
            top_distributors=extraction.top_distributors,
            primary_broker=extraction.primary_broker,
            sales_pitch_action=extraction.sales_pitch_action,
            prospectus_pdf_url=fund.prospectus_pdf_url,
            source_page_detail_url=fund.detail_url,
            note=extraction.note,
            needs_review=extraction.needs_review,
            manual_override=False,
            review_comment="",
            reviewed_at=None,
            reviewed_by=None,
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


def format_aum_oku(aum: float) -> str:
    """Format AUM in 億円 (hundred million yen) or 兆円."""
    if not aum:
        return "—"
    oku = aum / 1e8
    if abs(oku) >= 10000:
        cho = oku / 10000
        return f"{cho:,.1f}兆円"
    return f"{oku:,.0f}億円"


def format_inflow_oku(flow: float) -> str:
    """Format Net Inflow with +/- sign in 億円 (hundred million yen)."""
    if flow == 0:
        return "±0億円"
    oku = flow / 1e8
    sign = "+" if oku > 0 else ""
    if abs(oku) >= 10000:
        cho = oku / 10000
        return f"{sign}{cho:,.1f}兆円"
    return f"{sign}{oku:,.0f}億円"
