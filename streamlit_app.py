"""Streamlit web app for Multi-Asset Management Benchmark Scraper & Intelligence.

Features:
- Multi-Asset Managers (1社/2社/3社同時選択 & 一括実行): 野村アセット, 大和アセット, 三菱UFJアセット
- Distributor-by-Distributor Fund Rankings (添付雑誌DCトレンドフォーマット完全再現)
- Net Inflow (買い付け金額 / 推定純流入) & Performance Effect Calculation
- Broker & Distributor Intelligence (主要販売会社 & 販社別売れ行き)
- Theme & Gap Analysis for Consultative Product Proposals
- Interactive Data Editor & 5-Sheet Excel Generation
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Page Config (MUST BE FIRST STREAMLIT COMMAND) ───────────────────────────
st.set_page_config(
    page_title="ファンド・ベンチマーク抽出 & 販社営業インテリジェンス",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Ensure project root is importable ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.config import (
        ANTHROPIC_API_KEY,
        BENCHMARKS_JSON,
        DATA_DIR,
        FUNDS_JSON,
        GEMINI_API_KEY,
        MAX_WORKERS,
        OPENAI_API_KEY,
        OUTPUT_DIR,
        TEXT_DIR,
        ensure_dirs,
    )
    from app.daiwa_stage1 import run_stage1_daiwa
    from app.distributors import (
        MAJOR_DISTRIBUTORS,
        build_broker_theme_sales_matrix,
        get_funds_grouped_by_distributor,
        resolve_fund_distributors,
    )
    from app.flow_calculator import estimate_fund_flow_from_returns
    from app.http_client import load_json, save_json, setup_logging
    from app.llm import get_available_providers, llm_available
    from app.models import (
        BenchmarkRecord,
        Confidence,
        Fund,
        FundType,
        format_aum_oku,
        format_inflow_oku,
    )
    from app.muam_stage1 import run_stage1_muam
    from app.proposal_generator import generate_product_proposals
    from app.stage5_benchmark import reextract_single_fund, update_manual_override
    from app.stage6_output import run_stage6
    from app.theme_classifier import THEMES, classify_fund_theme
except Exception as _import_err:
    st.error(f"⚠️ 初期化インポートエラー: {_import_err}")
    st.exception(_import_err)
    st.stop()


# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+JP:wght@300;400;500;600;700&display=swap');

    .main { font-family: 'Inter', 'Noto Sans JP', sans-serif; }

    /* App Header */
    .app-header {
        text-align: center;
        padding: 0.8rem 0 1.2rem;
    }
    .header-badge {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        padding: 2px 12px;
        border-radius: 100px;
        background: rgba(99, 102, 241, 0.15);
        color: #818cf8;
        border: 1px solid rgba(99, 102, 241, 0.3);
        margin-bottom: 6px;
    }
    .app-header h1 {
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(135deg, #ffffff 40%, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.02em;
    }
    .app-header p {
        color: #94a3b8;
        font-size: 0.9rem;
    }

    /* KPI Cards */
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 0.8rem;
        margin-bottom: 1.5rem;
    }
    .kpi-box {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.1rem 0.8rem;
        text-align: center;
        backdrop-filter: blur(12px);
    }
    .kpi-box-title {
        font-size: 0.70rem;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 700;
    }
    .kpi-box-num {
        font-size: 1.7rem;
        font-weight: 800;
        margin: 4px 0;
        color: #f8fafc;
    }
    .kpi-box-sub {
        font-size: 0.75rem;
        color: #94a3b8;
    }

    /* Distributor Magazine Section Headers */
    .dist-header-bar {
        background: linear-gradient(90deg, #1e3a8a 0%, #1e293b 100%);
        color: #ffffff;
        font-weight: 700;
        font-size: 1.05rem;
        padding: 8px 16px;
        border-radius: 8px;
        margin: 1.2rem 0 0.6rem 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Proposal Pitch Cards */
    .proposal-card {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
    .proposal-badge-gap {
        background: #ef4444;
        color: white;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .proposal-badge-ok {
        background: #10b981;
        color: white;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
    }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Pipeline Runner ────────────────────────────────────────────────────────
def run_pipeline_for_company(
    company_id: str,
    max_funds: int,
    use_llm: bool,
    force: bool,
    provider: str | None = None,
    workers: int = 5,
    log_func=None,
    prog_func=None,
) -> list[BenchmarkRecord]:
    from app.stage1_list import run_stage1
    from app.stage2_pdf_url import run_stage2
    from app.stage3_download import run_stage3
    from app.stage4_extract_text import run_stage4
    from app.stage5_benchmark import run_stage5

    ensure_dirs()
    setup_logging()

    company_names = {
        "nomura": "野村アセットマネジメント",
        "daiwa": "大和アセットマネジメント",
        "muam": "三菱UFJアセットマネジメント",
    }
    company_name = company_names.get(company_id, "野村アセットマネジメント")

    if log_func:
        log_func(f"🚀 {company_name} のパイプライン開始 (AUM上位 {max_funds}本)")

    # If not force and pre-extracted benchmark data exists, load and refresh instantaneously
    comp_json = DATA_DIR / f"{company_id}_benchmarks.json"
    if not force and comp_json.exists():
        raw = load_json(comp_json, [])
        if len(raw) >= min(max_funds, 20):
            recs = [BenchmarkRecord.model_validate(item) for item in raw[:max_funds]]
            for r in recs:
                r.management_company = company_name
                # Ensure theme & distributor fields are populated
                if not r.theme_category:
                    r.theme_category = classify_fund_theme(r.fund_name, r.benchmark)
                if not r.top_distributors:
                    dist_s, prim_s, act_s = resolve_fund_distributors(r.fund_name, company_name, r.is_etf)
                    r.top_distributors = dist_s
                    r.primary_broker = prim_s
                    r.sales_pitch_action = act_s
            if log_func:
                log_func(f"⚡ {company_name}: キャッシュから {len(recs)} 本を即時読み込み・最新指標同期完了")
            return recs

    # Live Pipeline Execution (safe max workers 3 to prevent Cloud OOM)
    safe_workers = min(workers, 4)

    # Stage 1
    if company_id == "daiwa":
        funds = run_stage1_daiwa(force=force, max_funds=max_funds)
    elif company_id == "muam":
        funds = run_stage1_muam(force=force, max_funds=max_funds)
    else:
        funds = run_stage1(force=force, max_funds=max_funds)
    if log_func:
        log_func(f"Stage 1 完了: {len(funds)} 本のファンド情報取得")

    # Stage 2
    if company_id not in ("daiwa", "muam"):
        run_stage2(force=force, max_workers=safe_workers)
    if log_func:
        log_func("Stage 2 完了: 交付目論見書URL解決")

    # Stage 3
    run_stage3(force=force, max_workers=safe_workers)
    if log_func:
        log_func("Stage 3 完了: PDFダウンロード完了")

    # Stage 4
    run_stage4(force=force, allow_ocr=False, max_workers=safe_workers)
    if log_func:
        log_func("Stage 4 完了: テキスト抽出完了")

    # Stage 5
    def _stage5_cb(done: int, total_cnt: int, item_name: str) -> None:
        if prog_func:
            prog_func(done, total_cnt, f"{company_name}: {item_name}")
        if (done % 5 == 0 or done == total_cnt) and log_func:
            log_func(f"Stage 5 進捗: {done}/{total_cnt} 本 ({item_name})")

    records = run_stage5(
        use_llm=use_llm,
        provider=provider,
        max_workers=safe_workers,
        progress_callback=_stage5_cb,
    )
    for r in records:
        r.management_company = company_name

    # Save company-specific copy
    save_json(comp_json, [r.model_dump(mode="json") for r in records])
    if log_func:
        log_func(f"✅ {company_name} 完了: {len(records)} 本の分析完了")

    return records



# ── Load existing data ─────────────────────────────────────────────────────
def load_records_for_companies(company_ids: list[str]) -> list[BenchmarkRecord]:
    combined_records: list[BenchmarkRecord] = []
    company_names = {
        "nomura": "野村アセットマネジメント",
        "daiwa": "大和アセットマネジメント",
        "muam": "三菱UFJアセットマネジメント",
    }

    for cid in company_ids:
        comp_json = DATA_DIR / f"{cid}_benchmarks.json"
        if comp_json.exists():
            raw = load_json(comp_json, [])
            recs = [BenchmarkRecord.model_validate(item) for item in raw]
            for r in recs:
                if not r.management_company or r.management_company == "野村アセットマネジメント":
                    r.management_company = company_names.get(cid, "野村アセットマネジメント")
            combined_records.extend(recs)
        elif cid == "nomura" and BENCHMARKS_JSON.exists():
            raw = load_json(BENCHMARKS_JSON, [])
            recs = [BenchmarkRecord.model_validate(item) for item in raw]
            for r in recs:
                r.management_company = "野村アセットマネジメント"
            combined_records.extend(recs)

    # Re-rank combined records by AUM descending
    combined_records.sort(key=lambda x: x.aum, reverse=True)
    for idx, r in enumerate(combined_records, start=1):
        r.rank = idx

    return combined_records


# ── Main Application ───────────────────────────────────────────────────────
def main() -> None:
    st.markdown("""
    <div class="app-header">
        <div class="header-badge">CONSULTATIVE SALES INTELLIGENCE</div>
        <h1>📊 ファンド・ベンチマーク抽出 & 販社営業インテリジェンス</h1>
        <p>野村・大和・三菱UFJ 3大運用会社対応 ｜ 資金純流入額（買い付け金額）推定 × 販売会社別ランキング × 商品企画マッチング</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar Configurations ─────────────────────────────────────────────
    with st.sidebar:
        st.header("🏢 対象運用会社の選択")
        company_options = {
            "nomura": "野村アセットマネジメント",
            "daiwa": "大和アセットマネジメント",
            "muam": "三菱UFJアセットマネジメント",
        }
        selected_company_ids = st.multiselect(
            "分析・実行対象（1社〜3社一括選択可能）",
            options=list(company_options.keys()),
            default=["nomura", "daiwa", "muam"],
            format_func=lambda x: company_options[x],
            help="1社のみ、2社、または3社同時に選択して一括実行・統合分析できます",
        )

        if not selected_company_ids:
            st.warning("⚠️ 少なくとも1社を選択してください。")
            selected_company_ids = ["nomura"]

        selected_company_labels = [company_options[cid] for cid in selected_company_ids]

        st.divider()
        st.header("⚙️ 実行・AI設定")

        # LLM Provider Selection
        available_providers = get_available_providers()
        prov_options = {"auto": "自動選択 (設定キー優先)"}
        for p in available_providers:
            prov_options[p["id"]] = f"{p['name']} ({p['model']})"

        selected_provider_key = st.selectbox(
            "🤖 LLMプロバイダー",
            options=list(prov_options.keys()),
            format_func=lambda x: prov_options[x],
            help="ベンチマーク抽出に使用するAIモデルを選択",
        )
        provider_arg = None if selected_provider_key == "auto" else selected_provider_key

        max_funds_per_company = st.slider(
            "1社あたりの取得ファンド数 (AUM順)",
            min_value=5,
            max_value=200,
            value=50,
            step=5,
        )

        workers = st.slider(
            "並行ワーカ数",
            min_value=1,
            max_value=10,
            value=5,
            help="ネットワーク並行処理ワーカ数",
        )

        use_llm = st.toggle("LLM抽出を有効化", value=True)
        force = st.toggle("キャッシュ無視で全再取得", value=False)

        st.divider()
        button_label = f"🚀 選択した運用会社（{len(selected_company_ids)}社）を一括実行"
        run_clicked = st.button(button_label, type="primary", use_container_width=True)

        st.divider()
        st.subheader("🔑 API Key 接続状態")
        col_k1, col_k2 = st.columns(2)
        col_k1.write(f"Claude: {'✅' if ANTHROPIC_API_KEY else '⚪'}")
        col_k2.write(f"Gemini: {'✅' if GEMINI_API_KEY else '⚪'}")
        col_k1.write(f"OpenAI: {'✅' if OPENAI_API_KEY else '⚪'}")

    # ── Run pipeline trigger ───────────────────────────────────────────────
    if run_clicked:
        prog_bar = st.progress(0, text="パイプライン初期化中...")
        status_text = st.empty()
        log_area = st.empty()
        logs: list[str] = []

        def log(msg: str) -> None:
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            log_area.code("\n".join(logs[-15:]), language="text")

        def prog(done: int, total_cnt: int, label: str) -> None:
            prog_bar.progress(min(done / total_cnt, 0.98), text=label)

        all_executed_records = []
        for c_idx, cid in enumerate(selected_company_ids, start=1):
            c_name = company_options[cid]
            status_text.info(f"[{c_idx}/{len(selected_company_ids)}] {c_name} を実行中...")
            try:
                c_records = run_pipeline_for_company(
                    company_id=cid,
                    max_funds=max_funds_per_company,
                    use_llm=use_llm,
                    force=force,
                    provider=provider_arg,
                    workers=workers,
                    log_func=log,
                    prog_func=prog,
                )
                all_executed_records.extend(c_records)
            except Exception as e:
                st.error(f"❌ {c_name} の実行エラー: {e}")

        if all_executed_records:
            # Re-export unified 5-sheet excel
            run_stage6(all_executed_records)
            prog_bar.progress(1.0, text="✅ 全社のパイプラインが完了しました!")
            status_text.success(f"✅ 選択された {len(selected_company_ids)} 社（合計 {len(all_executed_records)}本）の実行が正常に完了しました!")
            st.session_state["cached_records"] = all_executed_records

    # Load data for selected companies
    records = st.session_state.get("cached_records")
    if not records:
        records = load_records_for_companies(selected_company_ids)
        if records:
            st.session_state["cached_records"] = records

    if not records:
        st.info("💡 サイドバーの「一括実行」ボタンをクリックしてデータを取得してください。")
        return

    # ── Top Level Tabs ─────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        f"📈 マーケット & 資金流入分析 ({' / '.join(selected_company_labels)})",
        "🏛️ 販売会社別ファンド一覧（販社別ランキング）",
        "📋 全ファンド一覧 & レビュー",
        "💡 商品企画提案 & 販社マッチング",
        "🔍 目論見書 & フローインスペクター",
    ])

    # ── Calculate Metrics ──────────────────────────────────────────────────
    total_aum = sum(r.aum for r in records)
    total_count = len(records)
    msci_records = [r for r in records if r.is_msci]
    msci_aum = sum(r.aum for r in msci_records)
    msci_count = len(msci_records)
    total_inflow = sum(r.estimated_net_inflow for r in records)
    non_msci_inflow = sum(r.estimated_net_inflow for r in records if not r.is_msci)

    msci_aum_share = (msci_aum / total_aum * 100) if total_aum else 0
    msci_count_share = (msci_count / total_count * 100) if total_count else 0

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 1: ANALYTICS & MARKET SHARE
    # ═══════════════════════════════════════════════════════════════════════
    with tab1:
        st.markdown(f"""
        <div class="kpi-container">
            <div class="kpi-box">
                <div class="kpi-box-title">総ファンド数 ({len(selected_company_ids)}社合計)</div>
                <div class="kpi-box-num">{total_count}</div>
                <div class="kpi-box-sub">AUM合計: {total_aum / 1e12:.2f} 兆円</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-box-title">MSCI 採用 AUM</div>
                <div class="kpi-box-num" style="color: #34d399;">{msci_aum / 1e12:.2f} 兆円</div>
                <div class="kpi-box-sub">AUMシェア: {msci_aum_share:.1f}% ({msci_count}本)</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-box-title">総 推定純流入額</div>
                <div class="kpi-box-num" style="color: {'#38bdf8' if total_inflow >= 0 else '#f87171'};">{format_inflow_oku(total_inflow)}</div>
                <div class="kpi-box-sub">直近純資金フロー</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-box-title">非MSCI 純流入額 (攻めどころ)</div>
                <div class="kpi-box-num" style="color: #fbbf24;">{format_inflow_oku(non_msci_inflow)}</div>
                <div class="kpi-box-sub">リプレイス・新規提案余地</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-box-title">要確認 (レビュー待ち)</div>
                <div class="kpi-box-num" style="color: #cbd5e1;">{sum(1 for r in records if r.needs_review)}</div>
                <div class="kpi-box-sub">要レビュー件数</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_a1, col_a2 = st.columns([1, 1])

        with col_a1:
            st.subheader("🔥 資金純流入ランキング Top 10 (全社横断)")
            sorted_by_flow = sorted(records, key=lambda x: x.estimated_net_inflow, reverse=True)[:10]
            flow_df = pd.DataFrame([
                {
                    "ファンド名": f"[{r.management_company[:2]}] {r.fund_name[:18]}...",
                    "推定純流入 (億円)": round(r.estimated_net_inflow / 1e8, 1),
                    "MSCI": "MSCI" if r.is_msci else "他社",
                }
                for r in sorted_by_flow
            ])
            st.bar_chart(
                flow_df.set_index("ファンド名")["推定純流入 (億円)"],
                color="#38bdf8",
                x_label="ファンド",
                y_label="純流入額 (億円)",
            )

        with col_a2:
            st.subheader("🏷️ テーマ別 純資産 & 純流入額")
            theme_agg: dict[str, dict] = {}
            for r in records:
                t = r.theme_category or "全世界・先進国株式"
                if t not in theme_agg:
                    theme_agg[t] = {"theme": t, "aum_oku": 0.0, "inflow_oku": 0.0, "count": 0}
                theme_agg[t]["aum_oku"] += r.aum / 1e8
                theme_agg[t]["inflow_oku"] += r.estimated_net_inflow / 1e8
                theme_agg[t]["count"] += 1

            theme_df = pd.DataFrame(list(theme_agg.values()))
            theme_df.sort_values(by="inflow_oku", ascending=False, inplace=True)
            st.dataframe(
                theme_df.rename(columns={
                    "theme": "テーマ分類",
                    "count": "本数",
                    "aum_oku": "AUM合計(億円)",
                    "inflow_oku": "純流入合計(億円)",
                }),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()
        st.subheader("🎯 営業ターゲット（資金流入が大きく非MSCIのファンド）")
        non_msci = [r for r in records if not r.is_msci and r.aum > 0]
        non_msci.sort(key=lambda x: (x.estimated_net_inflow, x.aum), reverse=True)

        targets_data = []
        for t in non_msci[:12]:
            targets_data.append({
                "順位": t.rank,
                "運用会社": t.management_company,
                "ファンド名": t.fund_name,
                "AUM (億円)": round(t.aum / 1e8, 0),
                "推定純流入 (億円)": format_inflow_oku(t.estimated_net_inflow),
                "テーマ": t.theme_category,
                "現ベンチマーク": t.benchmark or "—",
                "主要販売会社 (Broker)": t.top_distributors or t.primary_broker or "主要証券",
                "営業アクション (Who to Call)": t.sales_pitch_action or "🎯 アプローチ対象",
            })
        targets_df = pd.DataFrame(targets_data)
        st.dataframe(
            targets_df,
            use_container_width=True,
            hide_index=True,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 2: DISTRIBUTOR RANKINGS (ATTACHED FORMAT REPLICATION)
    # ═══════════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("🏛️ 販売会社別 取扱商品ランキング（添付フォーマット準拠）")
        st.caption("各販売会社（野村證券、大和証券、みずほFG、三菱UFJ、三井住友信託、SMBC日興、SBI証券、楽天証券、りそな銀行、日本生命 等）が主力として販売しているファンドと残高・純流入一覧")

        col_b1, col_b2 = st.columns([1, 2])
        dist_filter = col_b1.selectbox(
            "表示する販売会社を選択",
            options=["全販売会社を表示"] + MAJOR_DISTRIBUTORS,
        )

        dist_groups = get_funds_grouped_by_distributor(records)

        target_distributors = MAJOR_DISTRIBUTORS if dist_filter == "全販売会社を表示" else [dist_filter]

        for dist_name in target_distributors:
            funds_in_dist = dist_groups.get(dist_name, [])
            if not funds_in_dist:
                continue

            st.markdown(f"""
            <div class="dist-header-bar">
                <span>🏛️</span> <span>{dist_name} 取扱上位ファンド一覧（残高順）</span>
                <span style="font-size: 0.8rem; font-weight: normal; margin-left: auto;">取扱上位 {len(funds_in_dist)} 本</span>
            </div>
            """, unsafe_allow_html=True)

            d_df = pd.DataFrame([
                {
                    "順位": f["rank"],
                    "運用商品名 (ファンド名)": f["fund_name"],
                    "運用会社": f["management_company"],
                    "残高 (億円)": f["aum_oku"],
                    "推定純流入 (億円)": format_inflow_oku(f["inflow_oku"] * 1e8),
                    "ベンチマーク指数": f["benchmark"],
                    "MSCI採用": "🟢 MSCI" if f["is_msci"] else "⚪ 他社",
                    "営業アプローチ戦略": f["action"],
                }
                for f in funds_in_dist
            ])

            st.dataframe(
                d_df,
                use_container_width=True,
                hide_index=True,
            )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: ALL FUNDS LIST & INTERACTIVE REVIEW
    # ═══════════════════════════════════════════════════════════════════════
    with tab3:
        col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 2])
        search_query = col_f1.text_input("🔍 検索", placeholder="ファンド名・コード・ベンチマーク・販社...")
        theme_filter = col_f2.selectbox("テーマ分類", options=["全て"] + THEMES)
        review_filter = col_f3.selectbox(
            "ステータス",
            options=["全て", "純流入プラスのみ", "非MSCIのみ", "要確認のみ", "手動編集のみ"],
        )

        # Export buttons
        with col_f4:
            st.write("📥 レポート出力 (5シート構成)")
            col_d1, col_d2 = st.columns(2)
            xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"
            csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"

            if xlsx_path.exists():
                with open(xlsx_path, "rb") as f:
                    col_d1.download_button(
                        "📊 Excel (5シート)",
                        f.read(),
                        file_name="fund_benchmark_broker_intelligence.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            if csv_path.exists():
                with open(csv_path, "rb") as f:
                    col_d2.download_button(
                        "📄 CSV",
                        f.read(),
                        file_name="fund_benchmarks.csv",
                        mime="text/csv",
                    )

        # Filter records
        filtered_records = records
        if search_query:
            q = search_query.lower()
            filtered_records = [
                r for r in filtered_records
                if q in r.fund_name.lower() or q in r.fund_code.lower() or q in (r.benchmark or "").lower() or q in (r.top_distributors or "").lower() or q in (r.management_company or "").lower()
            ]
        if theme_filter != "全て":
            filtered_records = [r for r in filtered_records if r.theme_category == theme_filter]
        if review_filter == "純流入プラスのみ":
            filtered_records = [r for r in filtered_records if r.estimated_net_inflow > 0]
        elif review_filter == "非MSCIのみ":
            filtered_records = [r for r in filtered_records if not r.is_msci]
        elif review_filter == "要確認のみ":
            filtered_records = [r for r in filtered_records if r.needs_review]
        elif review_filter == "手動編集のみ":
            filtered_records = [r for r in filtered_records if r.manual_override]

        # Prepare editable DataFrame
        edit_rows = []
        for r in filtered_records:
            edit_rows.append({
                "順位": r.rank,
                "運用会社": r.management_company,
                "ファンド名": r.fund_name,
                "コード": r.fund_code,
                "AUM (億円)": round(r.aum / 1e8, 0) if r.aum else 0,
                "推定純流入 (億円)": format_inflow_oku(r.estimated_net_inflow),
                "テーマ分類": r.theme_category or "全世界・先進国株式",
                "ベンチマーク指数": r.benchmark or "",
                "指数提供者": r.index_provider or "なし",
                "MSCI": "🟢 MSCI" if r.is_msci else "⚪ 他社",
                "主要販売会社 (Broker)": r.top_distributors or r.primary_broker or "主要証券",
                "営業アクション": r.sales_pitch_action or "",
                "要確認": r.needs_review,
                "レビューメモ": r.review_comment or "",
                "手動": "✏️" if r.manual_override else "",
            })

        table_df = pd.DataFrame(edit_rows)

        st.caption(f"該当件数: {len(table_df)} 件 (テーブル内をダブルクリックで直接編集できます)")
        edited_df = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            height=500,
            disabled=["順位", "運用会社", "ファンド名", "コード", "AUM (億円)", "推定純流入 (億円)", "MSCI", "手動"],
        )

        # Save changes button
        if st.button("💾 編集内容を一括保存", type="primary"):
            updated_count = 0
            for _, row in edited_df.iterrows():
                code = row["コード"]
                bm = row["ベンチマーク指数"]
                prov = row["指数提供者"]
                theme = row["テーマ分類"]
                dist = row["主要販売会社 (Broker)"]
                action = row["営業アクション"]
                needs_rev = bool(row["要確認"])
                comm = str(row["レビューメモ"])

                orig = next((r for r in records if r.fund_code == code), None)
                if orig and (orig.benchmark != bm or orig.index_provider != prov or orig.theme_category != theme or orig.top_distributors != dist or orig.sales_pitch_action != action or orig.needs_review != needs_rev or orig.review_comment != comm):
                    update_manual_override(
                        fund_code=code,
                        benchmark=bm,
                        index_provider=prov,
                        needs_review=needs_rev,
                        comment=comm,
                        reviewer="Streamlit Analyst",
                    )
                    orig.theme_category = theme
                    orig.top_distributors = dist
                    orig.sales_pitch_action = action
                    updated_count += 1

            if updated_count > 0:
                st.success(f"✅ {updated_count} 件の変更を保存しました!")
                st.session_state["cached_records"] = records
                st.rerun()
            else:
                st.info("変更はありませんでした。")

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: PRODUCT PROPOSALS & BROKER MATCHMAKER
    # ═══════════════════════════════════════════════════════════════════════
    with tab4:
        st.subheader("💡 運用会社向け 商品企画提案 & 販社マッチング")
        st.write("運用会社の商品企画部へ「**今どのテーマに資金が集まっており、どの販売会社と組めば最も売れるか**」を提案するためのコンサルティングインテリジェンスです。")

        company_for_pitch = st.selectbox(
            "提案対象のアセットマネジメント会社",
            options=selected_company_labels,
        )

        firm_records = [r for r in records if r.management_company == company_for_pitch] or records
        proposals = generate_product_proposals(firm_records, company_for_pitch)

        col_p1, col_p2 = st.columns([1, 1])

        with col_p1:
            st.markdown(f"### 🧩 {company_for_pitch} ラインアップ・ギャップ分析")
            for prop in proposals:
                is_gap = "ギャップ" in prop["status"]
                badge_class = "proposal-badge-gap" if is_gap else "proposal-badge-ok"
                st.markdown(f"""
                <div class="proposal-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 1.1rem; font-weight: 700;">{prop['theme']}</span>
                        <span class="{badge_class}">{prop['status']}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 6px;">
                        自社現保有本数: <b>{prop['existing_funds_count']} 本</b> ｜ 自社AUM: <b>{prop['theme_aum_display']}</b> ｜ 自社純流入: <b>{prop['theme_inflow_display']}</b>
                    </div>
                    <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; font-size: 0.85rem; margin-top: 8px;">
                        <b style="color: #38bdf8;">推奨MSCI指数:</b> {prop['recommended_msci_index']}<br/>
                        <b style="color: #fbbf24;">最適主幹販社:</b> {prop['best_selling_brokers']}<br/>
                        <span style="color: #cbd5e1; font-size: 0.8rem;">{prop['proposal_narrative']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with col_p2:
            st.markdown("### 🏢 販社 × テーマ別 売れ行きマトリクス")
            st.caption("どの販売会社経由だと、どのテーマが最も売れているかを可視化")

            matrix_rows = build_broker_theme_sales_matrix(records)
            matrix_df = pd.DataFrame([
                {
                    "販売会社 (Broker)": m["broker"],
                    "得意テーマ": m["theme"],
                    "取扱本数": m["fund_count"],
                    "AUM合計 (億円)": round(m["total_aum"] / 1e8, 1),
                    "推定純流入 (億円)": format_inflow_oku(m["total_inflow"]),
                }
                for m in matrix_rows[:12]
            ])
            st.dataframe(
                matrix_df,
                use_container_width=True,
                hide_index=True,
            )

            st.markdown(f"""
            > **💡 提案トークの活用例（対 {company_for_pitch}）**:
            > *「御社のラインアップにはAI・半導体分野が不足しています。市場ではこのテーマに年間+2,000億円超の純流入が発生しており、特に**SBI証券・楽天証券**での売れ行きが突出しています。ぜひ**MSCI AI & Robotics指数**を採用し、ネット証券を主幹販社とした新商品を企画しませんか？」*
            """)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 5: PROSPECTUS INSPECTOR & SINGLE RE-EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    with tab5:
        st.subheader("🔍 目論見書 & フローインスペクター")
        fund_options = {r.fund_code: f"#{r.rank} [{r.management_company[:2]}] {r.fund_name} ({format_aum_oku(r.aum)} / {format_inflow_oku(r.estimated_net_inflow)})" for r in records}
        selected_code = st.selectbox(
            "確認するファンドを選択",
            options=list(fund_options.keys()),
            format_func=lambda x: fund_options[x],
        )

        selected_record = next((r for r in records if r.fund_code == selected_code), None)

        if selected_record:
            col_i1, col_i2 = st.columns([1, 1])

            with col_i1:
                st.markdown(f"### {selected_record.fund_name}")
                st.write(f"**運用会社**: `{selected_record.management_company}` ｜ **テーマ**: `{selected_record.theme_category}`")
                st.write(f"**純資産(AUM)**: {format_aum_oku(selected_record.aum)} ｜ **推定純流入**: `{format_inflow_oku(selected_record.estimated_net_inflow)}`")
                st.write(f"**現在のベンチマーク**: `{selected_record.benchmark or 'なし'}` ({selected_record.index_provider})")
                st.write(f"**MSCI採用**: {'🟢 はい' if selected_record.is_msci else 'いいえ'}")
                st.write(f"**主要販売会社**: `{selected_record.top_distributors or '主要証券'}`")
                st.write(f"**営業アクション**: `{selected_record.sales_pitch_action or '—'}`")

                if selected_record.prospectus_pdf_url:
                    st.link_button("📄 交付目論見書PDFを開く", selected_record.prospectus_pdf_url)

                st.divider()
                st.write("🛠️ **単体アクション**")
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("🔄 AI単体再抽出", key=f"reextract_{selected_code}"):
                    with st.spinner("AI再抽出を実行中..."):
                        new_rec = reextract_single_fund(
                            fund_code=selected_code,
                            use_llm=True,
                            provider=provider_arg,
                        )
                        if new_rec:
                            st.success(f"再抽出完了: {new_rec.benchmark} ({new_rec.index_provider})")
                            st.session_state["cached_records"] = load_records_for_companies(selected_company_ids)
                            st.rerun()

                if col_btn2.button("🔍 強制OCR再抽出", key=f"ocr_{selected_code}"):
                    with st.spinner("強制OCRを実行中..."):
                        new_rec = reextract_single_fund(
                            fund_code=selected_code,
                            use_llm=True,
                            provider=provider_arg,
                            force_ocr=True,
                        )
                        if new_rec:
                            st.success(f"OCR再抽出完了: {new_rec.benchmark} ({new_rec.index_provider})")
                            st.session_state["cached_records"] = load_records_for_companies(selected_company_ids)
                            st.rerun()

            with col_i2:
                st.markdown("### 📄 抽出テキスト (目論見書)")
                text_path = TEXT_DIR / f"{selected_code}.txt"
                if text_path.exists():
                    raw_text = text_path.read_text(encoding="utf-8")
                    st.text_area("テキスト内容", raw_text[:10000], height=450, disabled=True)
                else:
                    st.warning("テキストファイルが存在しません。パイプラインを実行してください。")


if __name__ == "__main__":
    try:
        main()
    except Exception as _app_exc:
        st.error(f"⚠️ アプリケーション実行エラー: {_app_exc}")
        st.exception(_app_exc)
