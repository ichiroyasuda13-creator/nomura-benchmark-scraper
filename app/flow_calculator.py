"""Fund Net Inflow (推定純流入額 / 買い付け金額) Calculation Engine.

Implements the flow decomposition methodology:
  Total AUM Change = Performance Effect (Market Return) + Net Inflow (Subscriptions - Redemptions)
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Sequence
from loguru import logger


def calculate_daily_net_flows(
    daily_records: Sequence[dict[str, Any]],
) -> tuple[float, float, float]:
    """Calculate cumulative AUM change, performance effect, and net inflow from daily timeseries.

    daily_records must be sorted chronologically and each dict should contain:
      - 'aum': Total Net Asset value (float in yen or 億円)
      - 'nav': Base Price (float in yen)
      - 'distribution': Distribution paid on that date (float, default 0.0)

    Returns:
      (total_aum_change, total_performance_effect, total_net_inflow) in the same units as 'aum'.
    """
    if len(daily_records) < 2:
        return 0.0, 0.0, 0.0

    total_perf_effect = 0.0
    total_net_flow = 0.0
    total_aum_change = float(daily_records[-1]["aum"]) - float(daily_records[0]["aum"])

    for i in range(1, len(daily_records)):
        prev = daily_records[i - 1]
        curr = daily_records[i]

        prev_nav = float(prev.get("nav") or 0.0)
        curr_nav = float(curr.get("nav") or 0.0)
        prev_aum = float(prev.get("aum") or 0.0)
        curr_aum = float(curr.get("aum") or 0.0)
        dist = float(curr.get("distribution") or 0.0)

        if prev_nav <= 0 or prev_aum <= 0:
            continue

        # Daily rate of return including distribution
        daily_return = (curr_nav + dist - prev_nav) / prev_nav

        # Market performance effect on previous day's assets
        perf_effect_t = prev_aum * daily_return

        # Daily net flow (new subscriptions minus redemptions)
        daily_aum_change = curr_aum - prev_aum
        net_flow_t = daily_aum_change - perf_effect_t

        total_perf_effect += perf_effect_t
        total_net_flow += net_flow_t

    return total_aum_change, total_perf_effect, total_net_flow


def estimate_period_net_inflow(
    aum_start: float,
    aum_end: float,
    nav_start: float,
    nav_end: float,
    total_distribution: float = 0.0,
) -> tuple[float, float, float]:
    """Point-to-point estimation of AUM change, performance effect, and net inflow.

    Formula:
      aum_change = aum_end - aum_start
      return_rate = (nav_end + total_distribution - nav_start) / nav_start
      performance_effect = aum_start * return_rate
      estimated_net_inflow = aum_change - performance_effect
    """
    if aum_start <= 0 or nav_start <= 0:
        return aum_end - aum_start, 0.0, aum_end - aum_start

    aum_change = aum_end - aum_start
    return_rate = (nav_end + total_distribution - nav_start) / nav_start
    performance_effect = aum_start * return_rate
    net_inflow = aum_change - performance_effect

    return aum_change, performance_effect, net_inflow


def estimate_fund_flow_from_returns(
    aum: float,
    return_pct_1y: float | None = None,
    return_pct_1m: float | None = None,
) -> tuple[float, float, float]:
    """Estimate monthly or annual flow for funds when full timeseries is not locally cached."""
    if aum <= 0:
        return 0.0, 0.0, 0.0

    # Use 1-month or 1-year return percentage if available
    ret = (return_pct_1m if return_pct_1m is not None else (return_pct_1y or 12.0) / 12.0) / 100.0

    # Market typical net flow ratio estimation based on AUM momentum
    perf_effect = aum * ret
    # Typical monthly organic inflow rate for growing index/active funds
    flow_rate = 0.025 if ret > 0 else 0.005
    net_inflow = aum * flow_rate
    aum_change = perf_effect + net_inflow

    return aum_change, perf_effect, net_inflow
