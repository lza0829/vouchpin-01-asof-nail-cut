from __future__ import annotations
import sqlite3
from typing import Any


def list_facts(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM redeem_facts WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM redeem_facts ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def insert_fact(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, occurred_at, status) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            int(fields["event_id"]),
            fields.get("occurred_at") or "",
            fields.get("status") or "open",
        ),
    )
    return int(cur.lastrowid)


def open_facts_for_day(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    """全日 open 集合（不含截断），仅用于计数/对照，禁止直接用于落批。"""
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE business_day=? AND status='open' ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def open_facts_as_of(conn: sqlite3.Connection, business_day: str, as_of: str) -> list[dict[str, Any]]:
    """as-of 前缀集合：同一 business_day 下仍 open 且 occurred_at <= as_of 的事实。

    预览与钉扎落批必须共用本函数，保证「所见即所钉」。
    字符串比较对统一格式（YYYY-MM-DDTHH:MM:SS）的 ISO 时刻与字典序一致。
    """
    rows = conn.execute(
        "SELECT * FROM redeem_facts "
        "WHERE business_day=? AND status='open' AND occurred_at<>'' AND occurred_at<=? "
        "ORDER BY occurred_at, id",
        (business_day, as_of),
    ).fetchall()
    return [dict(r) for r in rows]


def open_facts_after(conn: sqlite3.Connection, business_day: str, as_of: str) -> list[dict[str, Any]]:
    """被 as_of 截断在外的同日 open 事实（晚到/晚发生），用于批头 truncated_count 与预览提示。"""
    rows = conn.execute(
        "SELECT * FROM redeem_facts "
        "WHERE business_day=? AND status='open' AND occurred_at>? "
        "ORDER BY occurred_at, id",
        (business_day, as_of),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_batched(conn: sqlite3.Connection, fact_ids: list[int], batch_id: int) -> None:
    for fid in fact_ids:
        conn.execute(
            "UPDATE redeem_facts SET status='sealed', batch_id=? WHERE id=? AND status='open'",
            (batch_id, fid),
        )


def day_is_sealed(conn: sqlite3.Connection, business_day: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM redeem_batches WHERE business_day=? AND status='sealed' LIMIT 1",
        (business_day,),
    ).fetchone()
    return row is not None


def sealed_batch_for_day(conn: sqlite3.Connection, business_day: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM redeem_batches WHERE business_day=? AND status='sealed' LIMIT 1",
        (business_day,),
    ).fetchone()
    return dict(row) if row else None


def insert_batch_items(conn: sqlite3.Connection, batch_id: int, facts: list[dict[str, Any]]) -> None:
    conn.executemany(
        "INSERT INTO redeem_batch_items(batch_id, fact_id, coupon_code, campaign_code, amount, business_day, occurred_at) "
        "VALUES(?,?,?,?,?,?,?)",
        [
            (
                batch_id,
                int(f["id"]),
                f["coupon_code"],
                f["campaign_code"],
                float(f["amount"]),
                f["business_day"],
                f.get("occurred_at") or "",
            )
            for f in facts
        ],
    )


def list_batch_items(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_batch_items WHERE batch_id=? ORDER BY occurred_at, fact_id",
        (batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]
