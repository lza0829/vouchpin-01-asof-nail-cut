from __future__ import annotations
import sqlite3
from typing import Any


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM redeem_batches ORDER BY id DESC").fetchall()]


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM redeem_batches WHERE id=?", (batch_id,)).fetchone()
    return dict(row) if row else None


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    # 批头快照 as_of / 策略 / 纳入与截断笔数；sealed 后这些列不再被 UPDATE。
    cur = conn.execute(
        "INSERT INTO redeem_batches(business_day, status, fact_count, total_amount, sealed_at, "
        "as_of, cutoff_policy, truncated_count, note) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            fields["business_day"],
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            fields.get("sealed_at"),
            fields["as_of"],
            fields.get("cutoff_policy") or "as_of_prefix",
            int(fields.get("truncated_count") or 0),
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)
