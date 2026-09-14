CREATE TABLE service_locks (
    name VARCHAR PRIMARY KEY,
    owner VARCHAR NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE service_runs (
    id VARCHAR PRIMARY KEY,
    owner VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR NOT NULL CHECK (status IN ('running','completed','failed')),
    strategy_run_id VARCHAR,
    diagnostics JSON NOT NULL DEFAULT '{}'
);
