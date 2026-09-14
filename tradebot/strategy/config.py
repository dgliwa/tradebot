from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Schedule:
    timezone: str = "America/New_York"
    hour: int = 18
    minute: int = 0


@dataclass(frozen=True)
class Capital:
    starting_cash: float = 10_000.0
    weekly_contribution: float = 250.0
    contribution_weekday: int = 0
    position_fraction: float = 0.03
    max_positions: int = 10
    max_new_positions: int = 3


@dataclass(frozen=True)
class Universe:
    tracked_politicians: tuple[str, ...] = ("Nancy Pelosi",)
    lookback_days: int = 180
    rank_improvement_threshold: int = 2


@dataclass(frozen=True)
class Signals:
    momentum_21_weight: float = 0.4
    momentum_63_weight: float = 0.6
    insider_value_weight: float = 0.5
    insider_buyers_weight: float = 0.25
    insider_recency_weight: float = 0.25
    insider_weight: float = 4 / 7
    momentum_weight: float = 3 / 7


@dataclass(frozen=True)
class Risk:
    stop_loss_fraction: float = 0.08
    max_holding_days: int = 84
    negative_score_runs: int = 2
    stop_reentry_days: int = 28


@dataclass(frozen=True)
class Execution:
    slippage_bps: int = 10
    commission: float = 0.0
    allow_fractional: bool = True
    allow_margin: bool = False
    allow_short: bool = False


@dataclass(frozen=True)
class Paper:
    auto_submit_after_reconciled_orders: int = 10
    max_order_fraction: float = 0.03
    max_daily_new_positions: int = 3


@dataclass(frozen=True)
class Strategy:
    implementation: str = "pelosi"
    version: str = "0.1.0"
    name: str = "pelosi-led-long-equity"
    benchmark: str = "SPY"
    schedule: Schedule = field(default_factory=Schedule)
    capital: Capital = field(default_factory=Capital)
    universe: Universe = field(default_factory=Universe)
    signals: Signals = field(default_factory=Signals)
    risk: Risk = field(default_factory=Risk)
    execution: Execution = field(default_factory=Execution)
    paper: Paper = field(default_factory=Paper)

    def __post_init__(self) -> None:
        if self.implementation != "pelosi":
            raise ValueError(f"Unknown strategy implementation: {self.implementation}")
        if not self.version.strip() or not self.name.strip():
            raise ValueError("Strategy name and version are required")
        if self.benchmark != self.benchmark.strip().upper() or not self.benchmark:
            raise ValueError("Benchmark must be a normalized ticker")
        try:
            ZoneInfo(self.schedule.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown strategy timezone") from exc
        if not 0 <= self.schedule.hour <= 23 or not 0 <= self.schedule.minute <= 59:
            raise ValueError("Invalid strategy schedule")
        if self.capital.starting_cash <= 0 or self.capital.weekly_contribution < 0:
            raise ValueError("Invalid strategy capital")
        if not 0 <= self.capital.contribution_weekday <= 6:
            raise ValueError("Invalid contribution weekday")
        if not 0 < self.capital.position_fraction <= 1:
            raise ValueError("Invalid position fraction")
        if self.capital.max_positions < 1 or not 1 <= self.capital.max_new_positions <= self.capital.max_positions:
            raise ValueError("Invalid position limits")
        if not self.universe.tracked_politicians or any(not name.strip() for name in self.universe.tracked_politicians):
            raise ValueError("At least one tracked politician is required")
        if self.universe.lookback_days < 1 or self.universe.rank_improvement_threshold < 1:
            raise ValueError("Invalid universe settings")
        self._weights("momentum features", self.signals.momentum_21_weight, self.signals.momentum_63_weight)
        self._weights(
            "insider features", self.signals.insider_value_weight,
            self.signals.insider_buyers_weight, self.signals.insider_recency_weight,
        )
        self._weights("composite signals", self.signals.insider_weight, self.signals.momentum_weight)
        if not 0 < self.risk.stop_loss_fraction < 1 or min(
            self.risk.max_holding_days, self.risk.negative_score_runs, self.risk.stop_reentry_days
        ) < 1:
            raise ValueError("Invalid risk settings")
        if self.execution.slippage_bps < 0 or self.execution.commission < 0:
            raise ValueError("Invalid execution costs")
        if self.execution.allow_margin or self.execution.allow_short:
            raise ValueError("PoC forbids margin and short selling")
        if not self.execution.allow_fractional:
            raise ValueError("PoC requires fractional shares")
        if self.paper.auto_submit_after_reconciled_orders < 1:
            raise ValueError("Paper automation requires a positive reconciliation threshold")
        if not 0 < self.paper.max_order_fraction <= self.capital.position_fraction:
            raise ValueError("Paper order limit exceeds strategy position size")
        if not 1 <= self.paper.max_daily_new_positions <= self.capital.max_new_positions:
            raise ValueError("Paper daily limit exceeds strategy limit")

    @staticmethod
    def _weights(label: str, *weights: float) -> None:
        if any(weight < 0 for weight in weights) or abs(sum(weights) - 1) > 1e-9:
            raise ValueError(f"{label} weights must be nonnegative and sum to one")

    @property
    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_json.encode()).hexdigest()


def load_strategy_config(path: Path = Path("strategy.toml")) -> Strategy:
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Strategy file not found: {path}") from exc
    sections = {
        "schedule": Schedule,
        "capital": Capital,
        "universe": Universe,
        "signals": Signals,
        "risk": Risk,
        "execution": Execution,
        "paper": Paper,
    }
    unknown = set(values) - {"implementation", "version", "name", "benchmark", *sections}
    if unknown:
        raise ValueError(f"Unknown strategy keys: {', '.join(sorted(unknown))}")
    kwargs = {key: values[key] for key in ("implementation", "version", "name", "benchmark") if key in values}
    for name, kind in sections.items():
        section = values.get(name, {})
        if not isinstance(section, dict):
            raise ValueError(f"Strategy section {name} must be a table")
        if name == "universe" and "tracked_politicians" in section:
            section = {**section, "tracked_politicians": tuple(section["tracked_politicians"])}
        try:
            kwargs[name] = kind(**section)
        except TypeError as exc:
            raise ValueError(f"Invalid strategy section {name}: {exc}") from exc
    return Strategy(**kwargs)


def load_strategy(path: Path = Path("strategy.toml")):
    from tradebot.strategy.pelosi import PelosiStrategy

    config = load_strategy_config(path)
    implementations = {"pelosi": PelosiStrategy}
    try:
        return implementations[config.implementation](config)
    except KeyError as exc:
        raise ValueError(f"Unknown strategy implementation: {config.implementation}") from exc
