from __future__ import annotations

import json
import re
from typing import Any

import httpx
from loguru import logger
from pydantic import ValidationError

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
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
- index_provider: MSCI / JPX/東証 / JPX/日経 / 日本経済新聞社 / 野村 / FTSE Russell / S&P DJI / Nasdaq / ブルームバーグ / ICE / ソラクティブ / モーニングスター / STOXX / 複合 / なし
- is_msci: boolean
- reference_index: 参考指数。ベンチマークではない比較指数
- confidence: high / medium / low
- note: 補足。根拠が弱い場合は理由を書く
- needs_review: boolean
"""


def get_available_providers() -> list[dict[str, Any]]:
    """Return a list of all supported LLM providers."""
    import os
    import app.config as cfg
    gemini_key = os.getenv("GEMINI_API_KEY") or cfg.GEMINI_API_KEY
    claude_key = os.getenv("ANTHROPIC_API_KEY") or cfg.ANTHROPIC_API_KEY
    openai_key = os.getenv("OPENAI_API_KEY") or cfg.OPENAI_API_KEY

    return [
        {
            "id": "gemini",
            "name": "Google Gemini",
            "model": "gemini-2.0-flash / 1.5-flash",
            "configured": bool(gemini_key),
        },
        {
            "id": "anthropic",
            "name": "Anthropic Claude",
            "model": "claude-3-5-sonnet",
            "configured": bool(claude_key),
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "model": "gpt-4o-mini",
            "configured": bool(openai_key),
        },
        {
            "id": "ollama",
            "name": "Ollama (Local LLM)",
            "model": "llama3.2",
            "configured": bool(cfg.OLLAMA_BASE_URL),
        },
    ]



def llm_available(provider: str | None = None) -> bool:
    """Check if any or a specific LLM provider is configured and available."""
    target = (provider or LLM_PROVIDER or "auto").lower()
    if target == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    if target == "gemini":
        return bool(GEMINI_API_KEY)
    if target == "openai":
        return bool(OPENAI_API_KEY)
    if target == "ollama":
        return bool(OLLAMA_BASE_URL)
    # auto: check any key
    return bool(ANTHROPIC_API_KEY or GEMINI_API_KEY or OPENAI_API_KEY)


def resolve_active_provider(preferred: str | None = None) -> str | None:
    """Determine the active LLM provider based on preferences and availability."""
    target = (preferred or LLM_PROVIDER or "auto").lower()
    if target != "auto" and llm_available(target):
        return target
    if ANTHROPIC_API_KEY:
        return "anthropic"
    if GEMINI_API_KEY:
        return "gemini"
    if OPENAI_API_KEY:
        return "openai"
    return None


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    return json.loads(text)


def _call_anthropic(prompt: str, model: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=15.0)
        message = client.messages.create(
            model=model,
            max_tokens=1200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except ImportError:
        # Fallback to direct HTTP
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1200,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]



def _call_openai(prompt: str, model: str) -> str:
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, model: str) -> str:
    import os
    import app.config as cfg
    api_key = os.getenv("GEMINI_API_KEY") or cfg.GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    # If model is default or flash, use 2.0-flash or 1.5-flash
    target_model = model or "gemini-2.0-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
        f"?key={api_key}"
    )
    headers = {"Content-Type": "application/json"}
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        # Fallback to gemini-1.5-flash if 2.0 returns 404
        if resp.status_code == 404 and target_model != "gemini-1.5-flash":
            url_fallback = (
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
                f"?key={api_key}"
            )
            resp = client.post(url_fallback, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini API returned no candidates: {data}")
        return candidates[0]["content"]["parts"][0]["text"]




def _call_ollama(prompt: str, model: str) -> str:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]


def extract_with_llm(
    *,
    fund_name: str,
    section_text: str,
    rule_hint: dict[str, Any],
    provider: str | None = None,
    model: str | None = None,
    max_retries: int = 2,
) -> BenchmarkExtraction | None:
    active_provider = resolve_active_provider(provider)
    if not active_provider:
        return None

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

    # Determine default model for active provider
    if active_provider == "anthropic":
        active_model = model or ANTHROPIC_MODEL
        call_fn = lambda p: _call_anthropic(p, active_model)
    elif active_provider == "gemini":
        active_model = model or GEMINI_MODEL
        call_fn = lambda p: _call_gemini(p, active_model)
    elif active_provider == "openai":
        active_model = model or OPENAI_MODEL
        call_fn = lambda p: _call_openai(p, active_model)
    elif active_provider == "ollama":
        active_model = model or OLLAMA_MODEL
        call_fn = lambda p: _call_ollama(p, active_model)
    else:
        logger.warning("Unsupported LLM provider: {}", active_provider)
        return None

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            content = call_fn(user_prompt)
            payload = _extract_json(content)
            payload.setdefault("extraction_method", ExtractionMethod.LLM.value)
            result = BenchmarkExtraction.model_validate(payload)
            if result.confidence == Confidence.LOW:
                result.needs_review = True
            return result
        except (ValidationError, json.JSONDecodeError, IndexError, KeyError) as exc:
            last_error = exc
            logger.warning("{} parse failed (attempt {}): {}", active_provider, attempt, exc)
        except Exception as exc:
            last_error = exc
            logger.warning("{} request failed (attempt {}): {}", active_provider, attempt, exc)

    logger.error("LLM extraction failed for {} using {}: {}", fund_name, active_provider, last_error)
    return None


def extract_distributors_with_llm(
    *,
    fund_name: str,
    text: str,
    provider: str | None = None,
    model: str | None = None,
    max_retries: int = 2,
) -> tuple[list[str], float]:
    """Extract distributor company names from prospectus text using LLM.

    Strict instruction: Only return names explicitly written in the text.
    Do NOT guess or hallucinate unmentioned companies.
    """
    active_provider = resolve_active_provider(provider)
    if not active_provider:
        return [], 0.0

    prompt_data = {
        "fund_name": fund_name,
        "prospectus_text": text[:12000],
        "instruction": (
            "テキスト内に明記されている販売会社・取扱金融機関・指定参加者（証券会社・銀行・保険等）の社名のみを抽出してください。\n"
            "テキストに明記されていない社名の推測や補完は厳禁です。\n"
            "特定の販売会社名が記載されていない（例：『販売会社にご確認ください』等のみの）場合は空リスト [] を返してください。\n"
            "JSON形式: {\"distributors\": [\"社名1\", \"社名2\", ...]}"
        ),
    }
    user_prompt = json.dumps(prompt_data, ensure_ascii=False)

    if active_provider == "anthropic":
        active_model = model or ANTHROPIC_MODEL
        call_fn = lambda p: _call_anthropic(p, active_model)
    elif active_provider == "gemini":
        active_model = model or GEMINI_MODEL
        call_fn = lambda p: _call_gemini(p, active_model)
    elif active_provider == "openai":
        active_model = model or OPENAI_MODEL
        call_fn = lambda p: _call_openai(p, active_model)
    elif active_provider == "ollama":
        active_model = model or OLLAMA_MODEL
        call_fn = lambda p: _call_ollama(p, active_model)
    else:
        return [], 0.0

    for attempt in range(1, max_retries + 1):
        try:
            content = call_fn(user_prompt)
            payload = _extract_json(content)
            dist_list = payload.get("distributors", [])
            if isinstance(dist_list, list):
                cleaned = [str(d).strip() for d in dist_list if str(d).strip()]
                if cleaned:
                    return cleaned, 0.8
                return [], 0.0
        except Exception as exc:
            logger.warning("Distributor LLM extraction failed (attempt {}): {}", attempt, exc)

    return [], 0.0


