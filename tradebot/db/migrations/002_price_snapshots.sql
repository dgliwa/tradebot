ALTER TABLE raw_prices RENAME TO legacy_raw_prices;

CREATE TABLE price_snapshots (
    id VARCHAR PRIMARY KEY,
    ticker VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    content_hash VARCHAR NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count > 0),
    UNIQUE (ticker, source, fetched_at)
);

CREATE TABLE raw_prices (
    snapshot_id VARCHAR NOT NULL REFERENCES price_snapshots(id),
    date DATE NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume BIGINT NOT NULL CHECK (volume >= 0),
    PRIMARY KEY (snapshot_id, date)
);

CREATE VIEW latest_prices AS
WITH latest AS (
    SELECT *, row_number() OVER (
        PARTITION BY ticker, source ORDER BY fetched_at DESC, id DESC
    ) AS rank
    FROM price_snapshots
)
SELECT s.id AS snapshot_id, s.ticker, p.date, p.open, p.high, p.low, p.close,
       p.volume, s.fetched_at, s.source
FROM latest s JOIN raw_prices p ON p.snapshot_id = s.id
WHERE s.rank = 1;

ALTER TABLE raw_insider ADD COLUMN raw_xml VARCHAR;
ALTER TABLE raw_insider ADD COLUMN document_url VARCHAR;

CREATE TABLE database_metadata (
    key VARCHAR PRIMARY KEY,
    value VARCHAR NOT NULL
);
