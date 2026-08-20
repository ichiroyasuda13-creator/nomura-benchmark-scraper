"""Prospectus Text Distributor Extractor for Daiwa and MUAM.

Extracts selling brokerages, banks, and designated participants directly from
prospectus text (交付目論見書) using high-precision rule-based parsing with LLM fallback.
"""

from __future__ import annotations

import re
from typing import Sequence

from loguru import logger


# Common non-distributor terms and false-positive phrases to ignore
IGNORED_PATTERNS = {
    "有価証券",
    "投資信託",
    "公社債投信",
    "日本証券業協会",
    "一般社団法人投資信託協会",
    "東京証券取引所",
    "ニューヨーク証券取引所",
    "金融商品取引所",
    "証券取引等監視委員会",
    "指定金銭信託",
    "外国為替証拠金取引",
    "証券投資信託",
    "上場投資信託",
    "国債証券",
    "外国証券",
    "ハイブリッド証券",
    "預託証券",
    "受益証券",
    "身替証券",
    "代替証券",
    "持分証券",
    "委託会社",
    "受託会社",
    "販売会社",
    "信託財産",
    "信託報酬",
    "信託金",
    "信託契約",
    "信託期間",
    "信託終了",
    "信託約款",
    "信託財産留保額",
    "信託法",
}

MANAGEMENT_COMPANIES = [
    "大和アセットマネジメント",
    "三菱ＵＦＪアセットマネジメント",
    "三菱UFJアセットマネジメント",
    "野村アセットマネジメント",
    "アセットマネジメントOne",
    "三井住友DSアセットマネジメント",
    "日興アセットマネジメント",
]

DISTRIBUTOR_SECTION_HEADERS = [
    "取扱販売会社",
    "販売会社一覧",
    "販売会社等",
    "指定参加者",
    "指定参加会社",
    "募集・販売等に関する事務",
]

COMPANY_REGEX = re.compile(
    r"((?:株式会社|合同会社)?[A-Za-z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF10-\uFF19\uFF21-\uFF3A\uFF41-\uFF5A]{2,20}?(?:証券|證券|銀行|信託銀行|生命保険|損害保険)(?:株式会社|合同会社)?)"
)


def _clean_company_name(name: str) -> str:
    """Normalize extracted company name."""
    cleaned = name.strip(" 　\t\n・●○■※、,()（）:：-ー")
    cleaned = re.sub(r"^(?:株式会社|合同会社)", "", cleaned).strip()
    cleaned = re.sub(r"(?:株式会社|合同会社)$", "", cleaned).strip()
    return cleaned.strip(" 　\t\n・●○■※、,()（）:：-ー")


def _is_valid_distributor(name: str, trustees: list[str]) -> bool:
    """Check if the candidate string is a real distributor and not a false positive."""
    cleaned = _clean_company_name(name)
    if not cleaned or len(cleaned) < 2 or len(cleaned) > 25:
        return False
    if any(cleaned == ign or ign in name for ign in IGNORED_PATTERNS):
        return False
    if any(mgmt in name or mgmt in cleaned for mgmt in MANAGEMENT_COMPANIES):
        return False
    if any(tr in cleaned or cleaned in tr for tr in trustees):
        return False
    # Avoid phrases ending in general words
    if any(cleaned.endswith(bad) for bad in ["信託", "証券へ", "銀行へ", "証券等", "銀行等", "証券の", "銀行の"]):
        return False
    # Must contain typical financial entity keywords
    if not any(k in cleaned for k in ["証券", "證券", "銀行", "生命保険", "損害保険"]):
        return False
    return True


def extract_distributors_from_text(text: str) -> tuple[list[str], float]:
    """Extract distributor company names from prospectus text using rule-based analysis.

    Returns:
        (distributor_names, confidence_score)
        If no distributors found, returns ([], 0.0).
    """
    if not text or not text.strip():
        return [], 0.0

    found_names: list[str] = []

    # Identify trustee(s) in the text to avoid misidentifying custody banks as distributors
    trustee_matches = re.findall(
        r"受託会社[：:\s（(]+(?:ファンドの財産の保管[^\n]*[）)])?\s*([^\n、,]+(?:信託銀行|銀行))",
        text,
    )
    trustees = [_clean_company_name(t) for t in trustee_matches if _clean_company_name(t)]

    # 1. Look for specific structured section blocks
    for header in DISTRIBUTOR_SECTION_HEADERS:
        pattern = rf"(?:{re.escape(header)})[\s\S]{{0,600}}"
        for sec_match in re.finditer(pattern, text):
            sec_text = sec_match.group(0)
            candidates = COMPANY_REGEX.findall(sec_text)
            for cand in candidates:
                if _is_valid_distributor(cand, trustees):
                    clean = _clean_company_name(cand)
                    if clean and clean not in found_names:
                        found_names.append(clean)

    # 2. Check for wrap account dedicated patterns (e.g. Daiwa Fund Wrap -> 大和証券)
    if "ダイワファンドラップ" in text and ("販売会社" in text or "大和証券" in text or "投資一任契約" in text):
        if "大和証券" not in found_names:
            found_names.append("大和証券")

    # 3. Check for specific distributor mentions in dedicated formats
    dist_inline = re.findall(r"販売会社[：:\s]+([^\n、,]+(?:証券|證券|銀行))", text)
    for dist in dist_inline:
        if _is_valid_distributor(dist, trustees):
            clean = _clean_company_name(dist)
            if clean and clean not in found_names:
                found_names.append(clean)

    if found_names:
        return found_names, 0.9

    return [], 0.0


def extract_distributors_with_fallback(
    fund_name: str,
    text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[list[str], float, str]:
    """Extract distributors using rule-based extraction first, falling back to LLM if needed.

    Returns:
        (distributor_names, confidence_score, provenance_type: 'ACTUAL' | 'DERIVED' | 'NONE')
    """
    # 1. Rule-based extraction
    rule_dists, rule_conf = extract_distributors_from_text(text)
    if rule_dists:
        return rule_dists, rule_conf, "ACTUAL"

    # 2. LLM fallback
    from app.llm import extract_distributors_with_llm, llm_available
    if llm_available(provider):
        llm_dists, llm_conf = extract_distributors_with_llm(
            fund_name=fund_name,
            text=text,
            provider=provider,
            model=model,
        )
        if llm_dists:
            return llm_dists, llm_conf, "DERIVED"

    return [], 0.0, "NONE"
