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
  * One unreachable manager must not discard the others' data, so a partial
    failure still exits 0 and lets the workflow commit what it got. It is
    reported as a GitHub warning annotation and in the job summary so a
    green tick never silently hides a missing manager.
"""

from __future__ import annotations

import os
import sys
from datetime import date

from app.config import DATA_DIR, ensure_dirs
from app.daiwa_stage1 import run_stage1_daiwa
from app.muam_stage1 import run_stage1_muam
from app.stage1_list import run_stage1

MAX_FUNDS_PER_COMPANY = 100


def _managers() -> list[tuple[str, object]]:
    return [
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


def collect() -> list[tuple[str, int, str]]:
    """Run every manager. Returns (name, fund_count, error) per manager."""
    results: list[tuple[str, int, str]] = []
    for name, runner in _managers():
        try:
            funds = runner()  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001 - one dead API must not stop the rest
            print(f"  FAIL {name}: {exc}", flush=True)
            results.append((name, 0, str(exc)))
            continue
        print(f"  OK   {name}: {len(funds)} funds", flush=True)
        results.append((name, len(funds), ""))
    return results


def report(results: list[tuple[str, int, str]], today: str) -> None:
    """Surface per-manager outcomes on the GitHub run page.

    A partial failure keeps the run green so the healthy managers' data still
    gets committed, so the warning annotation is the only thing standing
    between a missing manager and nobody noticing.
    """
    failed = [(n, e) for n, _, e in results if e]

    if failed and os.getenv("GITHUB_ACTIONS"):
        for name, err in failed:
            print(f"::warning::{name}: snapshot skipped - {err}", flush=True)
        print(
            f"::warning::{len(failed)} of {len(results)} managers failed; "
            "committed data is incomplete for today.",
            flush=True,
        )

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    total = sum(c for _, c, _ in results)
    lines = [
        f"## Daily fund snapshots — {today}",
        "",
        f"**{total} funds captured across {len(results) - len(failed)}/{len(results)} managers.**",
        "",
        "| Manager | Funds | Status |",
        "| --- | ---: | --- |",
    ]
    for name, count, err in results:
        status = "✅ OK" if not err else f"❌ {err[:80]}"
        lines.append(f"| {name} | {count} | {status} |")
    if failed:
        lines += [
            "",
            "> ⚠️ Today's data is **incomplete**. A manager that fails here every "
            "day is permanently missing history — these APIs only serve current "
            "values, so a skipped day cannot be backfilled later.",
        ]
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    ensure_dirs()
    today = date.today().isoformat()

    results = collect()
    report(results, today)

    total = sum(count for _, count, _ in results)
    failed = [name for name, _, err in results if err]
    print(f"\n{total} snapshots written for {today}; {len(failed)} manager(s) failed.")

    if total == 0:
        print("No snapshots written - failing so the run is not silently green.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
