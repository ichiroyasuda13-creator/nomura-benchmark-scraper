from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import BENCHMARKS_JSON, FUNDS_JSON, PDF_DIR, TEXT_DIR
from app.http_client import load_json, save_json
from app.llm import extract_with_llm, llm_available
from app.models import (
    BenchmarkExtraction,
    BenchmarkRecord,
    Confidence,
    ExtractionMethod,
    Fund,
    FundType,
)
from app.distributors import resolve_fund_distributors
from app.flow_calculator import estimate_fund_flow_from_returns
from app.theme_classifier import classify_fund_theme
from app.providers import (
    BENCHMARK_CANDIDATE_PATTERNS,
    NEGATIVE_BENCHMARK_PATTERNS,
    REFERENCE_INDEX_PATTERNS,
    SECTION_PATTERNS,
    clean_index_name,
    detect_index_provider,
    extract_from_fund_name,
    has_rendou_trigger,
    is_index_like_fund_name,
    is_money_market_fund,
    is_msci_benchmark,
    is_valid_benchmark_name,
    parse_composite_components,
    prioritize_candidates,
)



def _strip_header(text: str) -> str:
    lines = text.splitlines()
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


def extract_relevant_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for name, pattern in SECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            sections[name] = match.group(0).strip()
    if not sections:
        sections["full"] = text[:12000]
    return sections


def _detect_negative_benchmark(text: str) -> bool:
    return any(pattern.search(text) for pattern in NEGATIVE_BENCHMARK_PATTERNS)


def _detect_reference_index(text: str) -> str | None:
    for pattern in REFERENCE_INDEX_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = clean_index_name(match.group(1))
            if candidate:
                return candidate
    return None


def _normalize_extraction_text(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _rule_extract_candidates(text: str) -> list[str]:
    normalized = _normalize_extraction_text(text)
    candidates: list[str] = []
    for pattern in BENCHMARK_CANDIDATE_PATTERNS:
        for match in pattern.finditer(normalized):
            if match.lastindex is None:
                composite_chunk = match.group(0)
                parsed_components = parse_composite_components(composite_chunk)
                for comp in parsed_components:
                    candidate = comp["index"]
                    if candidate not in candidates:
                        candidates.append(candidate)
                continue
            candidate = clean_index_name(match.group(1))
            if len(candidate) < 2:
                continue
            if not is_valid_benchmark_name(candidate):
                continue
            if candidate not in candidates:
                candidates.append(candidate)
    return prioritize_candidates(candidates)


def _guess_fund_type(text: str, candidates: list[str], negative: bool) -> FundType:
    if negative:
        return FundType.ACTIVE_NO_BM
    if "複合ベンチマーク" in text or (
        any(key in text for key in ("マザーファンド", "資産配分", "バランス", "マイバランス"))
        and len(candidates) > 1
    ):
        return FundType.BALANCE_COMPOSITE
    if any(key in text for key in ("に連動", "連動する投資成果", "連動する運用成果", "インデックス型")) and candidates:
        if "複合ベンチマーク" in text or len(candidates) > 1:
            return FundType.BALANCE_COMPOSITE
        return FundType.INDEX
    if candidates:
        return FundType.ACTIVE
    if "インデックス" in text or "index" in text.lower():
        return FundType.INDEX
    return FundType.UNKNOWN


def _confidence_for_rule(benchmark: str | None, index_provider: str) -> Confidence:
    if not benchmark:
        return Confidence.LOW
    if index_provider not in {"なし", "複合"}:
        return Confidence.HIGH
    return Confidence.MEDIUM


def _build_rule_extraction(
    fund: Fund,
    sections: dict[str, str],
) -> BenchmarkExtraction:
    # 1. Check if fund is a money market fund / MRF
    if is_money_market_fund(fund.fund_name):
        return BenchmarkExtraction(
            fund_type=FundType.ACTIVE_NO_BM,
            benchmark="なし",
            index_provider="なし",
            is_msci=False,
            confidence=Confidence.HIGH,
            extraction_method=ExtractionMethod.RULE,
            note="短期金融資産・MRF（ベンチマーク非設定）",
            needs_review=False,
        )

    combined = "\n".join(sections.values())
    negative = _detect_negative_benchmark(combined)
    candidates = _rule_extract_candidates(combined)
    reference_index = _detect_reference_index(combined)
    fund_type = _guess_fund_type(combined, candidates, negative)

    if negative:
        return BenchmarkExtraction(
            fund_type=FundType.ACTIVE_NO_BM,
            benchmark="なし",
            index_provider="なし",
            is_msci=False,
            reference_index=reference_index,
            confidence=Confidence.HIGH,
            extraction_method=ExtractionMethod.RULE,
            note="否定表現を検出（ベンチマーク非設定）",
            needs_review=False,
        )

    benchmark = candidates[0] if candidates else None
    composite = fund_type == FundType.BALANCE_COMPOSITE or len(candidates) > 1

    benchmark_detail: dict[str, Any] | None = None
    if composite and candidates:
        parsed = parse_composite_components(combined)
        if parsed:
            benchmark_detail = {"components": parsed}
            formatted_parts = [
                f"{c['weight']}%×{c['index']}" if c.get("weight") else c['index']
                for c in parsed
            ]
            benchmark = " + ".join(formatted_parts[:4])
        else:
            benchmark_detail = {
                "components": [{"index": name} for name in candidates],
            }
            benchmark = " + ".join(candidates[:4])

    index_provider = detect_index_provider(benchmark, composite=composite)
    confidence = _confidence_for_rule(benchmark, index_provider)

    if fund_type == FundType.UNKNOWN and is_index_like_fund_name(
        fund.fund_name,
        is_etf=fund.is_etf,
    ):
        fund_type = FundType.INDEX

    return BenchmarkExtraction(
        fund_type=fund_type,
        benchmark=benchmark,
        benchmark_detail=benchmark_detail,
        index_provider=index_provider,
        is_msci=is_msci_benchmark(benchmark, index_provider),
        reference_index=reference_index,
        confidence=confidence,
        extraction_method=ExtractionMethod.RULE,
        note="" if benchmark else "ルールベースでベンチマーク候補未検出",
        needs_review=confidence != Confidence.HIGH,
    )


def _build_name_fallback_extraction(fund: Fund) -> BenchmarkExtraction | None:
    if is_money_market_fund(fund.fund_name):
        return BenchmarkExtraction(
            fund_type=FundType.ACTIVE_NO_BM,
            benchmark="なし",
            index_provider="なし",
            is_msci=False,
            confidence=Confidence.HIGH,
            extraction_method=ExtractionMethod.NAME_FALLBACK,
            note="短期金融資産・MRF（ベンチマーク非設定）",
            needs_review=False,
        )

    matched = extract_from_fund_name(fund.fund_name)
    if not matched:
        return None

    benchmark, provider = matched
    return BenchmarkExtraction(
        fund_type=FundType.INDEX,
        benchmark=benchmark,
        index_provider=provider,
        is_msci=is_msci_benchmark(benchmark, provider),
        confidence=Confidence.MEDIUM,
        extraction_method=ExtractionMethod.NAME_FALLBACK,
        note="本文未取得のため名称から推定",
        needs_review=True,
    )


def _benchmark_is_usable(extraction: BenchmarkExtraction) -> bool:
    if extraction.fund_type == FundType.ACTIVE_NO_BM:
        return True
    return is_valid_benchmark_name(extraction.benchmark)


def _should_force_ocr(
    fund: Fund,
    text: str,
    extraction: BenchmarkExtraction,
) -> bool:
    if _benchmark_is_usable(extraction):
        return False
    if extraction.fund_type == FundType.ACTIVE_NO_BM:
        return False

    index_like = (
        is_index_like_fund_name(fund.fund_name, is_etf=fund.is_etf)
        or extraction.fund_type == FundType.INDEX
        or has_rendou_trigger(text)
    )
    return index_like


def _finalize_extraction(
    extraction: BenchmarkExtraction,
    fund: Fund | None = None,
) -> BenchmarkExtraction:
    if extraction.confidence == Confidence.LOW:
        extraction.needs_review = True
    if extraction.benchmark and (
        not extraction.index_provider or extraction.index_provider == "なし"
    ):
        extraction.index_provider = detect_index_provider(
            extraction.benchmark,
            composite=extraction.fund_type == FundType.BALANCE_COMPOSITE,
        )
    extraction.is_msci = is_msci_benchmark(
        extraction.benchmark,
        extraction.index_provider,
    )

    if fund:
        extraction.theme_category = classify_fund_theme(fund.fund_name, extraction.benchmark or "")
        top_dist, primary, action = resolve_fund_distributors(
            fund.fund_name,
            fund.management_company,
            fund.is_etf,
        )
        aum_chg, perf, flow = estimate_fund_flow_from_returns(fund.aum)
        extraction.top_distributors = top_dist
        extraction.primary_broker = primary
        extraction.sales_pitch_action = action
        extraction.estimated_net_inflow = flow
        extraction.performance_effect = perf
        extraction.aum_change = aum_chg

    return extraction



def _apply_llm_if_needed(
    fund: Fund,
    sections: dict[str, str],
    current: BenchmarkExtraction,
    *,
    use_llm: bool,
    used_ocr: bool,
    provider: str | None = None,
    model: str | None = None,
) -> BenchmarkExtraction:
    if not use_llm or not llm_available(provider):
        return current
    if current.confidence == Confidence.HIGH and current.benchmark:
        return current

    llm_result = extract_with_llm(
        fund_name=fund.fund_name,
        section_text="\n\n".join(sections.values()),
        rule_hint=current.model_dump(mode="json"),
        provider=provider,
        model=model,
    )
    if not llm_result or not llm_result.benchmark:
        return current

    if used_ocr:
        llm_result.extraction_method = ExtractionMethod.OCR_LLM
    elif current.extraction_method == ExtractionMethod.RULE:
        llm_result.extraction_method = ExtractionMethod.RULE_LLM
    return _finalize_extraction(llm_result)


def _run_forced_ocr(
    fund: Fund,
    existing_text: str,
) -> tuple[str, bool]:
    pdf_path = PDF_DIR / f"{fund.fund_code}.pdf"
    if not pdf_path.exists():
        return existing_text, False

    try:
        from app.stage4_extract_text import extract_ocr_pages
    except ImportError:
        return existing_text, False

    try:
        ocr_text = extract_ocr_pages(pdf_path, max_pages=3, dpi=300)
    except Exception as exc:
        logger.warning("Stage5: forced OCR failed for {}: {}", fund.fund_code, exc)
        return existing_text, False

    if not ocr_text.strip():
        return existing_text, False

    combined = f"{ocr_text}\n\n{existing_text}"
    text_path = TEXT_DIR / f"{fund.fund_code}.txt"
    header = f"# fund_code={fund.fund_code}\n# ocr=yes\n\n"
    text_path.write_text(header + combined, encoding="utf-8")
    logger.info("Stage5: forced OCR text saved for {}", fund.fund_code)
    return combined, True


def extract_benchmark_for_fund(
    fund: Fund,
    *,
    use_llm: bool = True,
    provider: str | None = None,
    model: str | None = None,
    force_ocr: bool = False,
) -> BenchmarkRecord:
    text_path = TEXT_DIR / f"{fund.fund_code}.txt"
    if not text_path.exists():
        name_fallback = _build_name_fallback_extraction(fund)
        if name_fallback:
            return BenchmarkRecord.from_fund(fund, name_fallback)
        extraction = BenchmarkExtraction(
            fund_type=FundType.UNKNOWN,
            confidence=Confidence.LOW,
            note="テキストファイルなし",
            needs_review=True,
        )
        return BenchmarkRecord.from_fund(fund, extraction)

    raw_text = text_path.read_text(encoding="utf-8")
    text = _strip_header(raw_text)
    used_ocr = raw_text.startswith("# ocr=yes")

    if force_ocr:
        ocr_text, ocr_applied = _run_forced_ocr(fund, text)
        if ocr_applied:
            text = ocr_text
            used_ocr = True

    sections = extract_relevant_sections(text)
    final = _build_rule_extraction(fund, sections)
    final = _apply_llm_if_needed(
        fund,
        sections,
        final,
        use_llm=use_llm,
        used_ocr=used_ocr,
        provider=provider,
        model=model,
    )

    if not force_ocr and _should_force_ocr(fund, text, final):
        ocr_text, ocr_applied = _run_forced_ocr(fund, text)
        if ocr_applied:
            sections = extract_relevant_sections(ocr_text)
            ocr_rule = _build_rule_extraction(fund, sections)
            ocr_rule.extraction_method = ExtractionMethod.OCR
            if ocr_rule.benchmark and ocr_rule.confidence != Confidence.LOW:
                final = ocr_rule
            else:
                final = _apply_llm_if_needed(
                    fund,
                    sections,
                    ocr_rule,
                    use_llm=use_llm,
                    used_ocr=True,
                    provider=provider,
                    model=model,
                )

    if not final.benchmark and final.fund_type != FundType.ACTIVE_NO_BM:
        name_fallback = _build_name_fallback_extraction(fund)
        if name_fallback:
            final = name_fallback
    elif not _benchmark_is_usable(final) and final.fund_type != FundType.ACTIVE_NO_BM:
        name_fallback = _build_name_fallback_extraction(fund)
        if name_fallback:
            final = name_fallback

    if not final.benchmark and final.fund_type != FundType.ACTIVE_NO_BM:
        final.note = final.note or "全段階でベンチマーク未検出"
        final.confidence = Confidence.LOW
        final.needs_review = True

    final = _finalize_extraction(final, fund)
    return BenchmarkRecord.from_fund(fund, final)



def run_stage5(*, use_llm: bool = True, provider: str | None = None, model: str | None = None) -> list[BenchmarkRecord]:
    raw = load_json(FUNDS_JSON, [])
    if not raw:
        raise RuntimeError("Stage5 requires funds.json. Run stage1 first.")
    funds = [Fund.model_validate(item) for item in raw]
    records = [
        extract_benchmark_for_fund(fund, use_llm=use_llm, provider=provider, model=model)
        for fund in funds
    ]
    save_json(BENCHMARKS_JSON, [record.model_dump(mode="json") for record in records])
    logger.info("Stage5: extracted benchmarks for {} funds", len(records))
    return records


def reextract_single_fund(
    fund_code: str,
    *,
    use_llm: bool = True,
    provider: str | None = None,
    model: str | None = None,
    force_ocr: bool = False,
) -> BenchmarkRecord | None:
    """Re-extract benchmark for a single specific fund and update benchmarks.json."""
    raw_funds = load_json(FUNDS_JSON, [])
    matching_funds = [f for f in raw_funds if f.get("fund_code") == fund_code]
    if not matching_funds:
        logger.warning("Fund {} not found in {}", fund_code, FUNDS_JSON)
        return None

    fund = Fund.model_validate(matching_funds[0])
    new_record = extract_benchmark_for_fund(
        fund,
        use_llm=use_llm,
        provider=provider,
        model=model,
        force_ocr=force_ocr,
    )

    # Update in benchmarks.json
    raw_records = load_json(BENCHMARKS_JSON, [])
    updated = False
    new_list = []
    for r in raw_records:
        if r.get("fund_code") == fund_code:
            new_list.append(new_record.model_dump(mode="json"))
            updated = True
        else:
            new_list.append(r)

    if not updated:
        new_list.append(new_record.model_dump(mode="json"))

    save_json(BENCHMARKS_JSON, new_list)
    logger.info("Re-extracted and saved fund {}", fund_code)
    return new_record


def update_manual_override(
    fund_code: str,
    *,
    benchmark: str | None,
    index_provider: str,
    fund_type: str,
    needs_review: bool,
    comment: str = "",
    reviewer: str = "Analyst",
) -> BenchmarkRecord | None:
    """Manually edit/override benchmark data for a fund and persist."""
    raw_records = load_json(BENCHMARKS_JSON, [])
    updated_record: BenchmarkRecord | None = None
    new_list = []

    for r in raw_records:
        if r.get("fund_code") == fund_code:
            rec = BenchmarkRecord.model_validate(r)
            rec.benchmark = benchmark
            rec.index_provider = index_provider
            try:
                rec.fund_type = FundType(fund_type)
            except ValueError:
                pass
            rec.needs_review = needs_review
            rec.manual_override = True
            rec.review_comment = comment
            rec.reviewed_at = datetime.now()
            rec.reviewed_by = reviewer
            rec.is_msci = is_msci_benchmark(rec.benchmark, rec.index_provider)
            rec.confidence = Confidence.HIGH if not needs_review else rec.confidence
            updated_record = rec
            new_list.append(rec.model_dump(mode="json"))
        else:
            new_list.append(r)

    if updated_record:
        save_json(BENCHMARKS_JSON, new_list)
        logger.info("Saved manual override for fund {}", fund_code)
    return updated_record

