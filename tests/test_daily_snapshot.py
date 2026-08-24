"""Tests for the daily snapshot job's failure reporting.

A partial failure keeps the run green so the healthy managers' data still gets
committed. That makes the warning annotation the only thing standing between a
silently missing manager and nobody noticing, so it is worth testing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "daily_snapshot.py"


def _load():
    spec = importlib.util.spec_from_file_location("daily_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PARTIAL = [
    ("野村アセットマネジメント", 100, ""),
    ("大和アセットマネジメント", 100, ""),
    ("三菱UFJアセットマネジメント", 0, "API blocked; fallback disabled."),
]
ALL_OK = [(name, 100, "") for name, _, _ in PARTIAL]


def test_partial_failure_emits_warning_annotations(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    _load().report(PARTIAL, "2026-08-25")

    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "三菱UFJアセットマネジメント" in out
    assert "1 of 3 managers failed" in out


def test_full_success_emits_no_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    _load().report(ALL_OK, "2026-08-25")

    assert "::warning::" not in capsys.readouterr().out


def test_stays_quiet_outside_ci(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    _load().report(PARTIAL, "2026-08-25")

    assert capsys.readouterr().out == ""


def test_job_summary_reports_every_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    _load().report(PARTIAL, "2026-08-25")

    text = summary.read_text(encoding="utf-8")
    assert "200 funds captured across 2/3 managers" in text
    for name, _, _ in PARTIAL:
        assert name in text
    assert "incomplete" in text
