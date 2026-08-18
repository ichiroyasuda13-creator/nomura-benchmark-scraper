"""Product Proposal & Broker Matchmaker Engine for Asset Managers.

Identifies portfolio theme gaps and generates actionable new fund proposals
linking MSCI Indexes with the highest-selling distributor channels.
"""

from __future__ import annotations

from typing import Any, Sequence
from app.models import BenchmarkRecord, format_aum_oku, format_inflow_oku


THEME_MSCI_RECOMMENDATIONS = {
    "AI・半導体・ハイテク": {
        "recommended_index": "MSCI ACWI IMI Robotics & AI Index / MSCI World Info Tech",
        "best_brokers": "SBI証券, 楽天証券, 野村證券",
        "pitch_hook": "市場全体でAI・半導体系に年間+2,000億円以上の資金が純流入。ネット証券での若年層・積立需要が突出して高いため、低コストMSCI AI指数での新設を提案。",
    },
    "インド・新興国株式": {
        "recommended_index": "MSCI India Domestic Index / MSCI Emerging Markets",
        "best_brokers": "SBI証券, 楽天証券, 大和証券",
        "pitch_hook": "インド株は単月+300億円超の資金流入が継続中。既存新興国枠からのリプレイスとしてMSCI India連動型の共同企画を推奨。",
    },
    "日本株式・高配当": {
        "recommended_index": "MSCI Japan High Dividend Yield Index / MSCI Japan Leaders",
        "best_brokers": "野村證券, みずほFG, SMBC日興証券",
        "pitch_hook": "東証PBR改革と新NISA成長投資枠で国内高配当・クオリティ株への買い付けが急増。対面大手証券のリテール営業部隊に最適。",
    },
    "全世界・先進国株式": {
        "recommended_index": "MSCI ACWI (オール・カントリー) / MSCI-KOKUSAI",
        "best_brokers": "全販路 (SBI, 楽天, 三菱UFJ, みずほ, 野村)",
        "pitch_hook": "公募投信最大の資金流入コア資産。MSCIブランドの圧倒的認知度を活かした旗艦ファンドの拡販・シリーズ化を提案。",
    },
    "債券・オルタナティブ": {
        "recommended_index": "MSCI Global Green Bond Index / MSCI World Real Estate",
        "best_brokers": "三井住友信託銀行, 三菱UFJモルガン, 大和証券",
        "pitch_hook": "金利上昇局面における安定インカム・金/REIT分散ニーズに対応。信託銀行・富裕層チャネルへの商品企画を提案。",
    },
    "バランス・複合資産": {
        "recommended_index": "MSCI Multi-Asset Adaptive Allocation Benchmark",
        "best_brokers": "確定拠出年金(DC)取扱銀行, 野村證券, 大和証券",
        "pitch_hook": "DC（企業型・iDeCo）および退職世代向けの資産均等型・ターゲットイヤー型商品の組成を提案。",
    },
}


def generate_product_proposals(
    records: Sequence[BenchmarkRecord],
    company_name: str = "野村アセットマネジメント",
) -> list[dict[str, Any]]:
    """Analyze the current lineup of an asset manager, identify gaps, and generate pitch proposals."""
    existing_themes = {r.theme_category for r in records if r.theme_category}
    total_aum = sum(r.aum for r in records)
    total_inflow = sum(r.estimated_net_inflow for r in records)

    proposals = []

    for theme, info in THEME_MSCI_RECOMMENDATIONS.items():
        theme_records = [r for r in records if r.theme_category == theme]
        theme_aum = sum(r.aum for r in theme_records)
        theme_inflow = sum(r.estimated_net_inflow for r in theme_records)

        has_theme = len(theme_records) > 0
        status = "ラインアップあり" if has_theme else "⚠️ 未保有 (ギャップ)"

        # Priority scoring: Missing theme with high market demand gets high priority
        if not has_theme:
            priority = "🔥 最優先提案 (新規組成)"
            opportunity_score = 95
        elif theme_inflow > 0 and not any(r.is_msci for r in theme_records):
            priority = "🎯 ベンチマーク切替・MSCI化提案"
            opportunity_score = 85
        else:
            priority = "🟢 既存拡販・シリーズ強化"
            opportunity_score = 70

        proposals.append({
            "theme": theme,
            "status": status,
            "priority": priority,
            "opportunity_score": opportunity_score,
            "existing_funds_count": len(theme_records),
            "theme_aum_display": format_aum_oku(theme_aum) if theme_aum else "0円",
            "theme_inflow_display": format_inflow_oku(theme_inflow) if theme_inflow else "—",
            "recommended_msci_index": info["recommended_index"],
            "best_selling_brokers": info["best_brokers"],
            "proposal_narrative": info["pitch_hook"],
            "action_plan": f"【提案方針】{info['best_brokers']} を主要販売パートナーとして、{info['recommended_index']} 連動型新商品の企画を {company_name} 商品企画部に打診する。",
        })

    # Sort proposals by opportunity score
    proposals.sort(key=lambda x: x["opportunity_score"], reverse=True)
    return proposals
