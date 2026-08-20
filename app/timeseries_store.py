"""Daily Fund Snapshot & Time-series Storage Engine.

Persists daily snapshots of Fund AUM, NAV, and distribution to data/timeseries/{fund_code}.jsonl.
Provides query capabilities for calculating multi-day flow decomposition.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from loguru import logger

from app.config import DATA_DIR

TIMESERIES_DIR = DATA_DIR / "timeseries"


def append_snapshot(
    fund_code: str,
    date: str,
    aum: float,
    nav: float,
    distribution: float = 0.0,
) -> None:
    """Append a daily snapshot to data/timeseries/{fund_code}.jsonl.

    Skips if an entry for the same date already exists.
    """
    if not fund_code or not date:
        return

    TIMESERIES_DIR.mkdir(parents=True, exist_ok=True)
    file_path = TIMESERIES_DIR / f"{fund_code}.jsonl"

    existing_dates: set[str] = set()
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        d = record.get("date")
                        if d:
                            existing_dates.add(str(d))
                    except json.JSONDecodeError:
                        pass

    if date in existing_dates:
        return

    entry = {
        "date": date,
        "aum": float(aum),
        "nav": float(nav),
        "distribution": float(distribution),
    }

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_series(fund_code: str, days: int = 30) -> list[dict[str, Any]]:
    """Load chronologically sorted daily records for fund_code up to `days` entries."""
    if not fund_code:
        return []

    file_path = TIMESERIES_DIR / f"{fund_code}.jsonl"
    if not file_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Sort chronologically by date
    records.sort(key=lambda x: str(x.get("date", "")))

    if days > 0 and len(records) > days:
        records = records[-days:]

    return records
