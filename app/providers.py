from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRule:
    keywords: tuple[str, ...]
    provider: str


@dataclass(frozen=True)
class NameIndexRule:
    pattern: re.Pattern[str]
    benchmark: str
    provider: str


PROVIDER_RULES: tuple[ProviderRule, ...] = (
    ProviderRule(
        ("MSCI", "コクサイ", "KOKUSAI", "ACWI", "エマージング"),
        "MSCI",
    ),
    ProviderRule(
        ("TOPIX", "東証株価指数", "東証REIT", "東証"),
        "JPX/東証",
    ),
    ProviderRule(
        ("JPX日経", "JPX日経インデックス400"),
        "JPX/日経",
    ),
    ProviderRule(
        ("日経平均", "日経225", "日経半導体", "日経高配当", "日経"),
        "日本経済新聞社",
    ),
    ProviderRule(
        ("NOMURA-BPI", "野村BPI", "NOMURA BPI", "野村総合"),
        "野村",
    ),
    ProviderRule(
        ("FTSE", "ラッセル", "Russell"),
        "FTSE Russell",
    ),
    ProviderRule(
        ("S&P", "S＆P", "ダウ", "DOW"),
        "S&P DJI",
    ),
    ProviderRule(
        ("NASDAQ", "ナスダック"),
        "Nasdaq",
    ),
)

IDX_CHARS = (
    r"[0-9A-Za-zＡ-Ｚａ-ｚ０-９ぁ-んァ-ヶ一-龠ー・／/\-\.&＆　 （）\(\),、，]"
)

NAME_INDEX_RULES: tuple[NameIndexRule, ...] = tuple(
    NameIndexRule(re.compile(pattern, re.I), benchmark, provider)
    for pattern, benchmark, provider in (
        (r"MSCI[-\s]?KOKUSAI|MSCIコクサイ|コクサイ", "MSCI-KOKUSAI指数", "MSCI"),
        (r"MSCI.*ACWI|オール・?カントリー|全世界株", "MSCI ACWI", "MSCI"),
        (r"MSCI.*エマージング|新興国株.*MSCI", "MSCI エマージング・マーケット", "MSCI"),
        (r"MSCI.*インド", "MSCI インディア", "MSCI"),
        (r"MSCI.*ジャパン|MSCIジャパン", "MSCI ジャパン", "MSCI"),
        (r"TOPIX|東証株価指数", "TOPIX", "JPX/東証"),
        (r"日経(平均|225)|日経２２５", "日経225", "日本経済新聞社"),
        (r"JPX日経(インデックス)?400", "JPX日経インデックス400", "JPX/日経"),
        (r"東証REIT|J-?REIT", "東証REIT指数", "JPX/東証"),
        (r"NASDAQ[-\s]?100|ナスダック100", "NASDAQ-100", "Nasdaq"),
        (r"S&P\s?500|S＆P500", "S&P 500", "S&P DJI"),
        (r"NOMURA-?BPI|野村BPI", "NOMURA-BPI総合", "野村"),
        (r"FTSE.*世界国債|世界国債インデックス", "FTSE世界国債インデックス", "FTSE Russell"),
        (r"Russell/?Nomura|ラッセル野村", "Russell/Nomura", "FTSE Russell / 野村"),
    )
)

INDEX_LIKE_NAME_KEYWORDS: tuple[str, ...] = (
    "インデックス",
    "連動",
    "ETF",
    "ＥＴＦ",
    "上場投信",
    "NEXT FUNDS",
)

NEGATIVE_BENCHMARK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"ベンチマーク(?:指数)?(?:を)?(?:設け(?:ません|ない)|設定(?:し(?:ません|ない)|いたしません)|ありません)",
        r"特定の指数を(?:ベンチマーク|運用の目標)(?:指数)?(?:と(?:は)?)?(?:し(?:ません|ない)|設定(?:し(?:ません|ない)|いたしません))",
        r"ベンチマーク(?:指数)?(?:は)?(?:設けて(?:おり|い)?(?:ません|ない))",
    )
)

REFERENCE_INDEX_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.DOTALL)
    for pattern in (
        r"参考指数(?:として)?[「『]?(.{2,80}?)[」』]?(?:を(?:用い|使用|参照|示し)|と(?:は)?(?:い(?:い|)ますが|異なり))",
        r"比較(?:対象|のため)(?:として)?[「『]?(.{2,80}?)[」』]?(?:を(?:用い|使用|参照))",
    )
)

BENCHMARK_CANDIDATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.DOTALL)
    for pattern in (
        rf"({IDX_CHARS}{{2,80}}?)(?:の動き)?\s*に連動する(?:投資|運用)成果を(?:めざ|目指)",
        rf"({IDX_CHARS}{{2,80}}?)(?:の動き)?\s*に連動(?:させる|することを|をめざ)",
        rf"({IDX_CHARS}{{2,80}}?)\s*への連動を(?:めざ|目指)",
        rf"({IDX_CHARS}{{2,80}}?)(?:（[^）]*）)*(?:以下)?「対象(?:インデックス|指数)」",
        rf"対象(?:インデックス|指数)[はとは：:]{{0,3}}\s*({IDX_CHARS}{{2,80}}?)(?:と(?:い|言)います|です|。)",
        rf"({IDX_CHARS}{{2,80}}?)\s*を\s*ベンチマーク",
        rf"ベンチマーク(?:指数)?[は：:]\s*[「『]?({IDX_CHARS}{{2,80}}?)[」』]?(?:と(?:は|する|します|した|定め)|です|。)",
        rf"連動(?:対象|指数)(?:として)?[「『]?({IDX_CHARS}{{2,80}}?)[」』]?(?:と(?:は|する|します|した|定め)|を(?:設定|採用))",
        r"複合ベンチマーク[\s\S]{0,300}?(?:連動|構成)[\s\S]{0,200}",
    )
)

SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "purpose",
        re.compile(
            r"ファンドの目的([\s\S]{0,4000}?)(?=ファンドの特色|運用の概要|投資対象|第\d+|\Z)",
        ),
    ),
    (
        "feature",
        re.compile(
            r"ファンドの特色([\s\S]{0,4000}?)(?=運用の概要|投資対象|第\d+|\Z)",
        ),
    ),
    ("index_note", re.compile(r"指数(?:の)?知的財産権([\s\S]{0,3000})")),
)

RENDOU_TRIGGER_PATTERN = re.compile(
    r"連動|対象インデックス|対象指数|に連動する投資成果|に連動する運用成果"
)

INDEX_NAME_HINTS: tuple[str, ...] = (
    "指数",
    "Index",
    "INDEX",
    "TOPIX",
    "MSCI",
    "日経",
    "NASDAQ",
    "S&P",
    "BPI",
    "FTSE",
    "Russell",
    "REIT",
    "ダウ",
    "コクサイ",
    "KOKUSAI",
    "ACWI",
)


def is_valid_benchmark_name(name: str | None) -> bool:
    if not name or name == "なし":
        return bool(name == "なし")
    cleaned = clean_index_name(name)
    if len(cleaned) < 3:
        return False
    if cleaned.startswith(("連動", "対象指数", "対象インデックス", "（対象", "本ファンド")):
        return False
    if "連動する投資成果" in cleaned or "基準価額の変動率" in cleaned:
        return False
    if cleaned in {"（対象株価指数）", "対象指数（以下", "対象指数（"}:
        return False
    if any(hint in cleaned for hint in INDEX_NAME_HINTS):
        return True
    if detect_index_provider(cleaned) != "なし":
        return True
    # アクティブ型の外部指数（Bloomberg 等）は「指数」を含まないこともある
    return len(cleaned) >= 8


def normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).upper()
    normalized = re.sub(r"[・\s　\-－/／]", "", normalized)
    return normalized


def clean_index_name(raw: str) -> str:
    cleaned = raw.strip(" 　「」『』\"'・:：。、\n")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"^ファンドの(?:目的|特色)\s*", "", cleaned)
    cleaned = re.sub(r"^本ファンドは[、,]?\s*", "", cleaned)
    cleaned = re.sub(r"^(は|を|に|の|、|，|および|又は|または)+", "", cleaned)
    if cleaned.startswith("本ファンドは"):
        cleaned = cleaned.split("、", 1)[-1]
    return cleaned.strip()


def detect_index_provider(
    benchmark: str | None,
    *,
    composite: bool = False,
) -> str:
    if composite:
        return "複合"
    if not benchmark or benchmark in {"なし", "null", "None"}:
        return "なし"

    normalized = normalize_for_match(benchmark)
    matched: list[str] = []
    for rule in PROVIDER_RULES:
        for keyword in rule.keywords:
            key_norm = normalize_for_match(keyword)
            if key_norm in normalized or keyword.upper() in benchmark.upper() or keyword in benchmark:
                if rule.provider not in matched:
                    matched.append(rule.provider)
                break

    if len(matched) > 1:
        return "複合"
    if len(matched) == 1:
        return matched[0]
    return "なし"


def is_msci_benchmark(benchmark: str | None, index_provider: str) -> bool:
    if not benchmark:
        return False
    if index_provider == "MSCI":
        return True
    normalized = normalize_for_match(benchmark)
    return any(
        normalize_for_match(keyword) in normalized
        for keyword in ("MSCI", "コクサイ", "KOKUSAI", "ACWI")
    )


def provider_match_score(candidate: str) -> int:
    provider = detect_index_provider(candidate)
    if provider == "なし":
        return 0
    return 2 if provider != "複合" else 1


def prioritize_candidates(candidates: list[str]) -> list[str]:
    if len(candidates) <= 1:
        return candidates
    return sorted(
        candidates,
        key=lambda item: (provider_match_score(item), len(item)),
        reverse=True,
    )


def extract_from_fund_name(fund_name: str) -> tuple[str, str] | None:
    for rule in NAME_INDEX_RULES:
        if rule.pattern.search(fund_name):
            return rule.benchmark, rule.provider
    return None


def is_index_like_fund_name(fund_name: str, *, is_etf: bool = False) -> bool:
    if is_etf:
        return True
    return any(keyword in fund_name for keyword in INDEX_LIKE_NAME_KEYWORDS)


def has_rendou_trigger(text: str) -> bool:
    return bool(RENDOU_TRIGGER_PATTERN.search(text))
