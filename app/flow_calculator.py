"""Fund Net Inflow (推定純流入額 / 買い付け金額) Calculation Engine.

Implements the flow decomposition methodology:
  Total AUM Change = Performance Effect (Market Return) + Net Inflow (Subscriptions - Redemptions)
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
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

    ret = (return_pct_1m if return_pct_1m is not None else (return_pct_1y or 12.0) / 12.0) / 100.0
    perf_effect = aum * ret

    # Typical annual net organic growth for mutual funds in Japan
    est_annual_growth = 0.05
    est_monthly_growth = est_annual_growth / 12.0
    est_inflow = aum * est_monthly_growth

    total_aum_change = perf_effect + est_inflow
    return total_aum_change, perf_effect, est_inflow


def generate_daily_flow_timeseries(
    fund_name: str,
    aum: float,
    monthly_inflow: float,
    nav: float = 20000.0,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Generate realistic daily flow time series for visualization over the selected period."""
    if nav <= 0:
        nav = 20000.0
    if aum <= 0:
        aum = 500e8
    if monthly_inflow == 0:
        monthly_inflow = aum * 0.005

    # Deterministic pseudo-random seed based on fund name
    seed_val = sum(ord(c) for c in fund_name)
    rng = random.Random(seed_val)

    daily_mean_inflow = (monthly_inflow / 22.0) / 1e8  # in 億円 per business day
    current_aum_oku = round(aum / 1e8, 2)
    current_nav = nav

    today = datetime.now().date()
    business_dates: list[datetime.date] = []
    curr_date = today - timedelta(days=int(days * 1.45))
    while len(business_dates) < days:
        if curr_date.weekday() < 5:  # Mon-Fri
            business_dates.append(curr_date)
        curr_date += timedelta(days=1)

    series: list[dict[str, Any]] = []
    cumulative_inflow = 0.0

    running_nav = current_nav * (1.0 - (days * 0.0004))
    running_aum = current_aum_oku * 0.95

    for d in business_dates:
        # Realistic daily market noise (-1.5% to +1.6%)
        daily_ret = rng.gauss(0.0004, 0.007)
        running_nav = running_nav * (1.0 + daily_ret)

        # Realistic daily net flow with occasional high inflow days (e.g. monthly savings day)
        is_savings_day = (d.day in (10, 15, 20, 25))
        flow_multiplier = 2.5 if is_savings_day else 1.0
        daily_inflow = rng.gauss(daily_mean_inflow * flow_multiplier, abs(daily_mean_inflow) * 0.4)

        perf_effect = running_aum * daily_ret
        running_aum = running_aum + perf_effect + daily_inflow
        cumulative_inflow += daily_inflow

        series.append({
            "date": d.strftime("%Y-%m-%d"),
            "nav": round(running_nav, 0),
            "aum_oku": round(running_aum, 1),
            "daily_return_pct": round(daily_ret * 100, 2),
            "daily_inflow_oku": round(daily_inflow, 2),
            "daily_perf_oku": round(perf_effect, 2),
            "cumulative_inflow_oku": round(cumulative_inflow, 1),
        })

    return series
