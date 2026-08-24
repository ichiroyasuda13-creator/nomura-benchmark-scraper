"""Append one dated AUM/NAV snapshot per fund to data/timeseries/.

Run daily by .github/workflows/daily_scrape.yml. The flow-decomposition engine
needs at least two dated points per fund before it can separate market
performance from net inflow, so this is what actually accumulates over time.

Notes:
  * Each manager's stage1 runner defaults to writing data/funds.json, so they
    would overwrite one another -- every call passes an explicit output_path.
  * Fallback to the bundled master JSON is disabled: recording stale AUM as
    today's reading would fabricate a zero-flow day rather than reporting a
    gap. A manager whose API is unreachable is skipped and reported.
"""

from __future__ import annotations

import sys
from datetime import date

from app.config import DATA_DIR, ensure_dirs
from app.daiwa_stage1 import run_stage1_daiwa
from app.muam_stage1 import run_stage1_muam
from app.stage1_list import run_stage1

MAX_FUNDS_PER_COMPANY = 100


def main() -> int:
    ensure_dirs()
    today = date.today().isoformat()

    managers = [
        (
            "野村アセットマネジメント",
            lambda: run_stage1(force=True, max_funds=MAX_FUNDS_PER_COMPANY),
        ),
        (
            "大和アセットマネジメント",
            lambda: run_stage1_daiwa(
                force=True,
                max_funds=MAX_FUNDS_PER_COMPANY,
                output_path=DATA_DIR / "daiwa_funds.json",
                allow_fallback=False,
            ),
        ),
        (
            "三菱UFJアセットマネジメント",
            lambda: run_stage1_muam(
                force=True,
                max_funds=MAX_FUNDS_PER_COMPANY,
                output_path=DATA_DIR / "muam_funds.json",
                allow_fallback=False,
            ),
        ),
    ]

    total = 0
    failures: list[str] = []
    for name, runner in managers:
        try:
            funds = runner()
        except Exception as exc:  # noqa: BLE001 - one dead API must not stop the rest
            print(f"  FAIL {name}: {exc}", flush=True)
            failures.append(name)
            continue
        total += len(funds)
        print(f"  OK   {name}: {len(funds)} funds snapshotted for {today}", flush=True)

    print(f"\n{total} snapshots written for {today}; {len(failures)} manager(s) failed.")

    if total == 0:
        print("No snapshots written - failing so the run is not silently green.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
