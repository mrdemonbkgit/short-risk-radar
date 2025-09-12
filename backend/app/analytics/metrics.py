from __future__ import annotations

from typing import Iterable, List, Tuple


def calc_basis_pct(mark: float, index: float) -> float:
    if index == 0:
        return 0.0
    return (mark - index) / index * 100.0


def simple_twap(values: Iterable[float]) -> float:
    arr = list(values)
    if not arr:
        return 0.0
    return sum(arr) / len(arr)


def calc_dominance_pct(fut_vol24: float, spot_vol24_agg: float) -> float:
    denom = fut_vol24 + spot_vol24_agg
    if denom <= 0:
        return 0.0
    return fut_vol24 / denom * 100.0


def calc_delta(value_now: float, value_then: float) -> float:
    return value_now - value_then


def calc_orderbook_imbalance(sum_bids_qty: float, sum_asks_qty: float) -> float:
    if sum_asks_qty == 0:
        return 0.0
    return sum_bids_qty / sum_asks_qty


def calc_srs_placeholder(
    funding_1h_abs: float,
    basis_twap15_abs: float,
    perp_dominance_pct: float,
    delta_oi_pos: float,
    depth_ratio: float,
) -> int:
    # Simplified non-zscore version for MVP: weighted sum scaled to 0-100
    score = (
        0.25 * funding_1h_abs +
        0.20 * basis_twap15_abs +
        0.20 * (perp_dominance_pct / 100.0) +
        0.20 * delta_oi_pos +
        0.15 * depth_ratio
    )
    # Clamp and scale
    score = max(0.0, min(1.0, score))
    return int(round(score * 100))
