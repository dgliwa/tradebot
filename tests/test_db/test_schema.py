def test_schema_layers_separate(db):
    names = {r[0] for r in db.execute('SHOW TABLES').fetchall()}
    assert {'raw_prices', 'raw_insider', 'raw_congressional', 'raw_macro', 'signals',
            'recommendations', 'orders', 'trades', 'universe_snapshots'} <= names


def test_instruments_options_aware(db):
    db.execute("INSERT INTO instruments VALUES ('AAPL', 'AAPL', 'stock', NULL, NULL, now())")
    db.execute("INSERT INTO instruments VALUES ('option', 'AAPL', 'call', '2026-12-18', 200, now())")
    assert db.execute("SELECT strike FROM instruments WHERE id='option'").fetchone() == (200,)


def test_disclosure_dates_separate(db):
    db.execute("""INSERT INTO raw_insider (id,ticker,transaction_date,filed_at,transaction_code,fetched_at)
                  VALUES ('a','AAPL','2026-07-01','2026-07-06','P',now())""")
    transaction_date, filed_at = db.execute('SELECT transaction_date,filed_at FROM raw_insider').fetchone()
    assert transaction_date < filed_at


def test_universe_snapshots_queryable(db):
    db.execute("""INSERT INTO universe_snapshots (id,run_date,week_start,ticker,created_at)
                  VALUES (1,'2026-07-06','2026-07-06','AAPL',now())""")
    assert db.execute("SELECT ticker FROM universe_snapshots WHERE week_start='2026-07-06'").fetchall() == [('AAPL',)]
