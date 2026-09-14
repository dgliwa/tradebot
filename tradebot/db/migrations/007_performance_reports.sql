CREATE TABLE benchmark_orders (
    id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    cash_ledger_id VARCHAR NOT NULL REFERENCES cash_ledger(id),
    ticker VARCHAR NOT NULL,
    amount DOUBLE NOT NULL CHECK (amount > 0),
    eligible_session DATE NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('pending','filled')),
    fill_price DOUBLE,
    quantity DOUBLE,
    UNIQUE (account_id, cash_ledger_id)
);

CREATE TABLE report_artifacts (
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    session DATE NOT NULL,
    strategy_config_hash VARCHAR NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (account_id, session, strategy_config_hash)
);

CREATE TABLE performance_snapshots (
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    session DATE NOT NULL,
    strategy_equity DOUBLE NOT NULL,
    benchmark_equity DOUBLE NOT NULL,
    net_cash_flow DOUBLE NOT NULL,
    strategy_index DOUBLE NOT NULL,
    benchmark_index DOUBLE NOT NULL,
    drawdown DOUBLE NOT NULL,
    gross_exposure DOUBLE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (account_id, session)
);
