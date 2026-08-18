from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd
from loguru import logger

from app.config import BENCHMARKS_JSON, OUTPUT_DIR
from app.http_client import load_json
from app.models import BenchmarkRecord, format_aum_oku

OUTPUT_COLUMNS = [
    "rank",
    "fund_name",
    "fund_code",
    "aum",
    "aum_date",
    "is_etf",
    "fund_type",
    "benchmark",
    "benchmark_detail",
    "index_provider",
    "is_msci",
    "reference_index",
    "confidence",
    "extraction_method",
    "prospectus_pdf_url",
    "source_page_detail_url",
    "note",
    "needs_review",
    "manual_override",
    "review_comment",
    "reviewed_at",
]

JAPANESE_COLUMNS = {
    "rank": "順位",
    "fund_name": "ファンド名",
    "fund_code": "ファンドコード",
    "aum": "純資産総額 (円)",
    "aum_oku": "純資産 (億円)",
    "aum_date": "基準日",
    "is_etf": "ETF",
    "fund_type": "ファンド種別",
    "benchmark": "ベンチマーク指数",
    "benchmark_detail": "詳細構成",
    "index_provider": "指数提供者",
    "is_msci": "MSCI採用",
    "reference_index": "参考指数",
    "confidence": "抽出信頼度",
    "extraction_method": "抽出方法",
    "needs_review": "要確認",
    "manual_override": "手動編集",
    "review_comment": "レビューメモ",
    "note": "システム備考",
    "prospectus_pdf_url": "交付目論見書URL",
}


def records_to_dataframe(records: list[BenchmarkRecord]) -> pd.DataFrame:
    rows = [record.model_dump(mode="json") for record in records]
    frame = pd.DataFrame(rows)
    for column in OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[OUTPUT_COLUMNS]


def _style_header(ws: openpyxl.worksheet.worksheet.Worksheet, max_col: int) -> None:
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Meiryo UI", size=10, bold=True, color="FFFFFF")
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col in range(1, max_col + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align
    ws.row_dimensions[1].height = 26


def _auto_fit_columns(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            # Japanese wide char width approx 1.7
            length = sum(1.7 if ord(c) > 127 else 1.0 for c in val_str)
            if length > max_len:
                max_len = int(length)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 10)


def create_styled_excel(records: list[BenchmarkRecord], filepath: Path) -> None:
    wb = openpyxl.Workbook()

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    msci_yes_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    msci_yes_font = Font(name="Meiryo UI", size=9, color="065F46", bold=True)
    review_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    review_font = Font(name="Meiryo UI", size=9, color="92400E", bold=True)
    regular_font = Font(name="Meiryo UI", size=9)

    # ── Sheet 1: All Funds ───────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "ファンド一覧"

    headers1 = [
        "順位", "ファンド名", "コード", "純資産総額 (円)", "純資産 (億円)", "基準日",
        "ETF", "種別", "ベンチマーク指数", "指数提供者", "MSCI採用", "信頼度",
        "抽出方法", "要確認", "手動編集", "レビューメモ", "目論見書PDF",
    ]
    ws1.append(headers1)
    _style_header(ws1, len(headers1))

    for row_idx, r in enumerate(records, start=2):
        oku_val = round(r.aum / 1e8, 1) if r.aum else 0.0
        row_data = [
            r.rank,
            r.fund_name,
            r.fund_code,
            r.aum,
            oku_val,
            str(r.aum_date) if r.aum_date else "",
            "ETF" if r.is_etf else "一般投信",
            r.fund_type.value if hasattr(r.fund_type, "value") else str(r.fund_type),
            r.benchmark or "—",
            r.index_provider,
            "はい" if r.is_msci else "いいえ",
            r.confidence.value if hasattr(r.confidence, "value") else str(r.confidence),
            r.extraction_method.value if hasattr(r.extraction_method, "value") else str(r.extraction_method),
            "要確認" if r.needs_review else "OK",
            "手動" if r.manual_override else "自動",
            r.review_comment or r.note,
            r.prospectus_pdf_url or "",
        ]
        ws1.append(row_data)

        for col_idx in range(1, len(headers1) + 1):
            cell = ws1.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            if row_idx % 2 == 1:
                cell.fill = zebra_fill

            # Format numbers
            if col_idx == 4:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif col_idx == 5:
                cell.number_format = "#,##0.0"
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in (1, 3, 6, 7, 11, 12, 13, 14, 15):
                cell.alignment = Alignment(horizontal="center")

            # MSCI Yes Highlight
            if col_idx == 11 and r.is_msci:
                cell.fill = msci_yes_fill
                cell.font = msci_yes_font
            # Needs Review Highlight
            if col_idx == 14 and r.needs_review:
                cell.fill = review_fill
                cell.font = review_font

    _auto_fit_columns(ws1)

    # ── Sheet 2: MSCI Sales Targets ──────────────────────────────────────
    ws2 = wb.create_sheet(title="MSCI営業ターゲット")
    headers2 = [
        "順位", "ファンド名", "コード", "純資産 (億円)", "ファンド種別",
        "現在のベンチマーク", "現在の指数提供会社", "営業機会 / 提案戦略",
    ]
    ws2.append(headers2)
    _style_header(ws2, len(headers2))

    non_msci_records = [r for r in records if not r.is_msci and r.aum > 0]
    non_msci_records.sort(key=lambda x: x.aum, reverse=True)

    for row_idx, r in enumerate(non_msci_records, start=2):
        oku_val = round(r.aum / 1e8, 1)
        strategy = ""
        if r.index_provider == "JPX/東証":
            strategy = "国内株/TOPIX採用中 → MSCI Japan/ACWIへのリプレイスまたはオルタナティブ提案"
        elif r.index_provider == "日本経済新聞社":
            strategy = "日経225採用中 → MSCI World / ACWI / Japan KOKUSAIへの拡張提案"
        elif r.index_provider == "S&P DJI":
            strategy = "S&P採用中 → MSCI USA / MSCI ACWIへの対抗提案"
        elif r.index_provider == "FTSE Russell":
            strategy = "FTSE採用中 → MSCI先進国/新興国インデックスへの切替提案"
        else:
            strategy = "高AUM非MSCIファンド → ベンチマーク新設またはMSCIインデックス採用商談"

        row_data = [
            r.rank,
            r.fund_name,
            r.fund_code,
            oku_val,
            r.fund_type.value if hasattr(r.fund_type, "value") else str(r.fund_type),
            r.benchmark or "—",
            r.index_provider,
            strategy,
        ]
        ws2.append(row_data)
        for col_idx in range(1, len(headers2) + 1):
            cell = ws2.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            if row_idx % 2 == 1:
                cell.fill = zebra_fill
            if col_idx == 4:
                cell.number_format = "#,##0.0"
                cell.alignment = Alignment(horizontal="right")

    _auto_fit_columns(ws2)

    # ── Sheet 3: Index Provider Market Share Summary ─────────────────────
    ws3 = wb.create_sheet(title="指数提供者別サマリー")
    headers3 = [
        "指数提供者", "ファンド数", "ファンド数シェア (%)", "純資産総額 (億円)", "AUMシェア (%)", "MSCIフラグ",
    ]
    ws3.append(headers3)
    _style_header(ws3, len(headers3))

    total_aum = sum(r.aum for r in records)
    total_count = len(records)

    provider_map: dict[str, dict[str, Any]] = {}
    for r in records:
        prov = r.index_provider or "なし"
        if prov not in provider_map:
            provider_map[prov] = {"count": 0, "aum": 0.0, "is_msci": r.is_msci}
        provider_map[prov]["count"] += 1
        provider_map[prov]["aum"] += r.aum

    sorted_providers = sorted(provider_map.items(), key=lambda x: x[1]["aum"], reverse=True)

    for row_idx, (prov, data) in enumerate(sorted_providers, start=2):
        count_share = (data["count"] / total_count * 100) if total_count else 0
        aum_share = (data["aum"] / total_aum * 100) if total_aum else 0
        oku = round(data["aum"] / 1e8, 1)

        row_data = [
            prov,
            data["count"],
            round(count_share, 1),
            oku,
            round(aum_share, 1),
            "MSCI" if data["is_msci"] else "他社",
        ]
        ws3.append(row_data)

        for col_idx in range(1, len(headers3) + 1):
            cell = ws3.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            if row_idx % 2 == 1:
                cell.fill = zebra_fill
            if col_idx in (2, 4):
                cell.number_format = "#,##0.0" if col_idx == 4 else "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in (3, 5):
                cell.number_format = "0.0%"
                cell.value = (count_share / 100) if col_idx == 3 else (aum_share / 100)
                cell.alignment = Alignment(horizontal="right")
            elif col_idx == 6:
                cell.alignment = Alignment(horizontal="center")
                if data["is_msci"]:
                    cell.fill = msci_yes_fill
                    cell.font = msci_yes_font

    _auto_fit_columns(ws3)

    wb.save(filepath)


def run_stage6(records: list[BenchmarkRecord] | None = None) -> tuple[Path, Path]:
    if records is None:
        raw = load_json(BENCHMARKS_JSON, [])
        records = [BenchmarkRecord.model_validate(item) for item in raw]
    if not records:
        raise RuntimeError("Stage6 requires benchmark records. Run stage5 first.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = records_to_dataframe(records)
    csv_path = OUTPUT_DIR / "nomura_benchmarks.csv"
    xlsx_path = OUTPUT_DIR / "nomura_benchmarks.xlsx"

    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    create_styled_excel(records, xlsx_path)
    logger.info("Stage6: wrote {} and styled {}", csv_path, xlsx_path)
    return csv_path, xlsx_path

