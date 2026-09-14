from __future__ import annotations

import json

import duckdb


def recommendation_rows(conn: duckdb.DuckDBPyConnection, run_id: str | None = None) -> list[dict]:
    if run_id is None:
        row = conn.execute(
            "SELECT id FROM strategy_runs WHERE status='completed' ORDER BY effective_session DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return []
        run_id = row[0]
    rows = conn.execute(
        """SELECT run_id,ticker,run_date,composite_score,rank,selected,explanation
           FROM recommendations WHERE run_id=? ORDER BY rank""", [run_id]
    ).fetchall()
    return [{
        "run_id": row[0], "ticker": row[1], "run_date": row[2].isoformat(),
        "composite_score": row[3], "rank": row[4], "selected": row[5],
        "explanation": json.loads(row[6]),
    } for row in rows]
