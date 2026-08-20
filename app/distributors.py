"""Distributor & Broker Intelligence Engine for Japanese Mutual Funds.

Maps mutual funds to major selling brokerages/distributors (野村證券, SBI証券, 楽天証券,
みずほ証券, 大和証券, SMBC日興証券, 三菱UFJモルガン, 三井住友信託, りそな, 日本生命 等)
and structures fund rankings by individual distributor (matching industry magazine reporting).
"""

from __future__ import annotations

from typing import Any, Sequence


# Major Distributor Categories
MAJOR_DISTRIBUTORS = [
    "野村證券",
    "大和証券",
    "みずほFG / みずほ証券",
    "三菱UFJフィナンシャルG",
    "三井住友信託銀行",
    "三井住友FG / SMBC日興証券",
    "SBI証券",
    "楽天証券",
    "りそな銀行",
    "日本生命保険 / 生保チャネル",
]


def resolve_distributors_from_codes(
    company_codes: list[str],
    master: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """Resolve distributor codes against master metadata.

    Returns:
        (securities_names, bank_names, insurance_names)
        CompanyType 1 -> securities
        CompanyType 2, 5 -> banks
        CompanyType 3 -> insurance
    """
    securities: list[str] = []
    banks: list[str] = []
    insurance: list[str] = []

    for code in company_codes:
        c_str = str(code).strip()
        info = master.get(c_str)
        if not info:
            continue
        name = str(info.get("CompanyName", "")).strip()
        ctype = str(info.get("CompanyType", "")).strip()
        if not name:
            continue
        if ctype == "1":
            securities.append(name)
        elif ctype in ("2", "5"):
            banks.append(name)
        elif ctype == "3":
            insurance.append(name)

    return securities, banks, insurance


def resolve_fund_distributors(
    fund_name: str,
    management_company: str = "野村アセットマネジメント",
    is_etf: bool = False,
) -> tuple[str, str, str]:
    """Determine top distributors, primary broker, and sales pitch target for a fund."""
    name_lower = fund_name.lower()
    mgmt = management_company or ""

    if is_etf or "etf" in name_lower or "上場投信" in name_lower or "next funds" in name_lower:
        top_dist = "全証券会社 (東証上場 / 野村・大和・SBI・楽天・三菱UFJ 等)"
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
            action = "MSCI-KOKUSAI採用防衛・拡販"
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
        elif "プライムバランス" in fund_name or "dc" in name_lower:
            top_dist = "三菱UFJ信託, 三菱UFJモルガン 3,628億 / 三井住友信託"
            primary = "三菱UFJ信託"
            action = "三菱UFJ・信託チャネルへ提案"
        else:
            top_dist = "三菱UFJ銀行, 三菱UFJモルガン, SBI証券"
            primary = "三菱UFJ銀行"
            action = "三菱UFJ銀行・ネット販路へ提案"
        return top_dist, primary, action

    top_dist = "SBI証券, 楽天証券, 野村證券, 大和証券"
    primary = "SBI証券 / 野村證券"
    action = "主要証券会社へ提案"
    return top_dist, primary, action


def get_funds_grouped_by_distributor(records: Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    """Group and rank funds by major distributor, replicating the industry magazine format."""
    grouped: dict[str, list[dict[str, Any]]] = {dist: [] for dist in MAJOR_DISTRIBUTORS}

    for r in records:
        dist_str = getattr(r, "top_distributors", "") or getattr(r, "primary_broker", "")
        fund_name = getattr(r, "fund_name", "")
        company = getattr(r, "management_company", "野村アセットマネジメント")
        aum = getattr(r, "aum", 0.0)
        bm = getattr(r, "benchmark", "") or "—"
        is_msci = getattr(r, "is_msci", False)
        theme = getattr(r, "theme_category", "全世界・先進国株式")
        action = getattr(r, "sales_pitch_action", "提案対象")

        item = {
            "fund_code": getattr(r, "fund_code", ""),
            "fund_name": fund_name,
            "management_company": company,
            "aum_oku": round(aum / 1e8, 1),
            "benchmark": bm,
            "is_msci": is_msci,
            "theme": theme,
            "action": action,
        }


        # Check which distributors sell this fund
        for dist in MAJOR_DISTRIBUTORS:
            match = False
            if dist == "野村證券" and ("野村證券" in dist_str or "野村" in company):
                match = True
            elif dist == "大和証券" and ("大和証券" in dist_str or "大和" in company):
                match = True
            elif dist.startswith("みずほ") and ("みずほ" in dist_str):
                match = True
            elif dist.startswith("三菱UFJ") and ("三菱" in dist_str or "三菱" in company):
                match = True
            elif dist.startswith("三井住友信託") and ("三井住友信託" in dist_str or "信託" in dist_str):
                match = True
            elif dist.startswith("三井住友FG") and ("SMBC" in dist_str or "三井住友" in dist_str):
                match = True
            elif dist == "SBI証券" and ("SBI" in dist_str or "ifree" in fund_name.lower() or "slim" in fund_name.lower()):
                match = True
            elif dist == "楽天証券" and ("楽天" in dist_str or "ifree" in fund_name.lower() or "slim" in fund_name.lower()):
                match = True
            elif dist == "りそな銀行" and ("りそな" in dist_str):
                match = True
            elif dist.startswith("日本生命") and ("日本生命" in dist_str or "ニッセイ" in fund_name):
                match = True

            if match:
                grouped[dist].append(item)

    # Sort each distributor's funds by AUM descending and assign rank 1..N
    result: dict[str, list[dict[str, Any]]] = {}
    for dist, funds in grouped.items():
        if not funds:
            continue
        funds.sort(key=lambda x: x["aum_oku"], reverse=True)
        ranked_funds = []
        for i, f in enumerate(funds[:15], start=1):
            f_copy = dict(f)
            f_copy["rank"] = i
            ranked_funds.append(f_copy)
        result[dist] = ranked_funds

    return result


def build_broker_theme_sales_matrix(records: Sequence[Any]) -> list[dict[str, Any]]:
    """Aggregate total inflows and AUM by Broker and Theme to show which broker sells what best."""
    matrix_map: dict[str, dict[str, Any]] = {}

    for r in records:
        theme = getattr(r, "theme_category", "全世界・先進国株式")
        broker = getattr(r, "primary_broker", "野村證券")
        inflow = getattr(r, "estimated_net_inflow", 0.0) or 0.0
        aum = getattr(r, "aum", 0.0) or 0.0

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
