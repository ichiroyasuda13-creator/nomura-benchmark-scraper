# 野村アセットマネジメント ファンド・ベンチマーク抽出アプリ

野村アセットマネジメントの公募ファンド（AUM上位約100本）について、交付目論見書PDFからベンチマーク指数を自動抽出し、CSV/Excelとして出力するバッチパイプラインです。

## 機能概要

1. **Stage 1**: 野村ファンド検索APIからAUM降順でファンド一覧取得
2. **Stage 2**: 交付目論見書PDF URL解決（URL規則 + 詳細ページフォールバック）
3. **Stage 3**: PDFダウンロード（キャッシュ付き）
4. **Stage 4**: PyMuPDFによるテキスト抽出（必要時OCR）
5. **Stage 5**: 正規表現 + Anthropic Claude によるベンチマーク抽出
6. **Stage 6**: `output/nomura_benchmarks.csv` / `.xlsx` 出力

## セットアップ

```powershell
cd nomura-benchmark-scraper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

`.env` に `ANTHROPIC_API_KEY` を設定してください。未設定の場合は Stage 5 はルールベースのみで動作し、`needs_review=True` が増えます。

OCRを使う場合は以下も必要です。

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)（日本語 `jpn` 言語データ）
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/)（pdf2image用）

## 実行方法

全ステージ通し実行:

```powershell
python -m app.run
```

ステージ指定:

```powershell
python -m app.run --stage 1
python -m app.run --stage 2 --force
python -m app.run --stage 5 --no-llm
python -m app.run --max-funds 10
```

## 出力

- `data/funds.json` — ファンド一覧（Stage 1/2）
- `data/pdfs/{fund_code}.pdf` — 交付目論見書
- `data/text/{fund_code}.txt` — 抽出テキスト
- `data/benchmarks.json` — 抽出結果JSON
- `output/nomura_benchmarks.csv`
- `output/nomura_benchmarks.xlsx`
- `logs/nomura_benchmark.log`

## 技術メモ

### Stage 1 API

ブラウザDevTools調査の結果、検索結果は以下のJSONP APIから取得できます。

```
https://fund.nomura-am.co.jp/nomura/cgi/wrap/qjsonp.aspx?F=ctl/fund_search&KEY1=&KEY2=
```

AUMは `SRTTotalNetAsset`（円）でソートしています。

### 交付目論見書PDF URL

多くのファンドで以下の規則が成り立ちます。

```
https://www.nomura-am.co.jp/fund/pros_gen/Y1{NAMCode}.pdf
```

例外がある場合は詳細ページHTMLから「交付目論見書」リンクを抽出します。

## テスト

```powershell
pytest
```

受け入れ基準の一部として、以下のケースをルールベース単体テストに含めています。

- MSCI/TOPIX連動インデックス型
- マイバランス70（複合ベンチマーク）
- 野村PIMCO・世界インカム戦略（アクティブ + ベンチマーク/参考指数）
- ベンチマーク非設定アクティブ

## 注意事項

- リクエスト間隔はデフォルト1.5秒
- PDF/テキスト/JSONはキャッシュされ、再実行時は差分のみ処理
- `needs_review=True` の行は人手確認を推奨
- 過度なアクセスは避け、社内利用目的に限定してください
