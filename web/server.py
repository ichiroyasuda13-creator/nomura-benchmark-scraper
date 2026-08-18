"""Flask web server wrapping the Nomura benchmark extraction pipeline."""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from loguru import logger

from app.config import (
    BENCHMARKS_JSON,
    FUNDS_JSON,
    OUTPUT_DIR,
    PROJECT_ROOT,
    TEXT_DIR,
    ensure_dirs,
)
from app.http_client import load_json, setup_logging
from app.llm import get_available_providers, llm_available
from app.models import BenchmarkRecord
from app.stage5_benchmark import reextract_single_fund, update_manual_override

# ── App Setup ──────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

# ── Pipeline state ─────────────────────────────────────────────────────────
_state = {
    "running": False,
    "cancelled": False,
    "current_stage": 0,
    "total_stages": 6,
    "stage_labels": [
        "ファンド一覧取得",
        "PDF URL解決",
        "PDFダウンロード",
        "テキスト抽出",
        "ベンチマーク抽出",
        "CSV/Excel出力",
    ],
    "results": [],
    "error": None,
}
_lock = threading.Lock()
_log_queues: list[queue.Queue] = []


def _broadcast(event: str, data: dict) -> None:
    """Push an SSE event to all connected clients."""
    msg = json.dumps(data, ensure_ascii=False, default=str)
    for q in list(_log_queues):
        try:
            q.put_nowait(f"event: {event}\ndata: {msg}\n\n")
        except queue.Full:
            pass


class _SSELogSink:
    """Loguru sink that broadcasts log lines to SSE clients."""

    def write(self, message):  # noqa: ANN001
        record = message.record
        text = str(message).rstrip()
        _broadcast("log", {
            "level": record["level"].name,
            "message": text,
            "time": str(record["time"]),
        })

        msg_text = record["message"]
        for i, label in enumerate(["Stage1", "Stage2", "Stage3", "Stage4", "Stage5", "Stage6"]):
            if label in msg_text and any(
                k in msg_text.lower()
                for k in ("fetching", "resolving", "download", "wrote text", "extract", "wrote", "available", "cached", "saved", "completed")
            ):
                with _lock:
                    _state["current_stage"] = i + 1
                _broadcast("stage", {"stage": i + 1, "label": _state["stage_labels"][i]})
                break


_sse_sink = _SSELogSink()
_sink_id = logger.add(_sse_sink, format="{time:HH:mm:ss} | {level:<8} | {message}", level="DEBUG")


def _run_pipeline(
    max_funds: int,
    use_llm: bool,
    force: bool,
    provider: str | None = None,
    model: str | None = None,
    workers: int = 5,
) -> None:
    """Execute pipeline stages in a background thread."""
    from app.stage1_list import run_stage1
    from app.stage2_pdf_url import run_stage2
    from app.stage3_download import run_stage3
    from app.stage4_extract_text import run_stage4
    from app.stage5_benchmark import run_stage5
    from app.stage6_output import run_stage6

    try:
        ensure_dirs()
        setup_logging()

        with _lock:
            _state["current_stage"] = 1
        _broadcast("stage", {"stage": 1, "label": _state["stage_labels"][0]})

        if _state["cancelled"]:
            return

        run_stage1(force=force, max_funds=max_funds)

        with _lock:
            _state["current_stage"] = 2
        _broadcast("stage", {"stage": 2, "label": _state["stage_labels"][1]})

        if _state["cancelled"]:
            return

        run_stage2(force=force, max_workers=workers)

        with _lock:
            _state["current_stage"] = 3
        _broadcast("stage", {"stage": 3, "label": _state["stage_labels"][2]})

        if _state["cancelled"]:
            return

        run_stage3(force=force, max_workers=workers)

        with _lock:
            _state["current_stage"] = 4
        _broadcast("stage", {"stage": 4, "label": _state["stage_labels"][3]})

        if _state["cancelled"]:
            return

        run_stage4(force=force, allow_ocr=True, max_workers=workers)

        with _lock:
            _state["current_stage"] = 5
        _broadcast("stage", {"stage": 5, "label": _state["stage_labels"][4]})

        if _state["cancelled"]:
            return

        records = run_stage5(use_llm=use_llm, provider=provider, model=model)

        with _lock:
            _state["current_stage"] = 6
        _broadcast("stage", {"stage": 6, "label": _state["stage_labels"][5]})

        if _state["cancelled"]:
            return

        run_stage6(records)

        with _lock:
            _state["results"] = [r.model_dump(mode="json") for r in records]
            _state["current_stage"] = 7  # done

        _broadcast("complete", {
            "total": len(records),
            "needs_review": sum(1 for r in records if r.needs_review),
        })
        logger.info("Pipeline completed: {} funds processed", len(records))

    except Exception as exc:
        logger.error("Pipeline error: {}", exc)
        with _lock:
            _state["error"] = str(exc)
        _broadcast("error", {"message": str(exc)})
    finally:
        with _lock:
            _state["running"] = False
        _broadcast("done", {"running": False})


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/llm/providers")
def api_llm_providers():
    return jsonify({"providers": get_available_providers()})


@app.route("/api/analytics")
def api_analytics():
    raw = load_json(BENCHMARKS_JSON, [])
    if not raw:
        return jsonify({"empty": True})

    total_aum = sum(float(r.get("aum") or 0.0) for r in raw)
    total_funds = len(raw)
    msci_funds = [r for r in raw if r.get("is_msci")]
    msci_aum = sum(float(r.get("aum") or 0.0) for r in msci_funds)

    provider_map = {}
    for r in raw:
        prov = r.get("index_provider") or "なし"
        if prov not in provider_map:
            provider_map[prov] = {"name": prov, "count": 0, "aum": 0.0, "is_msci": bool(r.get("is_msci"))}
        provider_map[prov]["count"] += 1
        provider_map[prov]["aum"] += float(r.get("aum") or 0.0)

    # Top non-MSCI sales targets
    non_msci = [r for r in raw if not r.get("is_msci") and float(r.get("aum") or 0.0) > 0]
    non_msci.sort(key=lambda x: float(x.get("aum") or 0.0), reverse=True)
    top_targets = non_msci[:10]

    return jsonify({
        "empty": False,
        "total_funds": total_funds,
        "total_aum": total_aum,
        "msci_count": len(msci_funds),
        "msci_aum": msci_aum,
        "msci_aum_share": (msci_aum / total_aum * 100) if total_aum else 0,
        "msci_count_share": (len(msci_funds) / total_funds * 100) if total_funds else 0,
        "providers": sorted(provider_map.values(), key=lambda x: x["aum"], reverse=True),
        "top_targets": top_targets,
    })


@app.route("/api/funds/<fund_code>/detail")
def api_fund_detail(fund_code: str):
    raw_bench = load_json(BENCHMARKS_JSON, [])
    matching = [r for r in raw_bench if r.get("fund_code") == fund_code]
    if not matching:
        return jsonify({"error": "Fund not found"}), 404

    record = matching[0]
    text_path = TEXT_DIR / f"{fund_code}.txt"
    extracted_text = ""
    if text_path.exists():
        try:
            extracted_text = text_path.read_text(encoding="utf-8")[:12000]
        except Exception:
            pass

    return jsonify({
        "record": record,
        "extracted_text": extracted_text,
    })


@app.route("/api/funds/<fund_code>/edit", methods=["POST"])
def api_fund_edit(fund_code: str):
    data = request.get_json(silent=True) or {}
    benchmark = data.get("benchmark")
    index_provider = data.get("index_provider", "なし")
    fund_type = data.get("fund_type", "インデックス")
    needs_review = bool(data.get("needs_review", False))
    comment = data.get("comment", "")
    reviewer = data.get("reviewer", "Analyst")

    updated = update_manual_override(
        fund_code=fund_code,
        benchmark=benchmark,
        index_provider=index_provider,
        fund_type=fund_type,
        needs_review=needs_review,
        comment=comment,
        reviewer=reviewer,
    )
    if not updated:
        return jsonify({"error": "Failed to update record"}), 404

    return jsonify({"status": "updated", "record": updated.model_dump(mode="json")})


@app.route("/api/funds/<fund_code>/reextract", methods=["POST"])
def api_fund_reextract(fund_code: str):
    data = request.get_json(silent=True) or {}
    use_llm = bool(data.get("use_llm", True))
    provider = data.get("provider")
    model = data.get("model")
    force_ocr = bool(data.get("force_ocr", False))

    updated = reextract_single_fund(
        fund_code=fund_code,
        use_llm=use_llm,
        provider=provider,
        model=model,
        force_ocr=force_ocr,
    )
    if not updated:
        return jsonify({"error": "Fund not found or extraction failed"}), 404

    return jsonify({"status": "reextracted", "record": updated.model_dump(mode="json")})


@app.route("/api/run", methods=["POST"])
def api_run():
    with _lock:
        if _state["running"]:
            return jsonify({"error": "Pipeline is already running"}), 409
        _state["running"] = True
        _state["cancelled"] = False
        _state["current_stage"] = 0
        _state["results"] = []
        _state["error"] = None

    body = request.get_json(silent=True) or {}
    max_funds = min(int(body.get("max_funds", 100)), 500)
    use_llm = bool(body.get("use_llm", True))
    force = bool(body.get("force", False))
    provider = body.get("provider") or None
    model = body.get("model") or None
    workers = int(body.get("workers", 5))

    thread = threading.Thread(
        target=_run_pipeline,
        args=(max_funds, use_llm, force, provider, model, workers),
        daemon=True,
    )
    thread.start()
    return jsonify({
        "status": "started",
        "max_funds": max_funds,
        "use_llm": use_llm,
        "provider": provider,
    })


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    with _lock:
        if not _state["running"]:
            return jsonify({"error": "No pipeline running"}), 400
        _state["cancelled"] = True
    _broadcast("cancelled", {})
    return jsonify({"status": "cancelling"})


@app.route("/api/status")
def api_status():
    """SSE stream of pipeline progress and log lines."""
    q: queue.Queue = queue.Queue(maxsize=500)
    _log_queues.append(q)

    def stream():
        try:
            with _lock:
                init = {
                    "running": _state["running"],
                    "current_stage": _state["current_stage"],
                }
            yield f"event: init\ndata: {json.dumps(init)}\n\n"

            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            if q in _log_queues:
                _log_queues.remove(q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/results")
def api_results():
    with _lock:
        results = _state["results"]
    if not results:
        raw = load_json(BENCHMARKS_JSON, [])
        results = raw
    return jsonify({
        "running": _state["running"],
        "results": results,
        "error": _state["error"],
    })


@app.route("/api/download/<fmt>")
def api_download(fmt: str):
    if fmt == "csv":
        path = OUTPUT_DIR / "nomura_benchmarks.csv"
        mime = "text/csv"
    elif fmt in ("xlsx", "excel"):
        path = OUTPUT_DIR / "nomura_benchmarks.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        return jsonify({"error": "Invalid format. Use csv or xlsx"}), 400

    if not path.exists():
        return jsonify({"error": "No output file yet. Run pipeline first."}), 404

    return send_file(path, mimetype=mime, as_attachment=True, download_name=path.name)


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  Nomura Benchmark Scraper - Web UI (Enterprise Edition)")
    print("  http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

