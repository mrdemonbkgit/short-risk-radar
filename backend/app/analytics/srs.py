from __future__ import annotations

from typing import Dict


def compute_srs(snapshot: Dict) -> int:
    # Simplified normalization: scale each component to [0,1] heuristically
    funding = abs(float(snapshot.get("funding_1h_pct", 0.0))) / 0.2  # 0.2%/h ~ strong
    basis = abs(float(snapshot.get("basis_twap15_pct", 0.0))) / 0.2
    dominance = float(snapshot.get("perp_dominance_pct", 0.0)) / 100.0
    delta_oi_pos = max(0.0, float(snapshot.get("delta_oi_1h_usdt", 0.0)))
    # Approximate scale for delta OI by OI
    oi_usdt = float(snapshot.get("oi_usdt", 0.0))
    delta_oi_scaled = min(1.0, delta_oi_pos / max(oi_usdt, 1.0))
    depth_ratio = float(snapshot.get("orderbook_imbalance", 0.0))
    depth_scaled = min(1.0, depth_ratio / 2.0)

    score = (
        0.25 * min(1.0, funding)
        + 0.20 * min(1.0, basis)
        + 0.20 * dominance
        + 0.20 * delta_oi_scaled
        + 0.15 * depth_scaled
    )
    score = max(0.0, min(1.0, score))
    return int(round(score * 100))
