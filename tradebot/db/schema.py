"""DDL constants for all TradeBot tables.

All statements use CREATE TABLE IF NOT EXISTS for idempotent DDL (D-06).
Execution order in ALL_TABLES matters: orders references instruments,
trades references orders — foreign key tables must precede dependent tables.
"""
from __future__ import annotations

SCHEMA_VERSIONS = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version    INTEGER PRIMARY KEY,
    name       VARCHAR NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

INSTRUMENTS = """
CREATE TABLE IF NOT EXISTS instruments (
    id              VARCHAR PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    instrument_type VARCHAR NOT NULL CHECK (instrument_type IN ('stock', 'call', 'put')),
    expiry          DATE,
    strike          DOUBLE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

RAW_PRICES = """
CREATE TABLE IF NOT EXISTS raw_prices (
    id         BIGINT PRIMARY KEY,
    ticker     VARCHAR NOT NULL,
    date       DATE NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    volume     BIGINT,
    fetched_at TIMESTAMPTZ NOT NULL,
    source     VARCHAR NOT NULL DEFAULT 'yfinance'
)
"""

RAW_INSIDER = """
CREATE TABLE IF NOT EXISTS raw_insider (
    id               VARCHAR PRIMARY KEY,
    ticker           VARCHAR NOT NULL,
    filer_name       VARCHAR,
    transaction_date DATE NOT NULL,
    filed_at         DATE NOT NULL,
    shares           DOUBLE,
    price_per_share  DOUBLE,
    form_type        VARCHAR NOT NULL DEFAULT 'Form4',
    transaction_code VARCHAR NOT NULL,
    fetched_at       TIMESTAMPTZ NOT NULL
)
"""

RAW_CONGRESSIONAL = """
CREATE TABLE IF NOT EXISTS raw_congressional (
    id               VARCHAR PRIMARY KEY,
    ticker           VARCHAR NOT NULL,
    member_name      VARCHAR,
    transaction_date DATE NOT NULL,
    filed_at         DATE NOT NULL,
    amount_min       DOUBLE,
    amount_max       DOUBLE,
    transaction_type VARCHAR,
    fetched_at       TIMESTAMPTZ NOT NULL
)
"""

RAW_MACRO = """
CREATE TABLE IF NOT EXISTS raw_macro (
    id               BIGINT PRIMARY KEY,
    series_id        VARCHAR NOT NULL,
    observation_date DATE NOT NULL,
    vintage_date     DATE NOT NULL,
    value            DOUBLE,
    fetched_at       TIMESTAMPTZ NOT NULL
)
"""

SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id          BIGINT PRIMARY KEY,
    ticker      VARCHAR NOT NULL,
    run_date    DATE NOT NULL,
    signal_type VARCHAR NOT NULL,
    score       DOUBLE NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

RECOMMENDATIONS = """
CREATE TABLE IF NOT EXISTS recommendations (
    id              BIGINT PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    run_date        DATE NOT NULL,
    composite_score DOUBLE NOT NULL,
    rank            INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id            VARCHAR PRIMARY KEY,
    ticker        VARCHAR NOT NULL,
    instrument_id VARCHAR REFERENCES instruments(id),
    side          VARCHAR NOT NULL CHECK (side IN ('buy', 'sell')),
    qty           DOUBLE NOT NULL,
    order_type    VARCHAR NOT NULL DEFAULT 'market',
    status        VARCHAR NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id          VARCHAR PRIMARY KEY,
    order_id    VARCHAR REFERENCES orders(id),
    ticker      VARCHAR NOT NULL,
    side        VARCHAR NOT NULL,
    qty         DOUBLE NOT NULL,
    fill_price  DOUBLE NOT NULL,
    filled_at   TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

UNIVERSE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS universe_snapshots (
    id         BIGINT PRIMARY KEY,
    run_date   DATE NOT NULL,
    week_start DATE NOT NULL,
    ticker     VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

ALL_TABLES: list[str] = [
    SCHEMA_VERSIONS,
    INSTRUMENTS,
    RAW_PRICES,
    RAW_INSIDER,
    RAW_CONGRESSIONAL,
    RAW_MACRO,
    SIGNALS,
    RECOMMENDATIONS,
    ORDERS,
    TRADES,
    UNIVERSE_SNAPSHOTS,
]
