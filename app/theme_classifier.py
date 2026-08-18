"""Theme & Strategic Category Classifier for Investment Funds.

Classifies mutual funds into strategic investment themes (AI/Semiconductors, India/Emerging,
All Country/World Equity, Japan Equity, Bonds/Commodities, Multi-Asset Balance)
to enable consultative product proposals for asset managers.
"""

from __future__ import annotations

import re


THEMES = [
    "AI・半導体・ハイテク",
    "インド・新興国株式",
    "全世界・先進国株式",
    "日本株式・高配当",
    "債券・オルタナティブ",
    "バランス・複合資産",
]


def classify_fund_theme(fund_name: str, benchmark: str = "") -> str:
    """Classify fund into a strategic investment theme based on name and benchmark."""
    combined = f"{fund_name} {benchmark}".lower()

    # 1. AI / Semiconductor / High Tech
    if any(
        k in combined
        for k in (
            "ai", "ａｉ", "人工知能", "半導体", "fang", "ｆａｎｇ", "tech", "テック",
            "sox", "ｓｏｘ", "nasdaq", "ナスダック", "情報技術", "ロボット", "ロボティクス",
            "サイバー", "デジタルトランスフォーメーション", "dx", "フィンテック"
        )
    ):
        return "AI・半導体・ハイテク"

    # 2. India & Emerging Markets
    if any(
        k in combined
        for k in (
            "インド", "nifty", "ニフティ", "新興国", "エマージング", "emerging",
            "アジア", "中国", "china", "ブラジル", "ベトナム", "ラテンアメリカ"
        )
    ):
        return "インド・新興国株式"

    # 3. Balance / Multi-Asset
    if any(
        k in combined
        for k in (
            "バランス", "マイバランス", "資産均等", "８資産", "8資産", "６資産", "6資産",
            "ターゲットイヤー", "ターゲット・イヤー", "分散投資コア", "コア戦略", "複合"
        )
    ):
        return "バランス・複合資産"

    # 4. Bonds & Alternatives / REIT / Gold
    if any(
        k in combined
        for k in (
            "債券", "bond", "国債", "bpi", "ｂｐｉ", "reit", "リート", "不動産",
            "ゴールド", "金", "コモディティ", "ハイイールド", "インカム", "公社債"
        )
    ):
        return "債券・オルタナティブ"

    # 5. Japan Equity & High Dividend
    if any(
        k in combined
        for k in (
            "topix", "ｔｏｐｉｘ", "トピックス", "日経225", "日経平均", "日本株式",
            "ジャパン", "国内株式", "日本株", "高配当", "好配当", "バリュー株", "小型株", "中小型"
        )
    ):
        return "日本株式・高配当"

    # 6. Global & Developed Market Equity
    if any(
        k in combined
        for k in (
            "オール・カントリー", "オールカントリー", "オルカン", "acwi", "全世界", "世界株式",
            "外国株式", "先進国", "kokusai", "コクサイ", "s&p500", "ｓ＆ｐ５００", "米国株式",
            "米国株", "グローバル株式", "world", "msci"
        )
    ):
        return "全世界・先進国株式"

    # Default to Global Equity if unknown
    return "全世界・先進国株式"
