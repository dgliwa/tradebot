CREATE TABLE strategy_runs (
    id VARCHAR PRIMARY KEY,
    strategy_name VARCHAR NOT NULL,
    strategy_version VARCHAR NOT NULL,
    config_hash VARCHAR NOT NULL,
    config_json JSON NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    effective_session DATE NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('started', 'completed', 'failed')),
    diagnostics JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (strategy_name, strategy_version, effective_session)
);
