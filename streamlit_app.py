"""Streamlit web app for Multi-Asset Management Benchmark Scraper & Intelligence.

Supports:
- 野村アセットマネジメント (Nomura AM)
- 大和アセットマネジメント (Daiwa AM)
- 三菱UFJアセットマネジメント (MUAM)
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

# ── Ensure project root is importable ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
from app.http_client import load_json, save_json, setup_logging
from app.llm import get_available_providers, llm_available
from app.models import BenchmarkRecord, Confidence, Fund, FundType, format_aum_oku
from app.muam_stage1 import run_stage1_muam
from app.stage5_benchmark import reextract_single_fund, update_manual_override

# ── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ファンド・ベンチマーク抽出 & MSCI営業インテリジェンス",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .kpi-box {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        backdrop-filter: blur(12px);
    }
    .kpi-box-title {
        font-size: 0.72rem;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 700;
    }
    .kpi-box-num {
        font-size: 1.9rem;
        font-weight: 800;
        margin: 4px 0;
        color: #f8fafc;
    }
    .kpi-box-sub {
        font-size: 0.78rem;
        color: #94a3b8;
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
    prog_bar.progress(5 / 7, text=f"Stage 5/6: ベンチマーク抽出中 (LLM: {prov_label})...")
    status_text.info(f"Stage 5: ベンチマーク指数と提供者を抽出中 (LLM Provider: {prov_label})...")
    records = run_stage5(use_llm=use_llm, provider=provider)
    log(f"Stage 5 完了: {len(records)} 本のベンチマーク抽出完了")

    # Save company-specific copy
    comp_json = DATA_DIR / f"{company_id}_benchmarks.json"
    save_json(comp_json, [r.model_dump(mode="json") for r in records])

    # Stage 6
    prog_bar.progress(6 / 7, text="Stage 6/6: 多機能Excel & CSV出力中...")
    status_text.info("Stage 6: スタイル適用済み多機能ExcelレポートとCSVを生成中...")
    run_stage6(records)
    log("Stage 6 完了: Excel / CSV 出力完了")

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
        <div class="header-badge">ENTERPRISE EDITION</div>
        <h1>📊 ファンド・ベンチマーク抽出 & MSCI営業インテリジェンス</h1>
        <p>野村・大和・三菱UFJ 3大運用会社対応 ｜ 交付目論見書PDFからのマルチLLMベンチマーク自動抽出 & マーケットシェア分析</p>
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
    tab1, tab2, tab3 = st.tabs([
        f"📈 {selected_company_name} マーケット & MSCI営業分析",
        "📋 ファンド一覧 & レビュー",
        "🔍 目論見書インスペクター & 単体再抽出",
    ])

    # ── Calculate Metrics ──────────────────────────────────────────────────
    total_aum = sum(r.aum for r in records)
    total_count = len(records)
    msci_records = [r for r in records if r.is_msci]
    msci_aum = sum(r.aum for r in msci_records)
    msci_count = len(msci_records)
    review_count = sum(1 for r in records if r.needs_review)

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
                <div class="kpi-box-title">MSCI 採用ファンド数</div>
                <div class="kpi-box-num" style="color: #38bdf8;">{msci_count}</div>
                <div class="kpi-box-sub">件数シェア: {msci_count_share:.1f}%</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-box-title">MSCI 採用 AUM</div>
                <div class="kpi-box-num" style="color: #34d399;">{msci_aum / 1e12:.2f} 兆円</div>
                <div class="kpi-box-sub">AUMシェア: {msci_aum_share:.1f}%</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-box-title">要確認 (レビュー待ち)</div>
                <div class="kpi-box-num" style="color: #fbbf24;">{review_count}</div>
                <div class="kpi-box-sub">確度要確認または未確定</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_a1, col_a2 = st.columns([1, 1])

        with col_a1:
            st.subheader("🏛️ 指数提供者別 AUMシェア")
            prov_agg: dict[str, dict] = {}
            for r in records:
                p = r.index_provider or "なし"
                if p not in prov_agg:
                    prov_agg[p] = {"provider": p, "aum_oku": 0.0, "count": 0, "is_msci": r.is_msci}
                prov_agg[p]["aum_oku"] += r.aum / 1e8
                prov_agg[p]["count"] += 1

            prov_df = pd.DataFrame(list(prov_agg.values()))
            prov_df.sort_values(by="aum_oku", ascending=False, inplace=True)
            prov_df["aum_share"] = (prov_df["aum_oku"] / (total_aum / 1e8) * 100).round(1)

            st.bar_chart(
                prov_df.set_index("provider")["aum_oku"],
                color="#6366f1",
                x_label="指数提供者",
                y_label="純資産総額 (億円)",
            )

        with col_a2:
            st.subheader(f"🎯 {selected_company_name} 営業ターゲット (非MSCI高AUM)")
            non_msci = [r for r in records if not r.is_msci and r.aum > 0]
            non_msci.sort(key=lambda x: x.aum, reverse=True)

            targets_data = []
            for t in non_msci[:8]:
                targets_data.append({
                    "順位": t.rank,
                    "ファンド名": t.fund_name,
                    "AUM (億円)": round(t.aum / 1e8, 0),
                    "現ベンチマーク": t.benchmark or "—",
                    "現提供会社": t.index_provider,
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
        search_query = col_f1.text_input("🔍 検索", placeholder="ファンド名・コード・ベンチマーク...")
        prov_filter = col_f2.selectbox(
            "指数提供者",
            options=["全て"] + sorted(list({r.index_provider for r in records if r.index_provider})),
        )
        review_filter = col_f3.selectbox(
            "ステータス",
            options=["全て", "要確認のみ", "OKのみ", "手動編集のみ"],
        )

        # Export buttons
        with col_f4:
            st.write("📥 ダウンロード")
            col_d1, col_d2 = st.columns(2)
            xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"
            csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"

            if xlsx_path.exists():
                with open(xlsx_path, "rb") as f:
                    col_d1.download_button(
                        "📊 Excel",
                        f.read(),
                        file_name=f"{selected_company_id}_benchmarks.xlsx",
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
                if q in r.fund_name.lower() or q in r.fund_code.lower() or q in (r.benchmark or "").lower()
            ]
        if prov_filter != "全て":
            filtered_records = [r for r in filtered_records if r.index_provider == prov_filter]
        if review_filter == "要確認のみ":
            filtered_records = [r for r in filtered_records if r.needs_review]
        elif review_filter == "OKのみ":
            filtered_records = [r for r in filtered_records if not r.needs_review]
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
                "ファンド種別": r.fund_type.value if hasattr(r.fund_type, "value") else str(r.fund_type),
                "ベンチマーク指数": r.benchmark or "",
                "指数提供者": r.index_provider or "なし",
                "MSCI": "🟢 MSCI" if r.is_msci else "⚪ 他社",
                "信頼度": r.confidence.value if hasattr(r.confidence, "value") else str(r.confidence),
                "要確認": r.needs_review,
                "レビューメモ": r.review_comment or "",
                "手動": "✏️" if r.manual_override else "",
            })

        table_df = pd.DataFrame(edit_rows)

        st.caption(f"該当件数: {len(table_df)} 件 (テーブル内をダブルクリックでベンチマーク指数や提供者を直接編集できます)")
        edited_df = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            height=500,
            disabled=["順位", "ファンド名", "コード", "AUM (億円)", "MSCI", "信頼度", "手動"],
        )

        # Save changes button
        if st.button("💾 編集内容を一括保存", type="primary"):
            updated_count = 0
            for _, row in edited_df.iterrows():
                code = row["コード"]
                bm = row["ベンチマーク指数"]
                prov = row["指数提供者"]
                ft = row["ファンド種別"]
                needs_rev = bool(row["要確認"])
                comm = str(row["レビューメモ"])

                orig = next((r for r in records if r.fund_code == code), None)
                if orig and (orig.benchmark != bm or orig.index_provider != prov or orig.needs_review != needs_rev or orig.review_comment != comm):
                    update_manual_override(
                        fund_code=code,
                        benchmark=bm,
                        index_provider=prov,
                        fund_type=ft,
                        needs_review=needs_rev,
                        comment=comm,
                        reviewer="Streamlit Analyst",
                    )
                    updated_count += 1

            if updated_count > 0:
                st.success(f"✅ {updated_count} 件の変更を保存しました!")
                st.session_state[f"records_{selected_company_id}"] = load_records_for_company(selected_company_id)
                st.rerun()
            else:
                st.info("変更はありませんでした。")

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: PROSPECTUS INSPECTOR & SINGLE RE-EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("🔍 目論見書インスペクター & 単体再抽出")
        fund_options = {r.fund_code: f"#{r.rank} - {r.fund_name} ({format_aum_oku(r.aum)})" for r in records}
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
                st.write(f"**運用会社**: `{selected_company_name}`")
                st.write(f"**ファンドコード**: `{selected_record.fund_code}` | **純資産**: {format_aum_oku(selected_record.aum)}")
                st.write(f"**現在のベンチマーク**: `{selected_record.benchmark or 'なし'}`")
                st.write(f"**指数提供会社**: `{selected_record.index_provider}` | **MSCI採用**: {'🟢 はい' if selected_record.is_msci else 'いいえ'}")
                st.write(f"**抽出方法**: `{selected_record.extraction_method}` | **信頼度**: `{selected_record.confidence}`")
                st.write(f"**要確認**: {'⚠️ 要確認' if selected_record.needs_review else '✅ 確認済み'}")

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
    main()
