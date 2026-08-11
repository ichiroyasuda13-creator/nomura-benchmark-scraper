"""Streamlit web app for Nomura Benchmark Scraper."""

from __future__ import annotations

import io
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Ensure project root is importable ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import BENCHMARKS_JSON, OUTPUT_DIR, ensure_dirs
from app.http_client import load_json, setup_logging
from app.models import BenchmarkRecord

# ── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="野村ベンチマーク抽出ツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Import fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+JP:wght@300;400;500;600;700&display=swap');

    .main { font-family: 'Inter', 'Noto Sans JP', sans-serif; }

    /* Glass card style */
    .glass-card {
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    /* Stage progress bar */
    .stage-bar {
        display: flex;
        align-items: center;
        gap: 0;
        margin: 1rem 0;
    }

    .stage-dot {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 700;
        flex-shrink: 0;
        transition: all 0.3s;
    }

    .stage-dot.pending {
        background: #111827;
        border: 2px solid rgba(255,255,255,0.1);
        color: #64748b;
    }

    .stage-dot.active {
        border: 2px solid #6366f1;
        color: #6366f1;
        background: #111827;
        box-shadow: 0 0 15px rgba(99,102,241,0.25);
        animation: pulse 2s infinite;
    }

    .stage-dot.done {
        background: #34d399;
        border: 2px solid #34d399;
        color: white;
    }

    .stage-connector {
        flex: 1;
        height: 2px;
        background: rgba(255,255,255,0.06);
        min-width: 20px;
    }

    .stage-connector.done {
        background: #34d399;
    }

    .stage-label {
        font-size: 0.6rem;
        color: #64748b;
        text-align: center;
        margin-top: 4px;
    }

    .stage-label.active { color: #818cf8; }
    .stage-label.done { color: #34d399; }

    @keyframes pulse {
        0%, 100% { box-shadow: 0 0 15px rgba(99,102,241,0.25); }
        50% { box-shadow: 0 0 25px rgba(99,102,241,0.4); }
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 100px;
        font-size: 0.68rem;
        font-weight: 600;
    }

    .badge-success { background: rgba(52,211,153,0.1); color: #34d399; }
    .badge-warning { background: rgba(251,191,36,0.1); color: #fbbf24; }
    .badge-error { background: rgba(248,113,113,0.1); color: #f87171; }
    .badge-info { background: rgba(96,165,250,0.1); color: #60a5fa; }

    /* Stat cards */
    .stat-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin: 1rem 0;
    }

    .stat-card {
        text-align: center;
        padding: 1rem;
        background: rgba(255,255,255,0.04);
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.06);
    }

    .stat-value {
        font-size: 1.8rem;
        font-weight: 700;
        line-height: 1.2;
    }

    .stat-label {
        font-size: 0.72rem;
        color: #64748b;
        margin-top: 4px;
    }

    .accent { color: #6366f1; }
    .success { color: #34d399; }
    .warning { color: #fbbf24; }

    /* Header */
    .app-title {
        text-align: center;
        margin-bottom: 2rem;
    }

    .app-title h1 {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #f1f5f9 30%, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .app-title p {
        color: #94a3b8;
        font-size: 0.9rem;
    }

    /* Hide Streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)


# ── Stage Progress Rendering ──────────────────────────────────────────────
STAGE_LABELS = ["一覧取得", "PDF URL", "DL", "テキスト", "BM抽出", "出力"]


def render_stage_progress(current_stage: int) -> None:
    """Render the 6-stage progress bar as HTML."""
    html_parts = ['<div class="stage-bar">']
    for i in range(1, 7):
        if i < current_stage:
            cls = "done"
        elif i == current_stage:
            cls = "active"
        else:
            cls = "pending"

        html_parts.append(
            f'<div style="display:flex;flex-direction:column;align-items:center">'
            f'<div class="stage-dot {cls}">{i}</div>'
            f'<div class="stage-label {cls}">{STAGE_LABELS[i - 1]}</div>'
            f'</div>'
        )
        if i < 6:
            conn_cls = "done" if i < current_stage else ""
            html_parts.append(f'<div class="stage-connector {conn_cls}"></div>')

    html_parts.append("</div>")
    return "".join(html_parts)


# ── Pipeline Runner ────────────────────────────────────────────────────────
def run_pipeline(max_funds: int, use_llm: bool, force: bool) -> list[BenchmarkRecord]:
    """Run the full pipeline with Streamlit progress updates."""
    from app.stage1_list import run_stage1
    from app.stage2_pdf_url import run_stage2
    from app.stage3_download import run_stage3
    from app.stage4_extract_text import run_stage4
    from app.stage5_benchmark import run_stage5
    from app.stage6_output import run_stage6

    ensure_dirs()
    setup_logging()

    progress_bar = st.progress(0, text="パイプライン開始中...")
    stage_display = st.empty()
    log_area = st.empty()
    logs: list[str] = []

    def update(stage: int, msg: str) -> None:
        progress_bar.progress(stage / 7, text=f"Stage {stage}/6: {STAGE_LABELS[stage - 1]}")
        stage_display.markdown(render_stage_progress(stage), unsafe_allow_html=True)
        logs.append(f"[Stage {stage}] {msg}")
        log_area.code("\n".join(logs[-20:]), language="text")

    # Stage 1
    update(1, "ファンド一覧取得中...")
    funds = run_stage1(force=force, max_funds=max_funds)
    logs.append(f"  → {len(funds)} ファンド取得完了")
    log_area.code("\n".join(logs[-20:]), language="text")

    # Stage 2
    update(2, "PDF URL解決中...")
    run_stage2(force=force)
    logs.append("  → PDF URL解決完了")
    log_area.code("\n".join(logs[-20:]), language="text")

    # Stage 3
    update(3, "PDFダウンロード中...")
    run_stage3(force=force)
    logs.append("  → PDFダウンロード完了")
    log_area.code("\n".join(logs[-20:]), language="text")

    # Stage 4
    update(4, "テキスト抽出中...")
    run_stage4(force=force, allow_ocr=True)
    logs.append("  → テキスト抽出完了")
    log_area.code("\n".join(logs[-20:]), language="text")

    # Stage 5
    update(5, "ベンチマーク抽出中 (LLM使用)" if use_llm else "ベンチマーク抽出中 (ルールベース)")
    records = run_stage5(use_llm=use_llm)
    logs.append(f"  → {len(records)} ファンドのベンチマーク抽出完了")
    log_area.code("\n".join(logs[-20:]), language="text")

    # Stage 6
    update(6, "CSV/Excel出力中...")
    run_stage6(records)
    logs.append("  → CSV/Excel出力完了")
    log_area.code("\n".join(logs[-20:]), language="text")

    progress_bar.progress(1.0, text="✅ パイプライン完了!")
    stage_display.markdown(render_stage_progress(7), unsafe_allow_html=True)

    return records


# ── Load existing results ──────────────────────────────────────────────────
def load_existing_results() -> list[dict]:
    """Load previously extracted results from JSON."""
    if BENCHMARKS_JSON.exists():
        raw = load_json(BENCHMARKS_JSON, [])
        return [BenchmarkRecord.model_validate(item).model_dump(mode="json") for item in raw]
    return []


# ── Confidence badge helper ────────────────────────────────────────────────
def confidence_color(conf: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "⚪")


# ── Main App ───────────────────────────────────────────────────────────────
def main() -> None:
    # Header
    st.markdown(
        '<div class="app-title">'
        "<h1>📊 野村ベンチマーク抽出ツール</h1>"
        "<p>Nomura Fund Benchmark Extractor — 交付目論見書PDFからベンチマーク指数を自動抽出</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Sidebar Controls ───────────────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ 実行設定")

        max_funds = st.slider(
            "取得ファンド数",
            min_value=5,
            max_value=200,
            value=100,
            step=5,
            help="AUM順上位からの取得数",
        )

        use_llm = st.toggle(
            "LLM抽出 (Claude Sonnet 5)",
            value=True,
            help="ONでAnthropicのLLMを使用、OFFでルールベースのみ",
        )

        force = st.toggle(
            "キャッシュ無視で再実行",
            value=False,
            help="ONでPDF/テキスト等を全て再取得",
        )

        st.divider()

        run_clicked = st.button(
            "🚀 実行開始",
            type="primary",
            use_container_width=True,
        )

        st.divider()

        # API Key status
        from app.config import ANTHROPIC_API_KEY
        if ANTHROPIC_API_KEY:
            st.success("✅ API Key 設定済み", icon="🔑")
        else:
            st.warning("⚠️ API Key 未設定", icon="🔑")
            st.caption("Streamlit Cloud: Secrets で `ANTHROPIC_API_KEY` を設定")

    # ── Run Pipeline ───────────────────────────────────────────────────────
    if run_clicked:
        with st.spinner("パイプライン実行中..."):
            try:
                records = run_pipeline(max_funds, use_llm, force)
                st.session_state["results"] = [
                    r.model_dump(mode="json") for r in records
                ]
                st.success(f"✅ {len(records)} ファンドの抽出が完了しました!")
            except Exception as e:
                st.error(f"❌ エラー: {e}")

    # ── Load results (from session or disk) ────────────────────────────────
    results = st.session_state.get("results")
    if not results:
        results = load_existing_results()
        if results:
            st.session_state["results"] = results

    # ── Display Results ────────────────────────────────────────────────────
    if results:
        # Stats
        total = len(results)
        extracted = sum(1 for r in results if r.get("benchmark") and r["benchmark"] != "なし")
        needs_review = sum(1 for r in results if r.get("needs_review"))
        msci_count = sum(1 for r in results if r.get("is_msci"))

        st.markdown(
            f"""
            <div class="stat-grid">
                <div class="stat-card">
                    <div class="stat-value accent">{total}</div>
                    <div class="stat-label">ファンド総数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value success">{extracted}</div>
                    <div class="stat-label">BM抽出成功</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning">{needs_review}</div>
                    <div class="stat-label">要確認</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{msci_count}</div>
                    <div class="stat-label">MSCI関連</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Download buttons
        col1, col2, col3 = st.columns([1, 1, 4])
        csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"
        xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"

        if csv_path.exists():
            with open(csv_path, "rb") as f:
                col1.download_button(
                    "📄 CSV",
                    f.read(),
                    file_name="nomura_benchmarks.csv",
                    mime="text/csv",
                )

        if xlsx_path.exists():
            with open(xlsx_path, "rb") as f:
                col2.download_button(
                    "📊 Excel",
                    f.read(),
                    file_name="nomura_benchmarks.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        # Search filter
        search = st.text_input(
            "🔍 検索",
            placeholder="ファンド名・ベンチマークで検索...",
            label_visibility="collapsed",
        )

        # Filter results
        display_results = results
        if search:
            query = search.lower()
            display_results = [
                r for r in results
                if query in (r.get("fund_name") or "").lower()
                or query in (r.get("benchmark") or "").lower()
                or query in (r.get("fund_code") or "").lower()
            ]

        # Build DataFrame for display
        df = pd.DataFrame(display_results)

        display_cols = {
            "rank": "順位",
            "fund_name": "ファンド名",
            "fund_code": "コード",
            "aum": "AUM",
            "fund_type": "種別",
            "benchmark": "ベンチマーク",
            "index_provider": "指数提供者",
            "confidence": "信頼度",
            "extraction_method": "抽出方法",
            "needs_review": "要確認",
        }

        if not df.empty:
            show_df = df[[c for c in display_cols if c in df.columns]].copy()
            show_df.rename(columns=display_cols, inplace=True)

            # Format AUM to 億円
            if "AUM" in show_df.columns:
                show_df["AUM"] = show_df["AUM"].apply(
                    lambda x: f"{x / 1e8:,.0f}億円" if x else "—"
                )

            # Format confidence
            if "信頼度" in show_df.columns:
                show_df["信頼度"] = show_df["信頼度"].apply(
                    lambda x: f"{confidence_color(x)} {x}"
                )

            # Format needs_review
            if "要確認" in show_df.columns:
                show_df["要確認"] = show_df["要確認"].apply(
                    lambda x: "⚠️ 要確認" if x else "✅ OK"
                )

            st.dataframe(
                show_df,
                use_container_width=True,
                hide_index=True,
                height=600,
            )
        else:
            st.info("検索結果がありません")

    else:
        # Empty state
        st.markdown(
            """
            <div style="text-align:center; padding: 3rem; color: #64748b;">
                <div style="font-size: 3rem; opacity: 0.3;">📂</div>
                <p style="font-size: 0.9rem; margin-top: 1rem;">
                    サイドバーの「実行開始」をクリックしてベンチマーク抽出を開始してください
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
