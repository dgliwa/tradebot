CREATE TABLE experiment_evaluations (
    id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    strategy_config_hash VARCHAR NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
