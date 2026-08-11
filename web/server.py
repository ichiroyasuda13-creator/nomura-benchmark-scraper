"""Flask web server wrapping the Nomura benchmark extraction pipeline."""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from loguru import logger

# ── App Setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

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

        # Auto-detect stage transitions from log messages
        msg_text = record["message"]
        for i, label in enumerate(["Stage1", "Stage2", "Stage3", "Stage4", "Stage5", "Stage6"]):
            if label in msg_text and ("fetching" in msg_text.lower()
                                      or "resolving" in msg_text.lower()
                                      or "download" in msg_text.lower()
                                      or "wrote text" in msg_text.lower()
                                      or "extract" in msg_text.lower()
                                      or "wrote" in msg_text.lower()
                                      or "available" in msg_text.lower()
                                      or "using cached" in msg_text.lower()
                                      or "saved" in msg_text.lower()):
                with _lock:
                    _state["current_stage"] = i + 1
                _broadcast("stage", {"stage": i + 1, "label": _state["stage_labels"][i]})
                break


_sse_sink = _SSELogSink()
_sink_id = logger.add(_sse_sink, format="{time:HH:mm:ss} | {level:<8} | {message}", level="DEBUG")


def _run_pipeline(max_funds: int, use_llm: bool, force: bool) -> None:
    """Execute pipeline stages in a background thread."""
    from app.config import ensure_dirs
    from app.http_client import setup_logging
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

        run_stage2(force=force)

        with _lock:
            _state["current_stage"] = 3
        _broadcast("stage", {"stage": 3, "label": _state["stage_labels"][2]})

        if _state["cancelled"]:
            return

        run_stage3(force=force)

        with _lock:
            _state["current_stage"] = 4
        _broadcast("stage", {"stage": 4, "label": _state["stage_labels"][3]})

        if _state["cancelled"]:
            return

        run_stage4(force=force, allow_ocr=True)

        with _lock:
            _state["current_stage"] = 5
        _broadcast("stage", {"stage": 5, "label": _state["stage_labels"][4]})

        if _state["cancelled"]:
            return

        records = run_stage5(use_llm=use_llm)

        with _lock:
            _state["current_stage"] = 6
        _broadcast("stage", {"stage": 6, "label": _state["stage_labels"][5]})

        if _state["cancelled"]:
            return

        run_stage6(records)

        # Store results for the API
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

    thread = threading.Thread(
        target=_run_pipeline,
        args=(max_funds, use_llm, force),
        daemon=True,
    )
    thread.start()
    return jsonify({"status": "started", "max_funds": max_funds, "use_llm": use_llm})


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
            # Send initial state
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

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/results")
def api_results():
    with _lock:
        return jsonify({
            "running": _state["running"],
            "results": _state["results"],
            "error": _state["error"],
        })


@app.route("/api/download/<fmt>")
def api_download(fmt: str):
    output_dir = PROJECT_ROOT / "output"
    if fmt == "csv":
        path = output_dir / "nomura_benchmarks.csv"
        mime = "text/csv"
    elif fmt in ("xlsx", "excel"):
        path = output_dir / "nomura_benchmarks.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        return jsonify({"error": "Invalid format. Use csv or xlsx"}), 400

    if not path.exists():
        return jsonify({"error": "No output file yet. Run pipeline first."}), 404

    return send_file(path, mimetype=mime, as_attachment=True, download_name=path.name)


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  Nomura Benchmark Scraper - Web UI")
    print("  http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
