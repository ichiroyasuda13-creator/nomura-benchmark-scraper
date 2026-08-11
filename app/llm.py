from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.models import BenchmarkExtraction, Confidence, ExtractionMethod, FundType


SYSTEM_PROMPT = """\
あなたは日本の投資信託交付目論見書から、連動対象・基準指数を抽出するアシスタントです。
与えられたテキストに書かれている情報のみを使い、推測や創作は禁止です。
必ずJSONオブジェクト1つのみを返してください。Markdownや説明文は禁止です。

重要:
- インデックスファンドは「○○に連動する投資成果をめざします」と書き、"ベンチマーク" という語を
  使わないことが多い。"ベンチマーク" という語の有無に関わらず、連動対象・対象インデックス・
  基準指数を特定すること。
- 指数名は「（配当込み）」「（円換算ベース）」「（円ベース）」「（税引後配当込み）」などの
  括弧修飾を含めて正確に記載すること。
- 複数のマザーファンド／複合配分の場合は各資産クラスの指数と比率を benchmark_detail に
  構造化して返す（例：マイバランス70）。
- 本文に指数の記載が本当に無い場合のみ benchmark=null。本文にない指数名を創作しない。
- 「参考指数」（連動対象ではない比較用）は benchmark ではなく reference_index に入れる。
- ベンチマーク非設定の否定文があれば benchmark="なし", fund_type=アクティブ（BMなし）

フィールド:
- fund_type: インデックス / アクティブ / アクティブ（BMなし） / バランス（複合BM） / 不明
- benchmark: 連動対象またはベンチマーク指数名。なければ null
- benchmark_detail: 複合ベンチマークの構成(object)または null
- index_provider: MSCI / JPX/東証 / JPX/日経 / 日本経済新聞社 / 野村 / FTSE Russell / S&P DJI / Nasdaq / 複合 / なし
- is_msci: boolean
- reference_index: 参考指数。ベンチマークではない比較指数
- confidence: high / medium / low
- note: 補足。根拠が弱い場合は理由を書く
- needs_review: boolean
"""


def llm_available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def extract_with_llm(
    *,
    fund_name: str,
    section_text: str,
    rule_hint: dict[str, Any],
    max_retries: int = 2,
) -> BenchmarkExtraction | None:
    if not llm_available():
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; skipping LLM extraction")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = json.dumps(
        {
            "fund_name": fund_name,
            "rule_hint": rule_hint,
            "prospectus_excerpt": section_text[:12000],
            "instruction": (
                "この投資信託が連動をめざす／基準とする指数を特定してください。"
                "インデックス型では「ベンチマーク」という語が無くても連動対象指数を返してください。"
            ),
        },
        ensure_ascii=False,
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1200,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            content = message.content[0].text
            payload = _extract_json(content)
            payload.setdefault("extraction_method", ExtractionMethod.LLM.value)
            result = BenchmarkExtraction.model_validate(payload)
            if result.confidence == Confidence.LOW:
                result.needs_review = True
            return result
        except (ValidationError, json.JSONDecodeError, IndexError, KeyError) as exc:
            last_error = exc
            logger.warning("LLM parse failed (attempt {}): {}", attempt, exc)
        except Exception as exc:
            last_error = exc
            logger.warning("LLM request failed (attempt {}): {}", attempt, exc)

    logger.error("LLM extraction failed for {}: {}", fund_name, last_error)
    return None
