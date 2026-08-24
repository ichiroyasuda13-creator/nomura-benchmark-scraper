"""Streamlit web app for Multi-Asset Management Benchmark Scraper & Intelligence.

OpenBB Terminal Pro Theme & Architecture:
- Aesthetic: OpenBB Terminal Dark Grid & Ambient Glow (`#0b0d13`, `#00F5D4` Teal, `#8B5CF6` Indigo, `#FFB703` Amber)
- Multi-Asset Managers: 野村アセット, 大和アセット, 三菱UFJアセット (1社 / 2社 / 3社同時統合分析)
- 期間切り替え機能: 直近1ヶ月 (1M) ｜ 直近3ヶ月 (3M) ｜ 年初来 (YTD) ｜ 過去1年間 (1Y)
- ファンド別 日次買い付け推移 & 累積フロー推移インタラクティブ可視化 (OpenBB Terminal Style)
- Distributor-by-Distributor Fund Rankings (主要販売会社別ランキング)
- 買い付け金額（推定純流入） & 運用効果の精密計算 & データ来歴 (DataProvenance) 表示
- Broker & Distributor Intelligence (主要販売会社 & 販社別売れ行きマトリクス)
- Theme & Gap Analysis for Consultative Product Proposals
- Interactive Data Editor & 7-Sheet Styled Excel Generation
"""

from __future__ import annotations

import io
import json
import os
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
    # Module aliases must be bound at import time. Binding them inside
    # main() made `cfg` function-local and raised UnboundLocalError
    # whenever no API key was entered.
    import app.config as cfg
    import app.llm as llm
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
        calculate_daily_net_flows,
        estimate_fund_flow_from_returns,
        generate_daily_flow_timeseries,
    )
    from app.http_client import load_json, save_json, setup_logging
    from app.llm import get_available_providers, llm_available
    from app.models import (
        BenchmarkRecord,
        Confidence,
        DataProvenance,
        Fund,
        FundType,
        format_aum_oku,
        format_inflow_oku,
    )
    from app.muam_stage1 import run_stage1_muam
    from app.proposal_generator import generate_product_proposals
    from app.stage5_benchmark import reextract_single_fund, update_manual_override
    from app.stage6_output import create_styled_excel, run_stage6
    from app.theme_classifier import THEMES, classify_fund_theme
    from app.timeseries_store import append_snapshot, load_series
except Exception as _import_err:
    st.error(f"❌ モジュールインポートエラー: {_import_err}")
    st.info("💡 仮想環境 `.venv` が有効化されているか、必要なパッケージがインストールされているか確認してください。")
    st.stop()


# ── OpenBB Terminal Signature CSS ──────────────────────────────────────────
TERMINAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
    --bg-main: #080a0f;
    --bg-card: #0f131c;
    --bg-card-hover: #161c28;
    --border-color: rgba(255, 255, 255, 0.08);
    --border-glow: rgba(0, 245, 212, 0.25);
    --accent-teal: #00F5D4;
    --accent-indigo: #818cf8;
    --accent-amber: #FFB703;
    --accent-rose: #f43f5e;
    --accent-emerald: #10B981;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
}

html, body, .stApp {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: var(--text-primary);
}

/* Specific text selectors to prevent overriding Streamlit Material Icon fonts */
.stMarkdown, .stText, label, p, h1, h2, h3, h4, h5, h6, .stSelectbox, .stSlider {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* Ensure Streamlit system icons (visibility toggle, expander arrows, etc.) render properly */
span[data-testid="stIconMaterial"],
[data-testid="stIcon"],
.material-icons,
.material-symbols-rounded,
.material-symbols-outlined,
button[aria-label="Show password"] span,
button[aria-label="Hide password"] span {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
}

code, kbd, samp, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

.main, .stApp {
    background-color: var(--bg-main);
    background-image: 
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 245, 212, 0.07), transparent 70%),
        radial-gradient(ellipse 60% 40% at 100% 100%, rgba(129, 140, 248, 0.05), transparent 70%);
}

.stTabs [data-baseweb="tab-list"] {
    background: rgba(15, 19, 28, 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 6px;
    gap: 8px;
}

.stTabs [data-baseweb="tab"] {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-secondary);
    border-radius: 8px;
    padding: 8px 16px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0, 245, 212, 0.15), rgba(129, 140, 248, 0.15)) !important;
    color: var(--accent-teal) !important;
    border: 1px solid var(--border-glow);
    box-shadow: 0 4px 12px rgba(0, 245, 212, 0.12);
}

/* KPI Widgets */
.bb-kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.bb-kpi-widget {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 16px 20px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, border-color 0.2s ease;
}

.bb-kpi-widget:hover {
    transform: translateY(-2px);
    border-color: var(--border-glow);
}

.bb-kpi-widget-topline {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
}

.topline-teal { background: var(--accent-teal); }
.topline-indigo { background: var(--accent-indigo); }
.topline-amber { background: var(--accent-amber); }
.topline-emerald { background: var(--accent-emerald); }
.topline-rose { background: var(--accent-rose); }

.bb-kpi-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.bb-kpi-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--text-muted);
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.bb-kpi-tag {
    font-size: 0.72rem;
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-secondary);
}

.bb-kpi-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.85rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.2;
    margin-bottom: 4px;
}

.bb-kpi-footer {
    font-size: 0.8rem;
    color: var(--text-secondary);
}

/* Provenance Badge */
.provenance-tag {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    margin-right: 6px;
}
.prov-actual { background: rgba(16, 185, 129, 0.2); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.4); }
.prov-derived { background: rgba(129, 140, 248, 0.2); color: #818cf8; border: 1px solid rgba(129, 140, 248, 0.4); }
.prov-estimated { background: rgba(255, 183, 3, 0.2); color: #FFB703; border: 1px solid rgba(255, 183, 3, 0.4); }
.prov-synthetic { background: rgba(244, 63, 94, 0.2); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.4); }
.prov-none { background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.4); }

/* Note banner */
.note-banner {
    background: rgba(244, 63, 94, 0.08);
    border: 1px solid rgba(244, 63, 94, 0.25);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.85rem;
    color: #fca5a5;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
}

/* CLI command bar */
.cli-bar {
    background: #030712;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 10px 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    color: var(--accent-teal);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
}
.cli-prompt { color: #64748b; }

.bb-section-banner {
    background: linear-gradient(90deg, rgba(30, 58, 138, 0.3), transparent);
    border-left: 3px solid #3b82f6;
    padding: 8px 14px;
    border-radius: 0 6px 6px 0;
    margin: 16px 0 12px 0;
    font-weight: 700;
    font-size: 0.95rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
</style>
"""

st.markdown(TERMINAL_CSS, unsafe_allow_html=True)


# ── Pipeline Runner ────────────────────────────────────────────────────────
def run_pipeline_for_company(
    company_id: str,
    max_funds: int,
    use_llm: bool,
    force: bool,
    provider: str | None = None,
    workers: int = 4,
    log_func=None,
    prog_func=None,
) -> list[BenchmarkRecord]:
    """Execute scraping pipeline for a specific company."""
    if company_id == "nomura":
        from app.stage1_list import run_stage1
        from app.stage2_pdf_url import run_stage2
        from app.stage3_download import run_stage3
        from app.stage4_extract_text import run_stage4
        from app.stage5_benchmark import run_stage5

        if log_func:
            log_func("Stage 1: Fetching Nomura fund list...")
        funds = run_stage1(max_funds=max_funds, force=force)

        if log_func:
            log_func(f"Stage 2: Resolving {len(funds)} prospectus URLs...")
        run_stage2(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 3: Downloading prospectus PDFs...")
        run_stage3(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 4: Extracting text from PDFs...")
        run_stage4(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 5: Analyzing benchmarks & distributors...")
        records = run_stage5(use_llm=use_llm, provider=provider, max_workers=workers)
        return records

    elif company_id == "daiwa":
        from app.stage3_download import run_stage3
        from app.stage4_extract_text import run_stage4
        from app.stage5_benchmark import run_stage5

        if log_func:
            log_func("Stage 1: Fetching Daiwa fund list from live API...")
        funds = run_stage1_daiwa(max_funds=max_funds, force=force)

        if log_func:
            log_func("Stage 3: Downloading Daiwa prospectus PDFs...")
        run_stage3(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 4: Extracting text from Daiwa PDFs...")
        run_stage4(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 5: Analyzing benchmarks for Daiwa...")
        records = run_stage5(use_llm=use_llm, provider=provider, max_workers=workers)
        return records

    elif company_id == "muam":
        from app.stage3_download import run_stage3
        from app.stage4_extract_text import run_stage4
        from app.stage5_benchmark import run_stage5

        if log_func:
            log_func("Stage 1: Fetching MUAM fund list from live API...")
        funds = run_stage1_muam(max_funds=max_funds, force=force)

        if log_func:
            log_func("Stage 3: Downloading MUAM prospectus PDFs...")
        run_stage3(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 4: Extracting text from MUAM PDFs...")
        run_stage4(force=force, max_workers=workers)

        if log_func:
            log_func("Stage 5: Analyzing benchmarks for MUAM...")
        records = run_stage5(use_llm=use_llm, provider=provider, max_workers=workers)
        return records

    return []


def load_records_for_companies(selected_ids: list[str]) -> list[BenchmarkRecord]:
    """Load cached benchmark records for selected management companies."""
    if not BENCHMARKS_JSON.exists():
        return []
    try:
        raw_list = load_json(BENCHMARKS_JSON, [])
        all_records = [BenchmarkRecord.model_validate(r) for r in raw_list]
    except Exception:
        return []

    name_map = {
        "nomura": "野村アセットマネジメント",
        "daiwa": "大和アセットマネジメント",
        "muam": "三菱UFJアセットマネジメント",
    }
    selected_names = [name_map[cid] for cid in selected_ids if cid in name_map]
    return [r for r in all_records if r.management_company in selected_names]


def get_provenance_badge(prov: DataProvenance | str) -> str:
    """Format DataProvenance as an HTML badge."""
    val = prov.value if hasattr(prov, "value") else str(prov)
    val_lower = val.lower()
    if val_lower == "actual":
        return '<span class="provenance-tag prov-actual">● 実測 (ACTUAL)</span>'
    elif val_lower == "derived":
        return '<span class="provenance-tag prov-derived">◆ 派生 (DERIVED)</span>'
    elif val_lower == "estimated":
        return '<span class="provenance-tag prov-estimated">▲ 推計 (ESTIMATED)</span>'
    elif val_lower == "synthetic":
        return '<span class="provenance-tag prov-synthetic">■ 合成 (SYNTHETIC)</span>'
    else:
        return '<span class="provenance-tag prov-none">○ 蓄積中 (NONE)</span>'


# ── Main Application ───────────────────────────────────────────────────────
def main() -> None:
    ensure_dirs()

    # ── Header ─────────────────────────────────────────────────────────────
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 4px;">
            <span style="font-size: 2rem;">⚡</span>
            <div>
                <h1 style="font-size: 1.75rem; font-weight: 800; margin: 0; letter-spacing: -0.02em; background: linear-gradient(135deg, #f8fafc 0%, #94a3b8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    AM FLOW ANALYSIS ｜ MSCI CLIENT INTELLIGENCE
                </h1>
                <p style="font-size: 0.84rem; color: #94a3b8; margin: 0;">
                    資産運用会社ベンチマーク・資金フロー解析 & 販社別マッチメーカー・商品企画提案プラットフォーム
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with header_col2:
        st.markdown("""
        <div style="text-align: right; padding-top: 8px;">
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; background: rgba(0, 245, 212, 0.1); color: #00F5D4; padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(0, 245, 212, 0.3);">
                ● LIVE SYSTEM v2.0
            </span>
        </div>
        """, unsafe_allow_html=True)

    # ── Sidebar Configurations ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🏢 ASSET MANAGERS (運用会社選択)")
        company_options = {
            "nomura": "野村アセットマネジメント",
            "daiwa": "大和アセットマネジメント",
            "muam": "三菱UFJアセットマネジメント",
        }
        selected_company_ids = []
        for cid, cname in company_options.items():
            if st.checkbox(cname, value=True, key=f"chk_{cid}"):
                selected_company_ids.append(cid)

        if not selected_company_ids:
            selected_company_ids = ["nomura"]

        st.divider()
        st.markdown("### ⏱️ HORIZON / 集計期間")
        period_choices = {
            "1M (直近1ヶ月)": {"days": 30, "label": "直近1ヶ月 (1M)"},
            "3M (直近3ヶ月)": {"days": 90, "label": "直近3ヶ月 (3M)"},
            "YTD (年初来)": {"days": 135, "label": "年初来 (YTD)"},
            "1Y (過去1年間)": {"days": 365, "label": "過去1年間 (1Y)"},
        }
        selected_period_key = st.selectbox("集計期間を選択", list(period_choices.keys()), index=0)
        period_info = period_choices[selected_period_key]
        period_label = period_info["label"]
        period_days = period_info["days"]

        st.divider()
        st.markdown("### 🔑 API KEY SETTINGS")
        with st.expander("🔑 APIキー設定 (Gemini / Claude / OpenAI)", expanded=not bool(os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))):
            input_gemini = st.text_input(
                "Google Gemini API Key",
                value=os.getenv("GEMINI_API_KEY", ""),
                type="password",
                placeholder="AIzaSy...",
                help="Google AI Studio (https://aistudio.google.com/) から取得した API キーを入力してください。",
            )
            if input_gemini:
                os.environ["GEMINI_API_KEY"] = input_gemini.strip()
                cfg.GEMINI_API_KEY = input_gemini.strip()
                llm.GEMINI_API_KEY = input_gemini.strip()

            input_claude = st.text_input(
                "Anthropic Claude API Key",
                value=os.getenv("ANTHROPIC_API_KEY", ""),
                type="password",
                placeholder="sk-ant-...",
                help="Anthropic Console から取得した API キー",
            )
            if input_claude:
                os.environ["ANTHROPIC_API_KEY"] = input_claude.strip()
                cfg.ANTHROPIC_API_KEY = input_claude.strip()
                llm.ANTHROPIC_API_KEY = input_claude.strip()

            input_openai = st.text_input(
                "OpenAI API Key",
                value=os.getenv("OPENAI_API_KEY", ""),
                type="password",
                placeholder="sk-...",
                help="OpenAI Platform から取得した API キー",
            )
            if input_openai:
                os.environ["OPENAI_API_KEY"] = input_openai.strip()
                cfg.OPENAI_API_KEY = input_openai.strip()
                llm.OPENAI_API_KEY = input_openai.strip()

        current_gemini = os.getenv("GEMINI_API_KEY") or getattr(cfg, "GEMINI_API_KEY", "")
        current_claude = os.getenv("ANTHROPIC_API_KEY") or getattr(cfg, "ANTHROPIC_API_KEY", "")
        current_openai = os.getenv("OPENAI_API_KEY") or getattr(cfg, "OPENAI_API_KEY", "")

        st.markdown("### ⚙️ SCRAPER & LLM ENGINE")

        available_providers = get_available_providers()
        provider_display_map = {
            p["id"]: f"{p['name']} ｜ {p['model']}" + (" 🟢 READY" if p.get("configured") else " ⚪ (未設定)")
            for p in available_providers
        }
        # Select Gemini or Claude as default if ready
        default_idx = 0
        for i, p in enumerate(available_providers):
            if p.get("configured"):
                default_idx = i
                break

        selected_provider_id = st.selectbox(
            "AI Model Provider",
            options=list(provider_display_map.keys()),
            format_func=lambda x: provider_display_map.get(x, x),
            index=default_idx if available_providers else 0,
        )
        max_funds_per_company = st.slider(
            "取得件数 / 社 (Max Funds)",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            help="Streamlit Cloud の無料サーバー負荷を抑えるため、通常は 15〜20 件程度が推奨です。",
        )
        workers = st.slider(
            "並列ワーカー数 (Workers)",
            min_value=1,
            max_value=4,
            value=2,
            help="Streamlit Cloud の CPU 制限を超えないよう 2 を推奨。ローカル実行時は増やせます。",
        )

        provider_arg = selected_provider_id
        use_llm = st.toggle("LLM Inference Engine", value=True)
        force = st.toggle("Force Re-Scrape (Bypass Cache)", value=False)

        st.markdown("### 📡 API GATEWAY STATUS")
        col_k1, col_k2 = st.columns(2)
        col_k1.caption(f"Gemini: {'🟢 READY' if current_gemini else '⚪ OFF'}")
        col_k2.caption(f"Claude: {'🟢 READY' if current_claude else '⚪ OFF'}")
        col_k1.caption(f"OpenAI: {'🟢 READY' if current_openai else '⚪ OFF'}")

        st.divider()
        button_label = f"🚀 RUN PIPELINE ({len(selected_company_ids)} MANAGERS)"
        run_clicked = st.button(button_label, type="primary", width="stretch")

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

    # Load data for selected companies dynamically
    records = load_records_for_companies(selected_company_ids)
    if not records and "cached_records" in st.session_state:
        name_map = {
            "nomura": "野村アセットマネジメント",
            "daiwa": "大和アセットマネジメント",
            "muam": "三菱UFJアセットマネジメント",
        }
        selected_names = [name_map[cid] for cid in selected_company_ids if cid in name_map]
        records = [r for r in st.session_state["cached_records"] if r.management_company in selected_names]

    if not records:
        st.info("💡 サイドバーの「🚀 RUN PIPELINE」ボタンをクリックしてデータを取得してください。")
        return

    # ── CLI Command Bar & Download ─────────────────────────────────────────
    active_managers_str = " ".join([f"--{cid}" for cid in selected_company_ids])
    cli_col1, cli_col2 = st.columns([3, 1])
    with cli_col1:
        st.markdown(f"""
        <div class="cli-bar">
            <span class="cli-prompt">> /am-flow/funds/intelligence</span>
            <span style="color: #00F5D4;">--period={selected_period_key}</span>
            <span style="color: #818cf8;">{active_managers_str}</span>
            <span style="color: #94a3b8;">--total-funds={len(records)}</span>
        </div>
        """, unsafe_allow_html=True)

    with cli_col2:
        # Generate styled Excel in memory for download
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        temp_excel_path = OUTPUT_DIR / f"temp_report_{int(time.time())}.xlsx"
        try:
            create_styled_excel(records, temp_excel_path)
            if temp_excel_path.exists():
                with open(temp_excel_path, "rb") as f:
                    excel_bytes = f.read()
                temp_excel_path.unlink(missing_ok=True)
                st.download_button(
                    label="📥 EXCEL レポート (7シート) 出力",
                    data=excel_bytes,
                    file_name=f"AM_Flow_Intelligence_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                )
        except Exception as e:
            st.caption(f"Excel準備中: {e}")

    # ── Phase 0 Note Banner ────────────────────────────────────────────────
    st.markdown("""
    <div class="note-banner">
        <span>⚠️</span>
        <span><b>注記:</b> 買い付け金額・販売会社情報は、時系列データ蓄積および目論見書テキスト解析に基づき順次実測化されます。日次時系列が蓄積途中のファンドは「データ蓄積中」と明示されます。</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Calculate Metrics for Selected Period ─────────────────────────────
    total_aum = sum(r.aum for r in records)
    total_count = len(records)
    msci_records = [r for r in records if r.is_msci]
    msci_aum = sum(r.aum for r in msci_records)
    msci_count = len(msci_records)

    # Compute period flow for all records from timeseries store
    record_flows: dict[str, float | None] = {}
    for r in records:
        s = load_series(r.fund_code, days=period_days)
        if len(s) >= 2:
            _, _, flow = calculate_daily_net_flows(s)
            record_flows[r.fund_code] = flow
        else:
            record_flows[r.fund_code] = None

    valid_flows = [f for f in record_flows.values() if f is not None]
    total_inflow = sum(valid_flows) if valid_flows else None
    non_msci_valid = [record_flows[r.fund_code] for r in records if not r.is_msci and record_flows[r.fund_code] is not None]
    non_msci_inflow = sum(non_msci_valid) if non_msci_valid else None
    msci_aum_share = (msci_aum / total_aum * 100) if total_aum else 0
    msci_count_share = (msci_count / total_count * 100) if total_count else 0
    needs_review_count = sum(1 for r in records if r.needs_review)

    # ── Top Level Tabs ─────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        f"📈 MARKET OVERVIEW ({period_label})",
        "🏛️ DISTRIBUTOR RANKINGS",
        "📋 ALL FUNDS MATRIX",
        "💡 PROPOSAL MATCHMAKER",
        "🔍 DAILY FLOW & PROSPECTUS",
        f"⚠️ NEEDS REVIEW ({needs_review_count})",
    ])

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
                    <span class="bb-kpi-label">MSCI ADOPTION</span>
                    <span class="bb-kpi-tag">{msci_count} 本</span>
                </div>
                <div class="bb-kpi-num">{msci_aum_share:.1f}%</div>
                <div class="bb-kpi-footer">MSCI AUM: {msci_aum / 1e12:.2f} 兆円</div>
            </div>
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-amber"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">NET INFLOW ({period_label})</span>
                    <span class="bb-kpi-tag">FLOW</span>
                </div>
                <div class="bb-kpi-num" style="font-size: 1.5rem;">{format_inflow_oku(total_inflow)}</div>
                <div class="bb-kpi-footer">非MSCI買い付け: {format_inflow_oku(non_msci_inflow)}</div>
            </div>
            <div class="bb-kpi-widget">
                <div class="bb-kpi-widget-topline topline-rose"></div>
                <div class="bb-kpi-header">
                    <span class="bb-kpi-label">SALES TARGETS</span>
                    <span class="bb-kpi-tag">OPPORTUNITY</span>
                </div>
                <div class="bb-kpi-num">{len(records) - msci_count}</div>
                <div class="bb-kpi-footer">要確認: {needs_review_count} 本</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_a1, col_a2 = st.columns([1, 1])

        with col_a1:
            st.markdown(f"#### ⚡ TOP 10 NET FLOW LEADERS ({period_label})")
            if valid_flows:
                sorted_by_flow = sorted(records, key=lambda x: record_flows.get(x.fund_code) or 0.0, reverse=True)[:10]
                flow_df = pd.DataFrame([
                    {
                        "ファンド名": f"[{r.management_company[:2]}] {r.fund_name[:18]}...",
                        "買い付け金額 (億円)": round((record_flows.get(r.fund_code) or 0.0) / 1e8, 1),
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
            else:
                st.info("ℹ️ 時系列データ蓄積中のため、ランキングは日次データ蓄積後に自動表示されます。")

        with col_a2:
            st.markdown(f"#### 🏷️ THEME BREAKDOWN & INFLOW VELOCITY ({period_label})")
            theme_agg: dict[str, dict] = {}
            for r in records:
                t = r.theme_category or "全世界・先進国株式"
                if t not in theme_agg:
                    theme_agg[t] = {"theme": t, "aum_oku": 0.0, "inflow_oku": 0.0, "count": 0, "has_inflow": False}
                theme_agg[t]["aum_oku"] += r.aum / 1e8
                flow_val = record_flows.get(r.fund_code)
                if flow_val is not None:
                    theme_agg[t]["inflow_oku"] += flow_val / 1e8
                    theme_agg[t]["has_inflow"] = True
                theme_agg[t]["count"] += 1

            theme_rows = []
            for t_data in theme_agg.values():
                theme_rows.append({
                    "テーマ分類": t_data["theme"],
                    "本数": t_data["count"],
                    "AUM合計(億円)": round(t_data["aum_oku"], 1),
                    f"買い付け金額合計 ({selected_period_key})": f"{t_data['inflow_oku']:,.1f}億円" if t_data["has_inflow"] else "データ蓄積中",
                })
            theme_df = pd.DataFrame(theme_rows)
            st.dataframe(
                theme_df,
                width="stretch",
                hide_index=True,
            )

        st.divider()
        st.markdown(f"#### 🎯 PRIME SALES TARGETS (Non-MSCI with High Inflow ｜ {period_label})")
        non_msci = [r for r in records if not r.is_msci and r.aum > 0]
        non_msci.sort(key=lambda x: (record_flows.get(x.fund_code) or 0.0, x.aum), reverse=True)

        targets_data = []
        for t in non_msci[:12]:
            targets_data.append({
                "順位": t.rank,
                "運用会社": t.management_company,
                "ファンド名": t.fund_name,
                "AUM (億円)": round(t.aum / 1e8, 0),
                f"買い付け金額 ({selected_period_key})": format_inflow_oku(record_flows.get(t.fund_code)),
                "テーマ": t.theme_category,
                "現ベンチマーク": t.benchmark or "—",
                "主要販売会社 (Broker)": t.top_distributors or t.primary_broker or "主要証券",
                "営業アクション (Target Playbook)": t.sales_pitch_action or "🎯 アプローチ対象",
            })
        targets_df = pd.DataFrame(targets_data)
        st.dataframe(
            targets_df,
            width="stretch",
            hide_index=True,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 2: DISTRIBUTOR RANKINGS
    # ═══════════════════════════════════════════════════════════════════════
    with tab2:
        st.markdown("### 🏛️ 販売会社別 取扱商品ランキング")
        st.caption(f"各販売会社が主力として販売しているファンドと残高一覧（二重計上防止済・集計期間: {period_label}）")

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
                    f"買い付け金額 ({selected_period_key})": format_inflow_oku(record_flows.get(f.get("fund_code", ""))),
                    "ベンチマーク指数": f["benchmark"],
                    "MSCI採用": "🟢 MSCI" if f["is_msci"] else "⚪ 他社",
                    "営業アプローチ戦略": f["action"],
                }
                for f in funds_in_dist
            ])

            st.dataframe(
                d_df,
                width="stretch",
                hide_index=True,
            )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: ALL FUNDS MATRIX & EDIT
    # ═══════════════════════════════════════════════════════════════════════
    with tab3:
        st.markdown("### 📋 全ファンド一覧・解析マトリクス")
        st.caption("全ファンドの残高・買い付け金額・ベンチマーク・テーマ・販売会社およびデータ来歴ステータス")

        col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1, 1, 1])
        company_filter = col_f1.selectbox("運用会社", ["すべて"] + list(company_options.values()))
        msci_filter = col_f2.selectbox("MSCI採用", ["すべて", "MSCIのみ", "非MSCIのみ"])
        theme_filter = col_f3.selectbox("テーマ分類", ["すべて"] + THEMES)
        search_query = col_f4.text_input("🔍 ファンド名 / コード検索", "")

        filtered_records = records
        if company_filter != "すべて":
            filtered_records = [r for r in filtered_records if r.management_company == company_filter]
        if msci_filter == "MSCIのみ":
            filtered_records = [r for r in filtered_records if r.is_msci]
        elif msci_filter == "非MSCIのみ":
            filtered_records = [r for r in filtered_records if not r.is_msci]
        if theme_filter != "すべて":
            filtered_records = [r for r in filtered_records if r.theme_category == theme_filter]
        if search_query:
            filtered_records = [r for r in filtered_records if search_query.lower() in r.fund_name.lower() or search_query.lower() in r.fund_code.lower()]

        table_rows = []
        for r in filtered_records:
            table_rows.append({
                "順位": r.rank,
                "運用会社": r.management_company,
                "ファンド名": r.fund_name,
                "コード": r.fund_code,
                "純資産 (億円)": round(r.aum / 1e8, 1),
                f"買い付け金額 ({selected_period_key})": format_inflow_oku(record_flows.get(r.fund_code)),
                "運用効果(億円)": round((r.performance_effect or 0.0) / 1e8, 1),
                "テーマ": r.theme_category,
                "ベンチマーク": r.benchmark or "—",
                "指数提供者": r.index_provider,
                "MSCI": "🟢 はい" if r.is_msci else "いいえ",
                "主要販売会社": r.top_distributors or r.primary_broker or "主要証券",
                "販社来歴": r.distributor_provenance.value if hasattr(r.distributor_provenance, "value") else str(r.distributor_provenance),
                "営業ターゲット判定": r.sales_pitch_action or "—",
                "信頼度": r.confidence.value if hasattr(r.confidence, "value") else str(r.confidence),
                "要確認": "⚠️" if r.needs_review else "✅",
            })

        st.dataframe(
            pd.DataFrame(table_rows),
            width="stretch",
            hide_index=True,
            height=450,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: PROPOSAL MATCHMAKER
    # ═══════════════════════════════════════════════════════════════════════
    with tab4:
        st.markdown("### 💡 商品企画提案 & 販社マッチメーカー")
        st.caption("運用会社の商品ラインアップの欠落（ギャップ）と各販売会社で最も売れるテーマをマッチングしたコンサルティング提案")

        company_for_pitch = st.selectbox(
            "提案対象の運用会社を選択",
            options=list(company_options.values()),
            index=0,
        )

        records_for_pitch = [r for r in records if r.management_company == company_for_pitch]
        if not records_for_pitch:
            records_for_pitch = records

        proposals = generate_product_proposals(records_for_pitch, company_for_pitch)

        st.markdown("#### 🎯 商品ラインアップ・ギャップ分析 & 組成推奨カード")
        prop_cols = st.columns(min(len(proposals), 3) if proposals else 1)
        for idx, prop in enumerate(proposals[:3]):
            with prop_cols[idx % len(prop_cols)]:
                p_border = "#f43f5e" if "最優先" in prop["priority"] else "#00F5D4"
                st.markdown(f"""
                <div style="background: #0f131c; border: 1px solid {p_border}; border-radius: 12px; padding: 18px; margin-bottom: 16px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="font-size: 0.75rem; font-weight: 700; color: {p_border};">{prop['priority']}</span>
                        <span style="font-size: 0.72rem; color: #94a3b8;">{prop['status']}</span>
                    </div>
                    <h4 style="margin: 0 0 8px 0; font-size: 1.1rem; color: #f8fafc;">{prop['theme']}</h4>
                    <p style="font-size: 0.82rem; color: #cbd5e1; margin-bottom: 12px;">{prop.get('proposal_narrative', prop.get('action_plan', ''))}</p>
                    <div style="background: rgba(255,255,255,0.04); padding: 8px 12px; border-radius: 6px; font-size: 0.8rem; margin-bottom: 8px;">
                        <b>推奨指数:</b> <code style="color: #00F5D4;">{prop['recommended_msci_index']}</code>
                    </div>
                    <div style="font-size: 0.78rem; color: #94a3b8;">
                        <b>最適主幹販社:</b> {prop['best_selling_brokers']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.divider()
        st.markdown("#### 📊 販売会社 × テーマ別 売れ行きマトリクス")
        matrix_rows = build_broker_theme_sales_matrix(records)
        matrix_df = pd.DataFrame([
            {
                "販売会社 (Broker)": m["broker"],
                "得意テーマ": m["theme"],
                "取扱本数": m["fund_count"],
                "AUM合計 (億円)": round(m["total_aum"] / 1e8, 1),
                f"買い付け金額 ({selected_period_key})": "データ蓄積中",
            }
            for m in matrix_rows[:12]
        ])
        st.dataframe(
            matrix_df,
            width="stretch",
            hide_index=True,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 5: DAILY FLOW INSPECTOR & PROSPECTUS
    # ═══════════════════════════════════════════════════════════════════════
    with tab5:
        st.markdown("### 🔍 ファンド別・日次買い付け推移 & 目論見書インスペクター")
        st.caption(f"1営業日ごとの資金流入（日次買い付け金額）および累積フローの推移グラフ（集計期間: {period_label}）")

        fund_options = {r.fund_code: f"#{r.rank} [{r.management_company[:2]}] {r.fund_name} ({format_aum_oku(r.aum)} / 買付 {format_inflow_oku(record_flows.get(r.fund_code))})" for r in records}
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
                st.write(f"**純資産(AUM)**: {format_aum_oku(selected_record.aum)} ｜ **期間買い付け金額 ({selected_period_key})**: `{format_inflow_oku(record_flows.get(selected_record.fund_code))}`")
                st.write(f"**現在のベンチマーク**: `{selected_record.benchmark or 'なし'}` ({selected_record.index_provider})")
                st.write(f"**MSCI採用**: {'🟢 はい' if selected_record.is_msci else 'いいえ'}")
                st.write(f"**主要販売会社**: `{selected_record.top_distributors or '主要証券'}`")
                
                prov_badge_html = get_provenance_badge(selected_record.distributor_provenance)
                st.markdown(f"**販社データ来歴**: {prov_badge_html}", unsafe_allow_html=True)
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

            series = load_series(selected_record.fund_code, days=period_days)
            if len(series) < 2:
                st.info(f"ℹ️ 日次データ蓄積中（現在{len(series)}営業日分）\n日次スナップショットが2営業日以上蓄積されると、買い付け金額と運用効果の分解グラフ・明細表が表示されます。")
            else:
                ledger_rows = []
                cum_flow = 0.0
                for s_i in range(1, len(series)):
                    prev_s = series[s_i - 1]
                    curr_s = series[s_i]
                    p_nav = float(prev_s.get("nav") or 0.0)
                    c_nav = float(curr_s.get("nav") or 0.0)
                    p_aum = float(prev_s.get("aum") or 0.0)
                    c_aum = float(curr_s.get("aum") or 0.0)
                    dist = float(curr_s.get("distribution") or 0.0)

                    if p_nav > 0 and p_aum > 0:
                        ret = (c_nav + dist - p_nav) / p_nav
                        perf = p_aum * ret
                        flow = (c_aum - p_aum) - perf
                        cum_flow += flow
                        ledger_rows.append({
                            "date": curr_s.get("date"),
                            "nav": c_nav,
                            "aum_oku": round(c_aum / 1e8, 1),
                            "daily_return_pct": round(ret * 100, 2),
                            "daily_perf_oku": round(perf / 1e8, 2),
                            "daily_inflow_oku": round(flow / 1e8, 2),
                            "cumulative_inflow_oku": round(cum_flow / 1e8, 1),
                        })

                if ledger_rows:
                    daily_df = pd.DataFrame(ledger_rows)

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
                        width="stretch",
                        hide_index=True,
                        height=300,
                    )

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 6: NEEDS REVIEW FUNDS
    # ═══════════════════════════════════════════════════════════════════════
    with tab6:
        st.markdown("### ⚠️ 要確認ファンド一覧 (NEEDS REVIEW)")
        st.caption("目論見書から販社が抽出できなかったファンドや、ベンチマーク信頼度が低位のファンド一覧です。手動オーバーライドまたは再解析を実行できます。")

        needs_review_funds = [r for r in records if r.needs_review]
        if not needs_review_funds:
            st.success("🎉 現在、要確認フラグの立っているファンドはありません。すべてのファンドの解析が完了しています。")
        else:
            st.warning(f"現在 **{len(needs_review_funds)} 本** のファンドが要確認状態です。")
            nr_rows = []
            for r in needs_review_funds:
                reasons = []
                if not r.benchmark or (hasattr(r.confidence, "value") and r.confidence.value == "low") or str(r.confidence).lower() == "low":
                    reasons.append("BM低信頼度・未特定")
                if not r.top_distributors or (hasattr(r.distributor_provenance, "value") and r.distributor_provenance.value == "synthetic") or str(r.distributor_provenance).lower() == "synthetic":
                    reasons.append("販売会社未取得 (推計中)")
                nr_rows.append({
                    "順位": r.rank,
                    "運用会社": r.management_company,
                    "ファンド名": r.fund_name,
                    "コード": r.fund_code,
                    "残高 (億円)": round(r.aum / 1e8, 1),
                    "現在のBM": r.benchmark or "—",
                    "確認理由": " / ".join(reasons) if reasons else "要確認",
                    "PDF有無": "あり" if r.prospectus_pdf_url else "なし",
                })
            st.dataframe(
                pd.DataFrame(nr_rows),
                width="stretch",
                hide_index=True,
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as _app_exc:
        st.error(f"⚠️ アプリケーション実行エラー: {_app_exc}")
        st.exception(_app_exc)
