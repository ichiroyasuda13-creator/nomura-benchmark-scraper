from __future__ import annotations

import pytest
from app.distributors import build_broker_theme_sales_matrix, resolve_fund_distributors
from app.flow_calculator import calculate_daily_net_flows, estimate_period_net_inflow
from app.models import BenchmarkRecord
from app.proposal_generator import generate_product_proposals
from app.theme_classifier import classify_fund_theme


def test_flow_calculation_nomura_japan_open_verification():
    """Verify Yukawa-san's test case for ノムラ・ジャパン・オープン (2026年4月).

    Start (2026/03/31): AUM = 2,974.3億円, NAV = 25,512円
    End (2026/04/30):   AUM = 3,597.5億円, NAV = 28,925円 (+13.378%)
    Expected AUM Change: +623.2億円
    Expected Performance Effect: +397.9億円
    Expected Estimated Net Inflow: +225.3億円 (Daily Sum: +220.7億円 vs Official 219.65億円)
    """
    aum_start = 2974.3e8
    aum_end = 3597.5e8
    nav_start = 25512.0
    nav_end = 28925.0

    aum_chg, perf, flow = estimate_period_net_inflow(aum_start, aum_end, nav_start, nav_end)

    assert abs(aum_chg / 1e8 - 623.2) < 0.1
    assert abs(perf / 1e8 - 397.9) < 0.1
    assert abs(flow / 1e8 - 225.3) < 0.1



def test_daily_flow_calculation_synthetic():
    daily_records = [
        {"date": "2026-04-01", "nav": 10000.0, "aum": 1000.0e8, "distribution": 0.0},
        {"date": "2026-04-02", "nav": 10100.0, "aum": 1020.0e8, "distribution": 0.0},  # ret=+1% (+10億 perf), aum=+20億 -> flow=+10億
        {"date": "2026-04-03", "nav": 10201.0, "aum": 1050.0e8, "distribution": 0.0},  # ret=+1% (+10.2億 perf), aum=+30億 -> flow=+19.8億
    ]
    aum_chg, perf, flow = calculate_daily_net_flows(daily_records)
    assert round(aum_chg / 1e8, 1) == 50.0
    assert round(perf / 1e8, 1) == 20.2
    assert round(flow / 1e8, 1) == 29.8


def test_theme_classification():
    assert classify_fund_theme("野村AI関連株式ファンド") == "AI・半導体・ハイテク"
    assert classify_fund_theme("iFreeNEXT FANG+インデックス") == "AI・半導体・ハイテク"
    assert classify_fund_theme("大和住銀インド株式ファンド") == "インド・新興国株式"
    assert classify_fund_theme("eMAXIS Slim 全世界株式（オール・カントリー）") == "全世界・先進国株式"
    assert classify_fund_theme("ノムラ・ジャパン・オープン", "TOPIX") == "日本株式・高配当"
    assert classify_fund_theme("野村日本高配当株プレミアム") == "日本株式・高配当"
    assert classify_fund_theme("NOMURA-BPI総合インデックスファンド") == "債券・オルタナティブ"
    assert classify_fund_theme("三菱UFJ プライムバランス（安定成長型）") == "バランス・複合資産"


def test_distributor_resolution():
    top_dist, primary, action = resolve_fund_distributors("ノムラ・ジャパン・オープン", "野村アセットマネジメント")
    assert "野村證券" in top_dist
    assert primary == "野村證券"
    assert "攻めどころ" in action

    top_dist2, primary2, action2 = resolve_fund_distributors("iFreeNEXT FANG+インデックス", "大和アセットマネジメント")
    assert "SBI証券" in top_dist2
    assert "楽天証券" in top_dist2


def test_product_proposals_generator():
    records = [
        BenchmarkRecord(
            rank=1,
            management_company="野村アセットマネジメント",
            fund_name="野村国内株式インデックスファンド・TOPIX",
            fund_code="0131102B",
            aum=5000e8,
            theme_category="日本株式・高配当",
            benchmark="TOPIX",
            index_provider="JPX/東証",
            is_msci=False,
            estimated_net_inflow=200e8,
        )
    ]
    proposals = generate_product_proposals(records, "野村アセットマネジメント")
    assert len(proposals) > 0
    # AI theme is missing in records -> should be prioritized as high opportunity
    ai_prop = next(p for p in proposals if p["theme"] == "AI・半導体・ハイテク")
    assert "ギャップ" in ai_prop["status"]
    assert "SBI証券" in ai_prop["best_selling_brokers"]
    assert "MSCI" in ai_prop["recommended_msci_index"]


def test_funds_grouped_by_distributor_magazine_format(tmp_path):
    from app.distributors import get_funds_grouped_by_distributor
    from app.stage6_output import create_styled_excel

    records = [
        BenchmarkRecord(
            rank=1,
            management_company="野村アセットマネジメント",
            fund_name="野村外国株式インデックスファンド・MSCI-KOKUSAI（確定拠出年金向け）",
            fund_code="0131102B",
            aum=10135e8,
            estimated_net_inflow=500e8,
            theme_category="全世界・先進国株式",
            benchmark="MSCI-KOKUSAI",
            is_msci=True,
            top_distributors="野村證券 10,135億 / みずほFG 516億",
        ),
        BenchmarkRecord(
            rank=2,
            management_company="大和アセットマネジメント",
            fund_name="DCダイワ日本株式インデックス",
            fund_code="0431102C",
            aum=1116e8,
            estimated_net_inflow=80e8,
            theme_category="日本株式・高配当",
            benchmark="TOPIX",
            is_msci=False,
            top_distributors="大和証券 1,116億 / 三井住友信託",
        ),
    ]

    grouped = get_funds_grouped_by_distributor(records)
    assert "野村證券" in grouped
    assert len(grouped["野村證券"]) >= 1
    assert grouped["野村證券"][0]["fund_name"] == "野村外国株式インデックスファンド・MSCI-KOKUSAI（確定拠出年金向け）"

    assert "大和証券" in grouped
    assert len(grouped["大和証券"]) >= 1

    # Test 5-sheet excel export
    excel_file = tmp_path / "test_report.xlsx"
    create_styled_excel(records, excel_file)
    assert excel_file.exists()

