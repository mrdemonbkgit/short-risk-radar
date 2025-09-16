from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import time


class Symbol(BaseModel):
    symbol: str
    base: Optional[str] = None
    quote: Optional[str] = None
    venue: Literal["BINANCEUSDTM"] = "BINANCEUSDTM"


class BorrowVenue(BaseModel):
    ex: str
    apr_pct: float


class BorrowInfo(BaseModel):
    shortable: bool = False
    venues: List[BorrowVenue] = Field(default_factory=list)


class Snapshot(BaseModel):
    symbol: str
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    mark: float
    index: float
    basis_pct: float
    basis_twap15_pct: float
    funding_1h_pct: float
    funding_daily_est_pct: float
    oi_usdt: float
    delta_oi_1h_usdt: float
    perp_dominance_pct: float
    orderbook_imbalance: float
    borrow: BorrowInfo
    srs: int
    traffic_light: Literal["RED", "YELLOW", "GREEN"]
    next_funding_in_sec: int

    # Optional enrichments
    funding_interval_hours: Optional[int] = None
    rule_reasons: Optional[List[str]] = None
    has_spot: Optional[bool] = None
    fut_vol24_usdt: Optional[float] = None
    spot_vol24_usdt: Optional[float] = None
    dominance_unknown: Optional[bool] = None


class TimeseriesPoint(BaseModel):
    ts: int
    value: float


class RulesExplanation(BaseModel):
    traffic_light: Literal["RED", "YELLOW", "GREEN"]
    reasons: List[str]
