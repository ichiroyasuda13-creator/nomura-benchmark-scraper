# 野村アセットマネジメント ファンド・ベンチマーク抽出 & 営業インテリジェンス (Enterprise Edition)

野村アセットマネジメントの公募ファンド（AUM上位最大500本）について、交付目論見書PDFからベンチマーク指数・指数提供会社を自動抽出し、MSCIマーケットシェア分析および営業ターゲット特定を行うエンタープライズ・インテリジェンス基盤です。

---

## 🌟 主なアップグレード機能

1. **マルチLLMエンジン (Multi-LLM Provider Engine)**:
   - **Anthropic Claude** (Claude 3.5 Sonnet / Claude 3.7)
   - **Google Gemini** (Gemini 2.0 Flash / Pro)
   - **OpenAI** (GPT-4o / GPT-4o-mini)
   - **Ollama** (ローカルLLM / Llama 3 / Qwen / Mistral)
   - APIキーの有無を自動検知してフォールバックする「自動選択 (Auto)」モード対応
2. **高速並行パイプライン (High Concurrency)**:
   - `ThreadPoolExecutor` により、PDF URL解決・ダウンロード・テキスト抽出を並行処理（デフォルト5並行、最大10並行）。
3. **拡張指数プロバイダー & 精密クレンジング**:
   - MSCI, JPX/東証, 日経, S&P DJI, FTSE Russell, Nasdaq, ブルームバーグ, ICE Data Indices, Solactive, STOXX, Morningstar, Hang Seng/CSI 等を網羅。
   - `（対象株価指数）` や `（以下「対象インデックス」といいます）` などの目論見書特有ノイズを除去。
   - MRF / MMF / マネー・ポートフォリオ等の自動判定（`アクティブ（BMなし）`）。
4. **多機能スタイル適用済み Excel レポート (`nomura_benchmarks.xlsx`)**:
   - **シート1「ファンド一覧」**: 全ファンドのベンチマーク、提供会社、信頼度、レビュー状況（ゼブラ柄＆数値書式適用）。
   - **シート2「MSCI営業ターゲット」**: MSCI非採用の高AUMファンドを降順抽出した営業アプローチ優先リスト。
   - **シート3「指数提供者別サマリー」**: 指数会社別のAUMシェア（金額・構成比%）と採用ファンド本数のピボット集計。
5. **デュアル UI (Web App & Streamlit Dashboard)**:
   - **Web UI (`http://localhost:5000`)**: タブ切り替え（営業分析、ファンド一覧、パイプライン実行）、SSEリアルタイムログ、インライン手動編集＆単体再抽出モーダル。
   - **Streamlit (`streamlit run streamlit_app.py`)**: 3タブ構成（マーケット分析チャート、データエディタ一括保存、目論見書インスペクター）。

---

## 🛠️ セットアップ

```powershell
cd nomura-benchmark-scraper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

`.env` に利用したいLLMのAPIキーを設定してください（複数設定可能）:

```env
# いずれか1つ以上を設定（未設定時はルールベースで動作）
ANTHROPIC_API_KEY=your_anthropic_api_key
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key

# 任意設定
LLM_PROVIDER=auto       # auto | anthropic | gemini | openai | ollama
MAX_WORKERS=5           # 並行ダウンロード数
```

---

## 🚀 実行方法

### 1. CLI パイプライン

```powershell
# 全ステージ一括実行 (デフォルト100本、5並行)
.\.venv\Scripts\python.exe -m app.run

# プロバイダー指定 (例: Gemini)
.\.venv\Scripts\python.exe -m app.run --llm-provider gemini --workers 8 --max-funds 50

# ステージ指定実行
.\.venv\Scripts\python.exe -m app.run --stage 5
```

### 2. Web UI (Flask Enterprise)

```powershell
.\.venv\Scripts\python.exe web/server.py
```
ブラウザで `http://localhost:5000` を開きます。

### 3. Streamlit ダッシュボード

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```
ブラウザで `http://localhost:8501` を開きます。

---

## 🧪 テストの実行

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## 📁 データ出力一覧

- `data/funds.json` — ファンド基本情報リスト
- `data/pdfs/{fund_code}.pdf` — 交付目論見書PDF
- `data/text/{fund_code}.txt` — 抽出テキスト
- `data/benchmarks.json` — ベンチマーク抽出・レビュー結果JSON
- `output/nomura_benchmarks.xlsx` — 3シート構成スタイル付きExcel
- `output/nomura_benchmarks.csv` — CSV出力
