from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


def _load_env() -> None:
    mode = os.environ.get("TRADEBOT_MODE", "paper").lower()
    env_file = Path(f".env.{mode}")
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)


_load_env()


@dataclass
class Settings:
    mode: str = field(default_factory=lambda: os.environ.get("TRADEBOT_MODE", "paper"))
    db_path: Path = field(
        default_factory=lambda: Path(os.environ.get("TRADEBOT_DB_PATH", "data/tradebot.duckdb"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("TRADEBOT_LOG_LEVEL", "INFO"))
    alpaca_key: str = field(default_factory=lambda: os.environ.get("ALPACA_KEY", ""))
    alpaca_secret: str = field(default_factory=lambda: os.environ.get("ALPACA_SECRET", ""))
    alpaca_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        )
    )
    universe: list[str] = field(
        default_factory=lambda: os.environ.get(
            "TRADEBOT_UNIVERSE",
            "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,V,UNH,JNJ,XOM,WMT,PG,MA,HD,CVX,MRK,ABBV,PEP",
        ).split(",")
    )

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"


settings = Settings()
