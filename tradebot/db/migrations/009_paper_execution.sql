CREATE TABLE broker_order_intents (
    id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL REFERENCES shadow_accounts(id),
    shadow_order_id VARCHAR NOT NULL REFERENCES shadow_orders(id),
    client_order_id VARCHAR NOT NULL UNIQUE,
    status VARCHAR NOT NULL CHECK (status IN ('awaiting_approval','submitted','filled','rejected','canceled')),
    approved_at TIMESTAMPTZ,
    broker_order_id VARCHAR,
    reconciled_at TIMESTAMPTZ,
    reconciliation_counted BOOLEAN NOT NULL DEFAULT false,
    diagnostics JSON NOT NULL DEFAULT '{}',
    UNIQUE (shadow_order_id)
);

CREATE TABLE broker_order_events (
    id VARCHAR PRIMARY KEY,
    intent_id VARCHAR NOT NULL REFERENCES broker_order_intents(id),
    broker_status VARCHAR NOT NULL,
    filled_quantity DOUBLE NOT NULL,
    filled_average_price DOUBLE,
    observed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_execution_state (
    id BOOLEAN PRIMARY KEY DEFAULT true CHECK (id),
    endpoint VARCHAR NOT NULL,
    auto_enabled BOOLEAN NOT NULL DEFAULT false,
    kill_switch BOOLEAN NOT NULL DEFAULT false,
    reconciled_order_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL
);
