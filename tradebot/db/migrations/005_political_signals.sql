CREATE TABLE source_coverage (
    id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL,
    checked_through DATE,
    checked_at TIMESTAMPTZ NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('valid', 'invalid')),
    errors JSON NOT NULL DEFAULT '[]',
    UNIQUE (source, ticker, checked_at)
);

CREATE TABLE congressional_imports (
    id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    coverage_through DATE NOT NULL,
    source_path VARCHAR,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    imported_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source, coverage_through)
);

ALTER TABLE raw_congressional ADD COLUMN owner VARCHAR;
ALTER TABLE raw_congressional ADD COLUMN asset_type VARCHAR DEFAULT 'stock';
ALTER TABLE raw_congressional ADD COLUMN option_type VARCHAR;
ALTER TABLE raw_congressional ADD COLUMN source VARCHAR DEFAULT 'manual_csv';
ALTER TABLE raw_congressional ADD COLUMN source_id VARCHAR;
ALTER TABLE raw_congressional ADD COLUMN raw_payload JSON;
ALTER TABLE raw_congressional ADD COLUMN import_id VARCHAR;

ALTER TABLE universe_snapshots ADD COLUMN run_id VARCHAR;
ALTER TABLE universe_snapshots ADD COLUMN reason JSON;
ALTER TABLE universe_snapshots ADD COLUMN source_filed_at DATE;

ALTER TABLE signals ADD COLUMN run_id VARCHAR;
ALTER TABLE signals ADD COLUMN raw_value DOUBLE;
ALTER TABLE signals ADD COLUMN details JSON DEFAULT '{}';

ALTER TABLE recommendations ADD COLUMN run_id VARCHAR;
ALTER TABLE recommendations ADD COLUMN selected BOOLEAN DEFAULT false;
ALTER TABLE recommendations ADD COLUMN explanation JSON DEFAULT '{}';
