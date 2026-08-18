"""Streamlit web app for Multi-Asset Management Benchmark Scraper & Intelligence.

OpenBB Terminal Pro Theme & Architecture:
- Aesthetic: OpenBB Terminal Dark Grid & Ambient Glow (`#0b0d13`, `#00F5D4` Teal, `#8B5CF6` Indigo, `#FFB703` Amber)
- Multi-Asset Managers: 野村アセット, 大和アセット, 三菱UFJアセット (1社 / 2社 / 3社同時統合分析)
- 期間切り替え機能: 直近1ヶ月 (1M) ｜ 直近3ヶ月 (3M) ｜ 年初来 (YTD) ｜ 過去1年間 (1Y)
- ファンド別 日次買い付け推移 & 累積フロー推移インタラクティブ可視化 (OpenBB Terminal Style)
- Distributor-by-Distributor Fund Rankings (添付雑誌DCトレンドフォーマット完全再現)
- 買い付け金額（推定純流入） & 運用効果の精密計算
- Broker & Distributor Intelligence (主要販売会社 & 販社別売れ行きマトリクス)
- Theme & Gap Analysis for Consultative Product Proposals
- Interactive Data Editor & 5-Sheet Styled Excel Generation
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
    page_title="AM Flow Analysis ｜ MSCI Fund & Benchmark Intelligence",
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
    from app.flow_calculator import (
        estimate_fund_flow_from_returns,
        generate_daily_flow_timeseries,
    )
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


# ── OpenBB Terminal Signature CSS ──────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Noto+Sans+JP:wght@400;500;600;700&display=swap');

    /* Global Root Variables */
    :root {
        --bb-bg-base: #0a0d14;
        --bb-bg-card: #10141e;
        --bb-bg-card-hover: #151a27;
        --bb-border: #1e2638;
        --bb-border-active: #00F5D4;
        --bb-teal: #00F5D4;
        --bb-teal-glow: rgba(0, 245, 212, 0.15);
        --bb-indigo: #818cf8;
        --bb-amber: #FBBF24;
        --bb-crimson: #F43F5E;
        --bb-emerald: #10B981;
        --bb-text-main: #f1f5f9;
        --bb-text-muted: #94a3b8;
        --bb-text-sub: #64748b;
    }

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', 'Noto Sans JP', sans-serif;
    }

    /* OpenBB Space Ambient Glow Background */
    .stApp {
        background-color: var(--bb-bg-base);
        background-image: 
            radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.08) 0%, transparent 45%),
            radial-gradient(circle at 85% 20%, rgba(0, 245, 212, 0.06) 0%, transparent 40%),
            radial-gradient(circle at 50% 80%, rgba(139, 92, 246, 0.05) 0%, transparent 50%);
        background-attachment: fixed;
        color: var(--bb-text-main);
    }

    /* OpenBB Top Terminal Header */
    .openbb-header {
        background: linear-gradient(180deg, rgba(16, 20, 30, 0.85) 0%, rgba(10, 13, 20, 0.95) 100%);
        border: 1px solid var(--bb-border);
        border-radius: 12px;
        padding: 1.2rem 1.8rem;
        margin-bottom: 1.4rem;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(20px);
        display: flex;
        justify-content: space-between;
        align-items: center;
        position: relative;
        overflow: hidden;
    }
    .openbb-header::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, #00F5D4, #818cf8, #FBBF24, transparent);
    }
    .openbb-logo-brand {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .openbb-icon-glyph {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.6rem;
        font-weight: 800;
        color: #00F5D4;
        background: rgba(0, 245, 212, 0.1);
        border: 1px solid rgba(0, 245, 212, 0.3);
        padding: 4px 10px;
        border-radius: 8px;
        letter-spacing: -0.05em;
    }
    .openbb-title-h1 {
        font-size: 1.7rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #ffffff;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .openbb-title-tag {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.70rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 4px;
        background: rgba(0, 245, 212, 0.12);
        color: #00F5D4;
        border: 1px solid rgba(0, 245, 212, 0.3);
    }
    .openbb-header-meta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        color: var(--bb-text-muted);
        text-align: right;
        line-height: 1.6;
    }

    /* OpenBB Terminal CLI Command Line Bar */
    .cli-bar {
        background: #0d111a;
        border: 1px solid var(--bb-border);
        border-radius: 8px;
        padding: 8px 16px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        color: var(--bb-teal);
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 1.2rem;
    }
    .cli-prompt {
        color: var(--bb-text-sub);
    }

    /* OpenBB Terminal KPI Widgets Grid */
    .bb-kpi-grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 0.85rem;
        margin-bottom: 1.4rem;
    }
    .bb-kpi-widget {
        background: var(--bb-bg-card);
        border: 1px solid var(--bb-border);
        border-radius: 10px;
        padding: 1.1rem 0.9rem;
        text-align: left;
        position: relative;
        overflow: hidden;
        transition: all 0.2s ease;
    }
    .bb-kpi-widget:hover {
        background: var(--bb-bg-card-hover);
        border-color: rgba(0, 245, 212, 0.4);
        transform: translateY(-2px);
    }
    .bb-kpi-widget-topline {
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
    }
    .topline-teal { background: #00F5D4; }
    .topline-emerald { background: #10B981; }
    .topline-indigo { background: #818cf8; }
    .topline-amber { background: #FBBF24; }
    .topline-slate { background: #64748b; }

    .bb-kpi-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }
    .bb-kpi-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.70rem;
        font-weight: 700;
        color: var(--bb-text-muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .bb-kpi-tag {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        padding: 1px 6px;
        border-radius: 3px;
        background: rgba(255, 255, 255, 0.05);
        color: var(--bb-text-sub);
    }
    .bb-kpi-num {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem;
        font-weight: 800;
        color: #ffffff;
        margin: 2px 0 4px 0;
        letter-spacing: -0.03em;
    }
    .bb-kpi-footer {
        font-size: 0.75rem;
        color: var(--bb-text-sub);
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 4px;
    }

    /* OpenBB Section Banner */
    .bb-section-banner {
        background: linear-gradient(90deg, #131824 0%, #0d111a 100%);
        border: 1px solid var(--bb-border);
        border-left: 3px solid var(--bb-teal);
        border-radius: 6px;
        padding: 8px 14px;
        margin: 1.4rem 0 0.8rem 0;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.90rem;
        font-weight: 700;
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    /* OpenBB Proposal Pitch Box */
    .bb-pitch-box {
        background: var(--bb-bg-card);
        border: 1px solid var(--bb-border);
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        transition: border-color 0.2s ease;
    }
    .bb-pitch-box:hover {
        border-color: rgba(0, 245, 212, 0.3);
    }
    .bb-badge-gap {
        font-family: 'JetBrains Mono', monospace;
        background: rgba(244, 63, 94, 0.15);
        color: #fb7185;
        border: 1px solid rgba(244, 63, 94, 0.3);
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .bb-badge-ok {
        font-family: 'JetBrains Mono', monospace;
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }

    /* OpenBB Terminal Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0b0e17;
        border-right: 1px solid var(--bb-border);
    }

    /* OpenBB Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid var(--bb-border);
        padding-bottom: 2px;
        margin-bottom: 1.2rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'JetBrains Mono', monospace;
        background-color: transparent;
        border-radius: 6px 6px 0 0;
        color: var(--bb-text-muted);
        font-weight: 600;
        font-size: 0.88rem;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        color: var(--bb-teal) !important;
        background-color: rgba(0, 245, 212, 0.08) !important;
        border-bottom: 2px solid var(--bb-teal) !important;
    }

    /* Tables & Editor */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--bb-border);
        border-radius: 8px;
        background-color: var(--bb-bg-card);
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
        log_func(f"🚀 [INIT] {company_name} パイプライン起動 (AUM上位 {max_funds}本)")

    # Smart Cache Sync (Instantaneous loading if pre-extracted data exists)
    comp_json = DATA_DIR / f"{company_id}_benchmarks.json"
    if not force and comp_json.exists():
        raw = load_json(comp_json, [])
        if len(raw) >= min(max_funds, 20):
            recs = [BenchmarkRecord.model_validate(item) for item in raw[:max_funds]]
            for r in recs:
                r.management_company = company_name
                if not r.theme_category:
                    r.theme_category = classify_fund_theme(r.fund_name, r.benchmark)
                if not r.top_distributors:
                    dist_s, prim_s, act_s = resolve_fund_distributors(r.fund_name, company_name, r.is_etf)
                    r.top_distributors = dist_s
                    r.primary_broker = prim_s
                    r.sales_pitch_action = act_s
            if log_func:
                log_func(f"⚡ [CACHE_HIT] {company_name}: {len(recs)} 本のマスターデータを即時同期")
            return recs

    # Live Safe Pipeline Execution
    safe_workers = min(workers, 4)

    # Stage 1
    if company_id == "daiwa":
        funds = run_stage1_daiwa(force=force, max_funds=max_funds)
    elif company_id == "muam":
        funds = run_stage1_muam(force=force, max_funds=max_funds)
    else:
        funds = run_stage1(force=force, max_funds=max_funds)
    if log_func:
        log_func(f"Stage 1 OK: {len(funds)} 本のファンドリスト取得")

    # Stage 2
    if company_id not in ("daiwa", "muam"):
        run_stage2(force=force, max_workers=safe_workers)
    if log_func:
        log_func("Stage 2 OK: 交付目論見書URL解決")

    # Stage 3
    run_stage3(force=force, max_workers=safe_workers)
    if log_func:
        log_func("Stage 3 OK: 目論見書PDFダウンロード")

    # Stage 4
    run_stage4(force=force, allow_ocr=False, max_workers=safe_workers)
    if log_func:
        log_func("Stage 4 OK: テキスト抽出完了")

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

    save_json(comp_json, [r.model_dump(mode="json") for r in records])
    if log_func:
        log_func(f"✅ [SUCCESS] {company_name} 完了: {len(records)} 本抽出完了")

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

    combined_records.sort(key=lambda x: x.aum, reverse=True)
    for idx, r in enumerate(combined_records, start=1):
        r.rank = idx

    return combined_records


# ── Main Application ───────────────────────────────────────────────────────
def main() -> None:
    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="openbb-header">
        <div class="openbb-logo-brand">
            <div class="openbb-icon-glyph">⚡</div>
            <div>
                <h1 class="openbb-title-h1">
                    AM FLOW ANALYSIS
                    <span class="openbb-title-tag">MSCI INTELLIGENCE // PRO</span>
                </h1>
                <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 4px;">
                    3大アセットマネジメント（野村・大和・三菱UFJ）ベンチマーク抽出 & 販社営業マッチメーカー
                </div>
            </div>
        </div>
        <div class="openbb-header-meta">
            CORE: <span style="color: #00F5D4;">v3.4-PRO</span> ｜ ROUTE: <span style="color: #818cf8;">/am-flow/intelligence</span><br/>
            STATUS: <span style="color: #10B981; font-weight: 700;">● ONLINE ACTIVE</span> ｜ TOKYO DESK
        </div>
    </div>
    """, unsafe_allow_html=True)


    # ── Sidebar Configurations ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⬡ ASSET MANAGERS")
        company_options = {
            "nomura": "野村アセットマネジメント",
            "daiwa": "大和アセットマネジメント",
            "muam": "三菱UFJアセットマネジメント",
        }
        selected_company_ids = st.multiselect(
            "対象運用会社（1〜3社 一括選択）",
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
        st.markdown("### ⏱️ TIME HORIZON")
        period_choices = {
            "1M": {"label": "直近1ヶ月 (1M)", "multiplier": 1.0, "days": 30},
            "3M": {"label": "直近3ヶ月 (3M)", "multiplier": 3.0, "days": 90},
            "YTD": {"label": "年初来 (YTD)", "multiplier": 4.5, "days": 135},
            "1Y": {"label": "過去1年間 (1Y)", "multiplier": 12.0, "days": 365},
        }
        selected_period_key = st.radio(
            "集計期間の選択",
            options=list(period_choices.keys()),
            format_func=lambda k: period_choices[k]["label"],
            index=0,
            help="買い付け金額および運用効果の算出期間を切り替えます",
        )
        period_multiplier = period_choices[selected_period_key]["multiplier"]
        period_days = period_choices[selected_period_key]["days"]
        period_label = period_choices[selected_period_key]["label"]

        st.divider()
        st.markdown("### ⚙️ TERMINAL ENGINE")

        available_providers = get_available_providers()
        prov_options = {"auto": "AUTO (Claude / Gemini / GPT)"}
        for p in available_providers:
            prov_options[p["id"]] = f"{p['name']} ({p['model']})"

        selected_provider_key = st.selectbox(
            "🤖 LLM EXTRACTOR",
            options=list(prov_options.keys()),
            format_func=lambda x: prov_options[x],
            help="ベンチマーク抽出に使用するAIモデルを選択",
        )
        provider_arg = None if selected_provider_key == "auto" else selected_provider_key

        max_funds_per_company = st.slider(
            "Top N Funds per Manager",
            min_value=5,
            max_value=200,
            value=50,
            step=5,
        )

        workers = st.slider(
            "Concurrent Workers",
            min_value=1,
            max_value=10,
            value=5,
            help="ネットワーク並行処理ワーカ数",
        )

        use_llm = st.toggle("LLM Inference Engine", value=True)
        force = st.toggle("Force Re-Scrape (Bypass Cache)", value=False)

        st.divider()
        button_label = f"🚀 RUN PIPELINE ({len(selected_company_ids)} MANAGERS)"
        run_clicked = st.button(button_label, type="primary", use_container_width=True)

        st.divider()
        st.markdown("### 🔑 API GATEWAY STATUS")
        col_k1, col_k2 = st.columns(2)
        col_k1.caption(f"Claude: {'🟢 READY' if ANTHROPIC_API_KEY else '⚪ OFF'}")
        col_k2.caption(f"Gemini: {'🟢 READY' if GEMINI_API_KEY else '⚪ OFF'}")
        col_k1.caption(f"OpenAI: {'🟢 READY' if OPENAI_API_KEY else '⚪ OFF'}")

    # ── Run pipeline trigger ───────────────────────────────────────────────
    if run_clicked:
        prog_bar = st.progress(0, text="Initializing OpenBB Pipeline...")
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
            status_text.info(f"[{c_idx}/{len(selected_company_ids)}] Processing {c_name}...")
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
                st.error(f"❌ {c_name} Pipeline Error: {e}")

        if all_executed_records:
            run_stage6(all_executed_records)
            prog_bar.progress(1.0, text="✅ Pipeline Execution Complete!")
            status_text.success(f"✅ Executed {len(selected_company_ids)} Managers ({len(all_executed_records)} Total Funds Analyzed)")
            st.session_state["cached_records"] = all_executed_records

    # Load data for selected companies
    records = st.session_state.get("cached_records")
    if not records:
        records = load_records_for_companies(selected_company_ids)
        if records:
            st.session_state["cached_records"] = records

    if not records:
        st.info("💡 サイドバーの「RUN PIPELINE」ボタンをクリックしてデータを取得してください。")
        return

    # ── CLI Command Bar ────────────────────────────────────────────────────
    active_managers_str = " ".join([f"--{cid}" for cid in selected_company_ids])
    st.markdown(f"""
    <div class="cli-bar">
        <span class="cli-prompt">> /am-flow/funds/intelligence</span>
        <span style="color: #00F5D4;">--period={selected_period_key}</span>
        <span style="color: #818cf8;">{active_managers_str}</span>
        <span style="color: #94a3b8;">--total-funds={len(records)}</span>
    </div>
    """, unsafe_allow_html=True)


    # ── Top Level Tabs ─────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        f"📈 MARKET OVERVIEW ({period_label})",
        "🏛️ DISTRIBUTOR RANKINGS",
        "📋 ALL FUNDS MATRIX",
        "💡 PROPOSAL MATCHMAKER",
        "🔍 DAILY FLOW & PROSPECTUS",
    ])

    # ── Calculate Metrics for Selected Period ─────────────────────────────
    total_aum = sum(r.aum for r in records)
    total_count = len(records)
    msci_records = [r for r in records if r.is_msci]
    msci_aum = sum(r.aum for r in msci_records)
    msci_count = len(msci_records)
    total_inflow = sum(r.estimated_net_inflow * period_multiplier for r in records)
    non_msci_inflow = sum(r.estimated_net_inflow * period_multiplier for r in records if not r.is_msci)

    msci_aum_share = (msci_aum / total_aum * 100) if total_aum else 0
    msci_count_share = (msci_count / total_count * 100) if total_count else 0

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 1: ANALYTICS & MARKET SHARE
    # ═══════════════════════════════════════════════════════════════════════
    with tab1:
        st.markdown(f"""
        <div class="bb-kpi-grid">
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-indigo"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">TOTAL UNIVERSE</span>
                    <span class="bb-kpi-tag">{len(selected_company_ids)} MANAGERS</span>
                </div>
                <div class="bb-kpi-num">{total_count}</div>
                <div class="bb-kpi-footer">AUM: {total_aum / 1e12:.2f} 兆円</div>
            </div>
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-teal"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">MSCI ADOPTED AUM</span>
                    <span class="bb-kpi-tag">{msci_count} FUNDS</span>
                </div>
                <div class="bb-kpi-num" style="color: #00F5D4;">{msci_aum / 1e12:.2f} <span style="font-size: 1.1rem;">兆円</span></div>
                <div class="bb-kpi-footer" style="color: #00F5D4;">SHARE: {msci_aum_share:.1f}%</div>
            </div>
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-emerald"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">TOTAL NET FLOW ({selected_period_key})</span>
                    <span class="bb-kpi-tag">BUY VOLUME</span>
                </div>
                <div class="bb-kpi-num" style="color: {'#34d399' if total_inflow >= 0 else '#f43f5e'};">{format_inflow_oku(total_inflow)}</div>
                <div class="bb-kpi-footer">{period_label} 累計</div>
            </div>
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-amber"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">NON-MSCI TARGET FLOW</span>
                    <span class="bb-kpi-tag">OPPORTUNITY</span>
                </div>
                <div class="bb-kpi-num" style="color: #FBBF24;">{format_inflow_oku(non_msci_inflow)}</div>
                <div class="bb-kpi-footer" style="color: #FBBF24;">リプレイス余地</div>
            </div>
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-slate"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">REVIEW QUEUE</span>
                    <span class="bb-kpi-tag">HUMAN-IN-LOOP</span>
                </div>
                <div class="bb-kpi-num" style="color: #cbd5e1;">{sum(1 for r in records if r.needs_review)}</div>
                <div class="bb-kpi-footer">要レビュー件数</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_a1, col_a2 = st.columns([1, 1])

        with col_a1:
            st.markdown(f"#### ⚡ TOP 10 NET FLOW LEADERS ({period_label})")
            sorted_by_flow = sorted(records, key=lambda x: x.estimated_net_inflow * period_multiplier, reverse=True)[:10]
            flow_df = pd.DataFrame([
                {
                    "ファンド名": f"[{r.management_company[:2]}] {r.fund_name[:18]}...",
                    "買い付け金額 (億円)": round((r.estimated_net_inflow * period_multiplier) / 1e8, 1),
                    "MSCI": "MSCI" if r.is_msci else "他社",
                }
                for r in sorted_by_flow
            ])
            st.bar_chart(
                flow_df.set_index("ファンド名")["買い付け金額 (億円)"],
                color="#00F5D4",
                x_label="ファンド",
                y_label=f"買い付け金額 (億円) - {period_label}",
            )

        with col_a2:
            st.markdown(f"#### 🏷️ THEME BREAKDOWN & INFLOW VELOCITY ({period_label})")
            theme_agg: dict[str, dict] = {}
            for r in records:
                t = r.theme_category or "全世界・先進国株式"
                if t not in theme_agg:
                    theme_agg[t] = {"theme": t, "aum_oku": 0.0, "inflow_oku": 0.0, "count": 0}
                theme_agg[t]["aum_oku"] += r.aum / 1e8
                theme_agg[t]["inflow_oku"] += (r.estimated_net_inflow * period_multiplier) / 1e8
                theme_agg[t]["count"] += 1

            theme_df = pd.DataFrame(list(theme_agg.values()))
            theme_df.sort_values(by="inflow_oku", ascending=False, inplace=True)
            st.dataframe(
                theme_df.rename(columns={
                    "theme": "テーマ分類",
                    "count": "本数",
                    "aum_oku": "AUM合計(億円)",
                    "inflow_oku": f"買い付け金額合計(億円 / {selected_period_key})",
                }),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()
        st.markdown(f"#### 🎯 PRIME SALES TARGETS (Non-MSCI with High Inflow ｜ {period_label})")
        non_msci = [r for r in records if not r.is_msci and r.aum > 0]
        non_msci.sort(key=lambda x: (x.estimated_net_inflow * period_multiplier, x.aum), reverse=True)

        targets_data = []
        for t in non_msci[:12]:
            targets_data.append({
                "順位": t.rank,
                "運用会社": t.management_company,
                "ファンド名": t.fund_name,
                "AUM (億円)": round(t.aum / 1e8, 0),
                f"買い付け金額 ({selected_period_key})": format_inflow_oku(t.estimated_net_inflow * period_multiplier),
                "テーマ": t.theme_category,
                "現ベンチマーク": t.benchmark or "—",
                "主要販売会社 (Broker)": t.top_distributors or t.primary_broker or "主要証券",
                "営業アクション (Target Playbook)": t.sales_pitch_action or "🎯 アプローチ対象",
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
        st.markdown("### 🏛️ 販売会社別 取扱商品ランキング（添付雑誌DCトレンドフォーマット準拠）")
        st.caption(f"各販売会社が主力として販売しているファンドと残高・買い付け金額一覧（集計期間: {period_label}）")

        col_b1, col_b2 = st.columns([1, 2])
        dist_filter = col_b1.selectbox(
            "FILTER DISTRIBUTOR",
            options=["全販売会社を表示"] + MAJOR_DISTRIBUTORS,
        )

        dist_groups = get_funds_grouped_by_distributor(records)
        target_distributors = MAJOR_DISTRIBUTORS if dist_filter == "全販売会社を表示" else [dist_filter]

        for dist_name in target_distributors:
            funds_in_dist = dist_groups.get(dist_name, [])
            if not funds_in_dist:
                continue

            st.markdown(f"""
            <div class="bb-section-banner">
                <span>🏛️ {dist_name} 取扱上位ファンド一覧（残高順）</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #94a3b8;">TOP {len(funds_in_dist)} FUNDS ｜ HORIZON: {period_label}</span>
            </div>
            """, unsafe_allow_html=True)

            d_df = pd.DataFrame([
                {
                    "順位": f["rank"],
                    "運用商品名 (ファンド名)": f["fund_name"],
                    "運用会社": f["management_company"],
                    "残高 (億円)": f["aum_oku"],
                    f"買い付け金額 ({selected_period_key})": format_inflow_oku(f["inflow_oku"] * period_multiplier * 1e8),
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
        search_query = col_f1.text_input("🔍 QUERY FILTER", placeholder="ファンド名・コード・ベンチマーク・販社...")
        theme_filter = col_f2.selectbox("THEME", options=["全て"] + THEMES)
        review_filter = col_f3.selectbox(
            "FILTER STATUS",
            options=["全て", "買い付け金額プラスのみ", "非MSCIのみ", "要確認のみ", "手動編集のみ"],
        )

        with col_f4:
            st.write("📥 EXPORT TERMINAL REPORT (5-SHEET)")
            col_d1, col_d2 = st.columns(2)
            xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"
            csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"

            if xlsx_path.exists():
                with open(xlsx_path, "rb") as f:
                    col_d1.download_button(
                        "📊 Excel (.xlsx)",
                        f.read(),
                        file_name="am_flow_analysis_intelligence.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            if csv_path.exists():
                with open(csv_path, "rb") as f:
                    col_d2.download_button(
                        "📄 CSV (.csv)",
                        f.read(),
                        file_name="am_flow_analysis_benchmarks.csv",
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
        if review_filter == "買い付け金額プラスのみ":
            filtered_records = [r for r in filtered_records if r.estimated_net_inflow > 0]
        elif review_filter == "非MSCIのみ":
            filtered_records = [r for r in filtered_records if not r.is_msci]
        elif review_filter == "要確認のみ":
            filtered_records = [r for r in filtered_records if r.needs_review]
        elif review_filter == "手動編集のみ":
            filtered_records = [r for r in filtered_records if r.manual_override]

        edit_rows = []
        for r in filtered_records:
            edit_rows.append({
                "順位": r.rank,
                "運用会社": r.management_company,
                "ファンド名": r.fund_name,
                "コード": r.fund_code,
                "AUM (億円)": round(r.aum / 1e8, 0) if r.aum else 0,
                f"買い付け金額 ({selected_period_key})": format_inflow_oku(r.estimated_net_inflow * period_multiplier),
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

        st.caption(f"MATCHED: {len(table_df)} FUNDS (ダブルクリックで直接編集可能)")
        edited_df = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            height=500,
            disabled=["順位", "運用会社", "ファンド名", "コード", "AUM (億円)", f"買い付け金額 ({selected_period_key})", "MSCI", "手動"],
        )

        if st.button("💾 SAVE CHANGES & RE-GENERATE REPORTS", type="primary"):
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
                    orig.benchmark = bm
                    orig.index_provider = prov
                    orig.theme_category = theme
                    orig.top_distributors = dist
                    orig.sales_pitch_action = action
                    orig.needs_review = needs_rev
                    orig.review_comment = comm
                    orig.manual_override = True
                    orig.is_msci = "MSCI" in (bm or "").upper() or "MSCI" in (prov or "").upper()

                    ft = orig.fund_type.value if hasattr(orig.fund_type, "value") else str(orig.fund_type or "インデックス型")
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
                run_stage6(records)
                st.success(f"✅ {updated_count} 件の変更を保存し、Excelレポートを更新しました!")
                st.session_state["cached_records"] = records
                st.rerun()
            else:
                st.info("変更はありませんでした。")

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: PRODUCT PROPOSALS & BROKER MATCHMAKER
    # ═══════════════════════════════════════════════════════════════════════
    with tab4:
        st.markdown("### 💡 運用会社向け 商品企画提案 & 販社マッチング")
        st.caption("運用会社の商品企画部へ「**今どのテーマに買い付け資金が集まっており、どの販売会社と組めば最も売れるか**」を提案するためのコンサルティングインテリジェンスです。")

        company_for_pitch = st.selectbox(
            "TARGET ASSET MANAGER",
            options=selected_company_labels,
        )

        firm_records = [r for r in records if r.management_company == company_for_pitch] or records
        proposals = generate_product_proposals(firm_records, company_for_pitch)

        col_p1, col_p2 = st.columns([1, 1])

        with col_p1:
            st.markdown(f"#### 🧩 {company_for_pitch} LINEUP GAP ANALYSIS")
            for prop in proposals:
                is_gap = "ギャップ" in prop["status"]
                badge_class = "bb-badge-gap" if is_gap else "bb-badge-ok"
                st.markdown(f"""
                <div class="bb-pitch-box">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 1.15rem; font-weight: 700; color: #ffffff;">{prop['theme']}</span>
                        <span class="{badge_class}">{prop['status']}</span>
                    </div>
                    <div style="font-size: 0.84rem; color: #94a3b8; margin-bottom: 8px; font-family: 'JetBrains Mono', monospace;">
                        自社現保有: <b style="color: #f1f5f9;">{prop['existing_funds_count']} 本</b> ｜ AUM: <b style="color: #f1f5f9;">{prop['theme_aum_display']}</b> ｜ 買い付け金額: <b style="color: #00F5D4;">{prop['theme_inflow_display']}</b>
                    </div>
                    <div style="background: #0d111a; border: 1px solid var(--bb-border); padding: 10px 14px; border-radius: 6px; font-size: 0.85rem; margin-top: 8px;">
                        <div style="margin-bottom: 4px;"><b style="color: #00F5D4;">推奨MSCI指数:</b> <span style="color: #e2e8f0; font-family: 'JetBrains Mono', monospace;">{prop['recommended_msci_index']}</span></div>
                        <div style="margin-bottom: 6px;"><b style="color: #FBBF24;">最適主幹販社:</b> <span style="color: #fde68a;">{prop['best_selling_brokers']}</span></div>
                        <div style="color: #cbd5e1; font-size: 0.82rem; line-height: 1.5;">{prop['proposal_narrative']}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with col_p2:
            st.markdown("#### 🏢 販社 × テーマ別 売れ行きマトリクス")
            st.caption("どの販売会社経由だと、どのテーマが最も売れているかを可視化")

            matrix_rows = build_broker_theme_sales_matrix(records)
            matrix_df = pd.DataFrame([
                {
                    "販売会社 (Broker)": m["broker"],
                    "得意テーマ": m["theme"],
                    "取扱本数": m["fund_count"],
                    "AUM合計 (億円)": round(m["total_aum"] / 1e8, 1),
                    f"買い付け金額 ({selected_period_key})": format_inflow_oku(m["total_inflow"] * period_multiplier),
                }
                for m in matrix_rows[:12]
            ])
            st.dataframe(
                matrix_df,
                use_container_width=True,
                hide_index=True,
            )

            st.markdown(f"""
            <div style="background: rgba(0, 245, 212, 0.06); border-left: 3px solid #00F5D4; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-top: 1rem; font-size: 0.86rem; color: #bae6fd;">
                <b style="color: #00F5D4;">💡 提案トークの活用例（対 {company_for_pitch}）:</b><br/>
                <i>「御社のラインアップにはAI・半導体分野が不足しています。市場ではこのテーマに期間中大きな買い付けが発生しており、特に<b>SBI証券・楽天証券</b>での売れ行きが突出しています。ぜひ<b>MSCI AI & Robotics指数</b>を採用し、ネット証券を主幹販社とした新商品を企画しませんか？」</i>
            </div>
            """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 5: DAILY FLOW INSPECTOR & PROSPECTUS
    # ═══════════════════════════════════════════════════════════════════════
    with tab5:
        st.markdown("### 🔍 ファンド別・日次買い付け推移 & 目論見書インスペクター")
        st.caption(f"1営業日ごとの資金流入（日次買い付け金額）および累積フローの推移グラフ（集計期間: {period_label}）")

        fund_options = {r.fund_code: f"#{r.rank} [{r.management_company[:2]}] {r.fund_name} ({format_aum_oku(r.aum)} / 買付 {format_inflow_oku(r.estimated_net_inflow * period_multiplier)})" for r in records}
        selected_code = st.selectbox(
            "SELECT FUND FOR DRILLDOWN",
            options=list(fund_options.keys()),
            format_func=lambda x: fund_options[x],
        )

        selected_record = next((r for r in records if r.fund_code == selected_code), None)

        if selected_record:
            col_i1, col_i2 = st.columns([1, 1])

            with col_i1:
                st.markdown(f"### {selected_record.fund_name}")
                st.write(f"**運用会社**: `{selected_record.management_company}` ｜ **テーマ**: `{selected_record.theme_category}`")
                st.write(f"**純資産(AUM)**: {format_aum_oku(selected_record.aum)} ｜ **期間買い付け金額 ({selected_period_key})**: `{format_inflow_oku(selected_record.estimated_net_inflow * period_multiplier)}`")
                st.write(f"**現在のベンチマーク**: `{selected_record.benchmark or 'なし'}` ({selected_record.index_provider})")
                st.write(f"**MSCI採用**: {'🟢 はい' if selected_record.is_msci else 'いいえ'}")
                st.write(f"**主要販売会社**: `{selected_record.top_distributors or '主要証券'}`")
                st.write(f"**営業アクション**: `{selected_record.sales_pitch_action or '—'}`")

                if selected_record.prospectus_pdf_url:
                    st.link_button("📄 交付目論見書PDFを開く", selected_record.prospectus_pdf_url)

                st.divider()
                st.write("🛠️ **SINGLE FUND AI ACTIONS**")
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("🔄 AI RE-EXTRACT", key=f"reextract_{selected_code}"):
                    with st.spinner("Executing LLM Inference..."):
                        new_rec = reextract_single_fund(
                            fund_code=selected_code,
                            use_llm=True,
                            provider=provider_arg,
                        )
                        if new_rec:
                            st.success(f"Extracted: {new_rec.benchmark} ({new_rec.index_provider})")
                            st.session_state["cached_records"] = load_records_for_companies(selected_company_ids)
                            st.rerun()

                if col_btn2.button("🔍 OCR RE-EXTRACT", key=f"ocr_{selected_code}"):
                    with st.spinner("Executing Optical OCR..."):
                        new_rec = reextract_single_fund(
                            fund_code=selected_code,
                            use_llm=True,
                            provider=provider_arg,
                            force_ocr=True,
                        )
                        if new_rec:
                            st.success(f"OCR Extracted: {new_rec.benchmark} ({new_rec.index_provider})")
                            st.session_state["cached_records"] = load_records_for_companies(selected_company_ids)
                            st.rerun()

            with col_i2:
                st.markdown("#### 📄 抽出テキスト (目論見書)")
                text_path = TEXT_DIR / f"{selected_code}.txt"
                if text_path.exists():
                    raw_text = text_path.read_text(encoding="utf-8")
                    st.text_area("テキスト内容", raw_text[:10000], height=240, disabled=True)
                else:
                    st.info("テキストファイルが存在しません。")

            st.divider()
            st.markdown(f"#### 📈 {selected_record.fund_name} の日次買い付け金額 & 累積推移 ({period_label})")

            daily_data = generate_daily_flow_timeseries(
                fund_name=selected_record.fund_name,
                aum=selected_record.aum,
                monthly_inflow=selected_record.estimated_net_inflow,
                nav=selected_record.nav or 20000.0,
                days=period_days,
            )
            daily_df = pd.DataFrame(daily_data)

            col_g1, col_g2 = st.columns([1, 1])

            with col_g1:
                st.markdown("##### 📊 DAILY NET INFLOW VELOCITY (日次フロー)")
                st.bar_chart(
                    daily_df.set_index("date")["daily_inflow_oku"],
                    color="#00F5D4",
                    x_label="日付",
                    y_label="日次買い付け金額 (億円)",
                )

            with col_g2:
                st.markdown("##### 📈 CUMULATIVE FLOW & NAV TRAJECTORY")
                st.line_chart(
                    daily_df.set_index("date")[["cumulative_inflow_oku", "aum_oku"]],
                    color=["#00F5D4", "#818cf8"],
                    x_label="日付",
                    y_label="金額 (億円)",
                )

            st.markdown("##### 📋 DAILY TRANSACTION LEDGER")
            st.dataframe(
                daily_df.rename(columns={
                    "date": "日付",
                    "nav": "基準価額 (円)",
                    "aum_oku": "純資産残高 (億円)",
                    "daily_return_pct": "日次騰落率 (%)",
                    "daily_perf_oku": "日次運用効果 (億円)",
                    "daily_inflow_oku": "日次買い付け金額 (億円)",
                    "cumulative_inflow_oku": "累積買い付け金額 (億円)",
                }),
                use_container_width=True,
                hide_index=True,
                height=300,
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as _app_exc:
        st.error(f"⚠️ アプリケーション実行エラー: {_app_exc}")
        st.exception(_app_exc)
