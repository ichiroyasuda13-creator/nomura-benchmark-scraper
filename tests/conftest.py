"""Shared test fixtures.

The stage1 runners persist to the repository's real data directory: a dated
AUM/NAV snapshot per fund under ``data/timeseries/``, plus the fund list at
``data/funds.json``. Under test that wrote mock values straight into the
tracked production data -- adding a fabricated second point for the funds used
as fixtures (enough for the dashboard's flow decomposition to report invented
inflows) and truncating funds.json. Redirect both to a temp directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_data_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.daiwa_stage1 as daiwa
    import app.muam_stage1 as muam
    import app.stage1_list as stage1
    import app.timeseries_store as store

    monkeypatch.setattr(store, "TIMESERIES_DIR", tmp_path / "timeseries")

    # Each runner binds FUNDS_JSON at import time, so patch all three.
    funds_json = tmp_path / "funds.json"
    for module in (stage1, daiwa, muam):
        monkeypatch.setattr(module, "FUNDS_JSON", funds_json, raising=False)
