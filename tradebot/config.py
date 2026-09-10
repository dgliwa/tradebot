from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"
DEFAULT_UNIVERSE = "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,V,UNH,JNJ,XOM,WMT,PG,MA,HD,CVX,MRK,ABBV,PEP"


def normalize_universe(tickers: list[str]) -> list[str]:
    result = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not result:
        raise ValueError("Universe must contain at least one ticker")
    return result


@dataclass
class Settings:
    mode: str = "paper"
    db_path: Path | None = None
    log_level: str = "INFO"
    alpaca_key: str = field(default="", repr=False)
    alpaca_secret: str = field(default="", repr=False)
    alpaca_base_url: str | None = None
    universe: list[str] = field(default_factory=lambda: DEFAULT_UNIVERSE.split(","))
    sec_user_agent: str = ""

    def __post_init__(self) -> None:
        self.mode = self.mode.strip().lower()
        if self.mode not in {"paper", "live"}:
            raise ValueError("TRADEBOT_MODE must be paper or live")
        expected_url = LIVE_URL if self.is_live else PAPER_URL
        self.alpaca_base_url = (self.alpaca_base_url or expected_url).rstrip("/")
        if self.alpaca_base_url != expected_url:
            raise ValueError("ALPACA_BASE_URL does not match TRADEBOT_MODE")
        self.db_path = Path(self.db_path) if self.db_path else Path(f"data/tradebot-{self.mode}.duckdb")
        self.universe = normalize_universe(self.universe)
        self.log_level = self.log_level.upper()
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid TRADEBOT_LOG_LEVEL")

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"


def load_settings(*, environ: Mapping[str, str] | None = None, env_dir: Path = Path(".")) -> Settings:
    """Read only the selected env file; never mutate the process environment."""
    env = dict(os.environ if environ is None else environ)
    mode = env.get("TRADEBOT_MODE", "paper").strip().lower()
    if mode not in {"paper", "live"}:
        raise ValueError("TRADEBOT_MODE must be paper or live")
    path = env_dir / f".env.{mode}"
    values = {k: v for k, v in dotenv_values(path, interpolate=False).items() if v is not None} if path.exists() else {}
    if values.get("TRADEBOT_MODE", mode).strip().lower() != mode:
        raise ValueError(f"TRADEBOT_MODE in {path.name} conflicts with selected mode")
    values.update(env)
    return Settings(
        mode=mode,
        db_path=Path(values["TRADEBOT_DB_PATH"]) if values.get("TRADEBOT_DB_PATH") else None,
        log_level=values.get("TRADEBOT_LOG_LEVEL", "INFO"),
        alpaca_key=values.get("ALPACA_KEY", ""),
        alpaca_secret=values.get("ALPACA_SECRET", ""),
        alpaca_base_url=values.get("ALPACA_BASE_URL"),
        universe=values.get("TRADEBOT_UNIVERSE", DEFAULT_UNIVERSE).split(","),
        sec_user_agent=values.get("SEC_USER_AGENT", ""),
    )
