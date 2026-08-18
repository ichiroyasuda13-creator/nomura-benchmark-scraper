"""Streamlit web app for Multi-Asset Management Benchmark Scraper & Intelligence.

Features:
- Multi-Asset Managers: 野村アセット, 大和アセット, 三菱UFJアセット
- Net Inflow (買い付け金額 / 推定純流入) & Performance Effect Calculation
- Broker & Distributor Intelligence (主要販売会社 & 販社別売れ行き)
- Theme & Gap Analysis for Consultative Product Proposals
- Interactive Data Editor & 4-Sheet Excel Generation
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
    from app.distributors import build_broker_theme_sales_matrix, resolve_fund_distributors
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
def run_pipeline(
    company_id: str,
    max_funds: int,
    use_llm: bool,
    force: bool,
    provider: str | None = None,
    workers: int = 5,
) -> list[BenchmarkRecord]:
    from app.stage1_list import run_stage1
    from app.stage2_pdf_url import run_stage2
    from app.stage3_download import run_stage3
    from app.stage4_extract_text import run_stage4
    from app.stage5_benchmark import run_stage5
    from app.stage6_output import run_stage6

    ensure_dirs()
    setup_logging()

    prog_bar = st.progress(0, text="パイプライン初期化中...")
    status_text = st.empty()
    log_area = st.empty()
    logs: list[str] = []

    def log(msg: str) -> None:
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        log_area.code("\n".join(logs[-15:]), language="text")

    company_names = {
        "nomura": "野村アセットマネジメント",
        "daiwa": "大和アセットマネジメント",
        "muam": "三菱UFJアセットマネジメント",
    }
    company_name = company_names.get(company_id, "野村アセットマネジメント")

    # Stage 1
    prog_bar.progress(1 / 7, text=f"Stage 1/6: {company_name} ファンド一覧取得中...")
    status_text.info(f"Stage 1: {company_name} 公式APIからAUM上位ファンドを取得中...")
    if company_id == "daiwa":
        funds = run_stage1_daiwa(force=force, max_funds=max_funds)
    elif company_id == "muam":
        funds = run_stage1_muam(force=force, max_funds=max_funds)
    else:
        funds = run_stage1(force=force, max_funds=max_funds)
    log(f"Stage 1 完了: {len(funds)} 本のファンド情報を取得")

    # Stage 2
    prog_bar.progress(2 / 7, text="Stage 2/6: 交付目論見書PDF URL解決中...")
    status_text.info(f"Stage 2: PDF URLを並行解決中 (並行数: {workers})...")
    if company_id not in ("daiwa", "muam"):
        run_stage2(force=force, max_workers=workers)
    log("Stage 2 完了: 交付目論見書URL解決完了")

    # Stage 3
    prog_bar.progress(3 / 7, text="Stage 3/6: PDFダウンロード中...")
    status_text.info(f"Stage 3: 交付目論見書PDFをダウンロード中 (並行数: {workers})...")
    run_stage3(force=force, max_workers=workers)
    log("Stage 3 完了: PDFダウンロード完了")

    # Stage 4
    prog_bar.progress(4 / 7, text="Stage 4/6: テキスト抽出中...")
    status_text.info("Stage 4: PyMuPDF / OCRで目論見書テキストを抽出中...")
    run_stage4(force=force, allow_ocr=True, max_workers=workers)
    log("Stage 4 完了: テキスト抽出完了")

    # Stage 5
    prov_label = provider or "Auto"
    prog_bar.progress(5 / 7, text=f"Stage 5/6: ベンチマーク・純流入・販社並行抽出中 (LLM: {prov_label}, 並行数: {workers})...")
    status_text.info(f"Stage 5: ベンチマーク指数・推定純流入・主要販社を並行分析中 (並行数: {workers})...")

    def _stage5_progress(done: int, total_cnt: int, item_name: str) -> None:
        pct = 5 / 7 + (done / total_cnt) * (1 / 7)
        prog_bar.progress(min(pct, 0.95), text=f"Stage 5/6: {done}/{total_cnt} 本抽出完了 ({item_name})")
        if done % 5 == 0 or done == total_cnt:
            log(f"Stage 5 進捗: {done}/{total_cnt} 本 ({item_name})")

    records = run_stage5(
        use_llm=use_llm,
        provider=provider,
        max_workers=workers,
        progress_callback=_stage5_progress,
    )
    log(f"Stage 5 完了: {len(records)} 本のベンチマーク・フロー分析完了")


    # Save company-specific copy
    comp_json = DATA_DIR / f"{company_id}_benchmarks.json"
    save_json(comp_json, [r.model_dump(mode="json") for r in records])

    # Stage 6
    prog_bar.progress(6 / 7, text="Stage 6/6: 4シート構成Excel & CSV出力中...")
    status_text.info("Stage 6: スタイル適用済み多機能Excelレポート（4シート）とCSVを生成中...")
    run_stage6(records)
    log("Stage 6 完了: Excel (4シート) / CSV 出力完了")

    prog_bar.progress(1.0, text="✅ 全ステージ完了!")
    status_text.success(f"✅ {company_name} のパイプラインが正常に完了しました!")
    return records


# ── Load existing data ─────────────────────────────────────────────────────
def load_records_for_company(company_id: str) -> list[BenchmarkRecord]:
    comp_json = DATA_DIR / f"{company_id}_benchmarks.json"
    if comp_json.exists():
        raw = load_json(comp_json, [])
        return [BenchmarkRecord.model_validate(item) for item in raw]
    if BENCHMARKS_JSON.exists():
        raw = load_json(BENCHMARKS_JSON, [])
        return [BenchmarkRecord.model_validate(item) for item in raw]
    return []


# ── Main Application ───────────────────────────────────────────────────────
def main() -> None:
    st.markdown("""
    <div class="app-header">
        <div class="header-badge">CONSULTATIVE SALES INTELLIGENCE</div>
        <h1>📊 ファンド・ベンチマーク抽出 & 販社営業インテリジェンス</h1>
        <p>野村・大和・三菱UFJ 3大運用会社対応 ｜ 資金純流入額（買い付け金額）推定 × 主要販売会社 × 商品企画マッチング</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar Configurations ─────────────────────────────────────────────
    with st.sidebar:
        st.header("🏢 運用会社の選択")
        company_options = {
            "nomura": "野村アセットマネジメント",
            "daiwa": "大和アセットマネジメント",
            "muam": "三菱UFJアセットマネジメント",
        }
        selected_company_id = st.selectbox(
            "対象運用会社",
            options=list(company_options.keys()),
            format_func=lambda x: company_options[x],
            help="分析・スクレイピング対象の資産運用会社を選択",
        )
        selected_company_name = company_options[selected_company_id]

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

        max_funds = st.slider(
            "取得ファンド数 (AUM順)",
            min_value=5,
            max_value=200,
            value=100,
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
        run_clicked = st.button(
            f"🚀 {selected_company_name} 実行開始",
            type="primary",
            use_container_width=True,
        )

        st.divider()
        st.subheader("🔑 API Key 接続状態")
        col_k1, col_k2 = st.columns(2)
        col_k1.write(f"Claude: {'✅' if ANTHROPIC_API_KEY else '⚪'}")
        col_k2.write(f"Gemini: {'✅' if GEMINI_API_KEY else '⚪'}")
        col_k1.write(f"OpenAI: {'✅' if OPENAI_API_KEY else '⚪'}")

    # ── Run pipeline trigger ───────────────────────────────────────────────
    if run_clicked:
        try:
            records = run_pipeline(
                company_id=selected_company_id,
                max_funds=max_funds,
                use_llm=use_llm,
                force=force,
                provider=provider_arg,
                workers=workers,
            )
            st.session_state[f"records_{selected_company_id}"] = records
        except Exception as e:
            st.error(f"❌ 実行エラー: {e}")

    # Load data for selected company
    records = st.session_state.get(f"records_{selected_company_id}")
    if not records:
        records = load_records_for_company(selected_company_id)
        if records:
            st.session_state[f"records_{selected_company_id}"] = records

    if not records:
        st.info(f"💡 サイドバーの「{selected_company_name} 実行開始」をクリックしてデータを取得してください。")
        return

    # ── Top Level Tabs ─────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        f"📈 {selected_company_name} マーケット & 資金流入分析",
        "📋 ファンド一覧 & 純流入・販社レビュー",
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
                <div class="kpi-box-title">総ファンド数 ({selected_company_name})</div>
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
            st.subheader("🔥 資金純流入ランキング (Top Net Inflows)")
            sorted_by_flow = sorted(records, key=lambda x: x.estimated_net_inflow, reverse=True)[:10]
            flow_df = pd.DataFrame([
                {
                    "ファンド名": r.fund_name[:20] + "...",
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
        st.subheader(f"🎯 {selected_company_name} 営業ターゲット（資金流入が大きく非MSCIのファンド）")
        non_msci = [r for r in records if not r.is_msci and r.aum > 0]
        non_msci.sort(key=lambda x: (x.estimated_net_inflow, x.aum), reverse=True)

        targets_data = []
        for t in non_msci[:10]:
            targets_data.append({
                "順位": t.rank,
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
    # TAB 2: FUND LIST & INTERACTIVE REVIEW
    # ═══════════════════════════════════════════════════════════════════════
    with tab2:
        col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 2])
        search_query = col_f1.text_input("🔍 検索", placeholder="ファンド名・コード・ベンチマーク・販社...")
        theme_filter = col_f2.selectbox("テーマ分類", options=["全て"] + THEMES)
        review_filter = col_f3.selectbox(
            "ステータス",
            options=["全て", "純流入プラスのみ", "非MSCIのみ", "要確認のみ", "手動編集のみ"],
        )

        # Export buttons
        with col_f4:
            st.write("📥 レポート出力 (4シート構成)")
            col_d1, col_d2 = st.columns(2)
            xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"
            csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"

            if xlsx_path.exists():
                with open(xlsx_path, "rb") as f:
                    col_d1.download_button(
                        "📊 Excel (4シート)",
                        f.read(),
                        file_name=f"{selected_company_id}_benchmarks_intelligence.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            if csv_path.exists():
                with open(csv_path, "rb") as f:
                    col_d2.download_button(
                        "📄 CSV",
                        f.read(),
                        file_name=f"{selected_company_id}_benchmarks.csv",
                        mime="text/csv",
                    )

        # Filter records
        filtered_records = records
        if search_query:
            q = search_query.lower()
            filtered_records = [
                r for r in filtered_records
                if q in r.fund_name.lower() or q in r.fund_code.lower() or q in (r.benchmark or "").lower() or q in (r.top_distributors or "").lower()
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
                "ファンド名": r.fund_name,
                "コード": r.fund_code,
                "AUM (億円)": round(r.aum / 1e8, 0) if r.aum else 0,
                "推定純流入 (億円)": format_inflow_oku(r.estimated_net_inflow),
                "運用効果 (億円)": format_inflow_oku(r.performance_effect),
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

        st.caption(f"該当件数: {len(table_df)} 件 (テーブル内をダブルクリックでベンチマーク指数・提供者・テーマ・メモを直接編集できます)")
        edited_df = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            height=500,
            disabled=["順位", "ファンド名", "コード", "AUM (億円)", "推定純流入 (億円)", "運用効果 (億円)", "MSCI", "手動"],
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
                comp_json = DATA_DIR / f"{selected_company_id}_benchmarks.json"
                save_json(comp_json, [r.model_dump(mode="json") for r in records])
                st.success(f"✅ {updated_count} 件の変更を保存しました!")
                st.session_state[f"records_{selected_company_id}"] = records
                st.rerun()
            else:
                st.info("変更はありませんでした。")

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: PRODUCT PROPOSALS & BROKER MATCHMAKER
    # ═══════════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader(f"💡 {selected_company_name} 向け 商品企画提案 & 販社マッチング")
        st.write("運用会社の商品企画部へ「**今どのテーマに資金が集まっており、どの販売会社と組めば最も売れるか**」を提案するためのコンサルティングインテリジェンスです。")

        proposals = generate_product_proposals(records, selected_company_name)

        col_p1, col_p2 = st.columns([1, 1])

        with col_p1:
            st.markdown("### 🧩 商品ラインアップ・ギャップ分析")
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

            st.markdown("""
            > **💡 提案トークの活用例**:
            > *「御社のラインアップにはAI・半導体分野が不足しています。市場ではこのテーマに年間+2,000億円超の純流入が発生しており、特に**SBI証券・楽天証券**での売れ行きが突出しています。ぜひ**MSCI AI & Robotics指数**を採用し、ネット証券を主幹販社とした新商品を企画しませんか？」*
            """)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: PROSPECTUS INSPECTOR & SINGLE RE-EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    with tab4:
        st.subheader("🔍 目論見書 & フローインスペクター")
        fund_options = {r.fund_code: f"#{r.rank} - {r.fund_name} ({format_aum_oku(r.aum)} / {format_inflow_oku(r.estimated_net_inflow)})" for r in records}
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
                st.write(f"**運用会社**: `{selected_company_name}` ｜ **テーマ**: `{selected_record.theme_category}`")
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
                            st.session_state[f"records_{selected_company_id}"] = load_records_for_company(selected_company_id)
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
                            st.session_state[f"records_{selected_company_id}"] = load_records_for_company(selected_company_id)
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

