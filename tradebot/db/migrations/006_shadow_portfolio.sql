ALTER TABLE recommendations ADD COLUMN entry_signal BOOLEAN DEFAULT false;
ALTER TABLE recommendations ADD COLUMN entry_reason VARCHAR;

CREATE TABLE shadow_accounts (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    strategy_version VARCHAR NOT NULL,
    strategy_config_hash VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cash_ledger (
    id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    occurred_at TIMESTAMPTZ NOT NULL,
    amount DOUBLE NOT NULL,
    entry_type VARCHAR NOT NULL CHECK (entry_type IN ('initial','contribution','trade','dividend','commission')),
    reference_id VARCHAR NOT NULL,
    UNIQUE (account_id, entry_type, reference_id)
);

CREATE TABLE shadow_orders (
    id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    run_id VARCHAR,
    recommendation_id BIGINT,
    ticker VARCHAR NOT NULL,
    side VARCHAR NOT NULL CHECK (side IN ('buy','sell')),
    quantity DOUBLE NOT NULL CHECK (quantity > 0),
    status VARCHAR NOT NULL CHECK (status IN ('pending','filled','rejected','canceled')),
    reason VARCHAR NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL,
    eligible_session DATE NOT NULL,
    stop_price DOUBLE,
    diagnostics JSON NOT NULL DEFAULT '{}'
);

CREATE TABLE shadow_fills (
    id VARCHAR PRIMARY KEY,
    order_id VARCHAR NOT NULL REFERENCES shadow_orders(id),
    ticker VARCHAR NOT NULL,
    side VARCHAR NOT NULL CHECK (side IN ('buy','sell')),
    quantity DOUBLE NOT NULL CHECK (quantity > 0),
    price DOUBLE NOT NULL CHECK (price > 0),
    commission DOUBLE NOT NULL CHECK (commission >= 0),
    filled_at TIMESTAMPTZ NOT NULL,
    UNIQUE (order_id)
);

CREATE TABLE reentry_cooldowns (
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    ticker VARCHAR NOT NULL,
    until_session DATE NOT NULL,
    reason VARCHAR NOT NULL,
    PRIMARY KEY (account_id, ticker)
);

CREATE TABLE corporate_actions (
    id VARCHAR PRIMARY KEY,
    ticker VARCHAR NOT NULL,
    action_date DATE NOT NULL,
    action_type VARCHAR NOT NULL CHECK (action_type IN ('dividend','split')),
    value DOUBLE NOT NULL CHECK (value > 0),
    source VARCHAR NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE applied_corporate_actions (
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    action_id VARCHAR NOT NULL REFERENCES corporate_actions(id),
    applied_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (account_id, action_id)
);
