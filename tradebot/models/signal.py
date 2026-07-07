from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Recommendation:
    """Output of the composite scorer for a single ticker on a run date.

    composite_score and rank are always set. Per-signal scores are
    optional because not all signals are active in every phase.
    Weights (insider=0.4, congressional=0.3, momentum=0.3) are applied
    by the scorer, not stored here.
    """
    ticker: str
    run_date: date
    composite_score: float
    rank: int
    insider_score: Optional[float] = None
    momentum_score: Optional[float] = None
    congressional_score: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
