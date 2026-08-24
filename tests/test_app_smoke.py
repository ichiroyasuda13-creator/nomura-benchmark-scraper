"""Regression tests for defects that unit tests could not see.

The Streamlit dashboard once died on startup with an UnboundLocalError before
rendering a single tab, while every unit test still passed. These tests drive
the real entry points so that class of breakage is caught.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import parse_aum_yen

# AppTest resolves relative paths against the calling file, so anchor on the repo root.
APP_PATH = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234", 1234.0),
        ("1,234", 1234.0),
        ("  567  ", 567.0),
        ("12.5", 12.5),
        (2500.0, 2500.0),
        ("", 0.0),
        (None, 0.0),
        # Placeholders and unit suffixes seen in the live fund feed. stage1
        # sorts every fund through parse_aum_yen, so these must not raise.
        ("―", 0.0),
        ("-", 0.0),
        ("N/A", 0.0),
        ("1,234億円", 1234.0),
    ],
)
def test_parse_aum_yen_never_raises(raw: object, expected: float) -> None:
    assert parse_aum_yen(raw) == expected  # type: ignore[arg-type]


def test_stage1_sort_survives_placeholder_aum() -> None:
    """One unparseable AUM cell must not abort the whole stage1 ranking."""
    raw_funds = [
        {"SRTTotalNetAsset": "5000"},
        {"SRTTotalNetAsset": "―"},
        {"SRTTotalNetAsset": "12,000"},
        {"SRTTotalNetAsset": None},
    ]
    ordered = sorted(
        raw_funds,
        key=lambda item: parse_aum_yen(item.get("SRTTotalNetAsset")),
        reverse=True,
    )
    assert [parse_aum_yen(f.get("SRTTotalNetAsset")) for f in ordered] == [
        12000.0,
        5000.0,
        0.0,
        0.0,
    ]


def test_llm_key_helpers_fall_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keys exported after import time must still be picked up."""
    import app.llm as llm

    monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "", raising=False)
    monkeypatch.setattr(llm, "GEMINI_API_KEY", "", raising=False)
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-from-env")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-from-env")

    assert llm._get_anthropic_key() == "sk-ant-from-env"
    assert llm._get_gemini_key() == "gem-from-env"
    assert llm._get_openai_key() == "sk-oai-from-env"


def test_streamlit_app_renders_without_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dashboard must render end-to-end with no LLM key configured.

    This is the exact condition that used to raise
    ``cannot access local variable 'cfg'`` and abort the whole page.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    at = AppTest.from_file(APP_PATH, default_timeout=300).run()

    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    # All dashboard tabs must be reached, not just the pre-crash header.
    assert len(at.tabs) >= 6


def test_flask_index_and_json_routes_respond() -> None:
    from web.server import app as flask_app

    flask_app.config["TESTING"] = True
    client = flask_app.test_client()

    assert client.get("/").status_code == 200
    for route in ("/api/llm/providers", "/api/results", "/api/analytics"):
        assert client.get(route).status_code == 200, route
