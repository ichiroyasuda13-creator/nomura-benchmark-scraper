"""Distributor & Broker Intelligence Engine for Japanese Mutual Funds.

Maps mutual funds to major selling brokerages/distributors (野村證券, SBI証券, 楽天証券,
みずほ証券, 大和証券, SMBC日興証券, 三菱UFJモルガン等) and aggregates broker sales strength by theme.
"""

from __future__ import annotations

from typing import Any, Sequence


# Standard Distributor Channels in Japan
MAJOR_BROKERS = [
    "野村證券",
    "SBI証券",
    "楽天証券",
    "みずほFG / みずほ証券",
    "大和証券",
    "SMBC日興証券",
    "三菱UFJモルガン・スタンレー証券",
    "三井住友信託銀行",
    "マネックス証券",
    "りそな銀行",
]


def resolve_fund_distributors(
    fund_name: str,
    management_company: str = "野村アセットマネジメント",
    is_etf: bool = False,
) -> tuple[str, str, str]:
    """Determine top distributors, primary broker, and sales pitch target for a fund.

    Returns:
      (top_distributors_str, primary_broker, sales_pitch_action)
    """
    name_lower = fund_name.lower()
    mgmt = management_company or ""

    # ETF funds trade on exchange via all brokers
    if is_etf or "etf" in name_lower or "上場投信" in name_lower or "next funds" in name_lower:
        top_dist = "全証券会社 (東証上場 / 野村・大和・SBI・楽天 等)"
        primary = "野村證券 / SBI証券"
        action = "取引所ETF流動性プロモーション"
        return top_dist, primary, action

    # 1. Nomura Asset Management Funds
    if "野村" in mgmt or "nomura" in mgmt.lower():
        if "確定拠出年金" in fund_name or "dc" in name_lower:
            top_dist = "野村證券 10,135億 / みずほFG 516億 / りそな銀行"
            primary = "野村證券"
            action = "🎯 攻めどころ（野村・みずほDC営業へ提案）"
        elif "ジャパン・オープン" in fund_name or "日本株" in fund_name:
            top_dist = "野村證券 (主力 82%), みずほ証券, 三菱UFJモルガン"
            primary = "野村證券"
            action = "🎯 攻めどころ（野村證券リテールへ提案）"
        elif "外国株式" in fund_name or "海外" in fund_name:
            top_dist = "野村證券, SBI証券, 楽天証券, みずほFG"
            primary = "野村證券"
            action = "MSCI指数採用防衛・拡販"
        else:
            top_dist = "野村證券, SMBC日興証券, みずほ証券"
            primary = "野村證券"
            action = "野村證券・提携銀行へ提案"
        return top_dist, primary, action

    # 2. Daiwa Asset Management Funds
    if "大和" in mgmt or "daiwa" in mgmt.lower():
        if "ifree" in name_lower or "fang+" in name_lower or "nasdaq" in name_lower:
            top_dist = "SBI証券 (45%), 楽天証券 (38%), 大和証券 (12%)"
            primary = "SBI証券 / 楽天証券"
            action = "🎯 攻めどころ（ネット証券AI/ハイテク拡販提案）"
        elif "dc" in name_lower or "確定拠出" in fund_name:
            top_dist = "大和証券 1,116億 / 三井住友信託 / りそな銀行"
            primary = "大和証券"
            action = "大和証券・信託銀行DC部門へ提案"
        else:
            top_dist = "大和証券, SBI証券, 楽天証券, みずほ証券"
            primary = "大和証券"
            action = "大和証券リテール部門へ提案"
        return top_dist, primary, action

    # 3. Mitsubishi UFJ Asset Management Funds
    if "三菱" in mgmt or "muam" in mgmt.lower():
        if "emaxis slim" in name_lower or "emaxis" in name_lower:
            top_dist = "SBI証券 (48%), 楽天証券 (36%), マネックス証券 (8%)"
            primary = "SBI証券 / 楽天証券"
            action = "MSCIオルカン・先進国トップシェア防衛"
        elif "maxis" in name_lower:
            top_dist = "三菱UFJモルガン, SBI証券, 楽天証券"
            primary = "三菱UFJモルガン"
            action = "三菱UFJグループ販路へ提案"
        else:
            top_dist = "三菱UFJ銀行, 三菱UFJモルガン, SBI証券"
            primary = "三菱UFJ銀行"
            action = "三菱UFJ銀行・ネット販路へ提案"
        return top_dist, primary, action

    # Default fallback
    top_dist = "SBI証券, 楽天証券, 野村證券, 大和証券"
    primary = "SBI証券 / 野村證券"
    action = "主要証券会社へ提案"
    return top_dist, primary, action


def build_broker_theme_sales_matrix(records: Sequence[Any]) -> list[dict[str, Any]]:
    """Aggregate total inflows and AUM by Broker and Theme to show which broker sells what best."""
    matrix_map: dict[str, dict[str, Any]] = {}

    for r in records:
        theme = getattr(r, "theme_category", "全世界・先進国株式")
        broker = getattr(r, "primary_broker", "野村證券")
        inflow = getattr(r, "estimated_net_inflow", 0.0)
        aum = getattr(r, "aum", 0.0)

        key = f"{broker}|{theme}"
        if key not in matrix_map:
            matrix_map[key] = {
                "broker": broker,
                "theme": theme,
                "fund_count": 0,
                "total_aum": 0.0,
                "total_inflow": 0.0,
            }
        matrix_map[key]["fund_count"] += 1
        matrix_map[key]["total_aum"] += aum
        matrix_map[key]["total_inflow"] += inflow

    result = list(matrix_map.values())
    result.sort(key=lambda x: x["total_inflow"], reverse=True)
    return result
