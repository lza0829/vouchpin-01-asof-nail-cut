from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.services import pin_policy


def _resolve_day(conn, business_day: str | None) -> str:
    return business_day or settings_repo.get(conn, "business_day")


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = _resolve_day(conn, business_day)
        return fact_repo.list_facts(conn, day)
    finally:
        conn.close()


def _cutoff_set(conn, day: str, as_of: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """同源的截断集合：纳入前缀 + 被截断的同日 open，预览与落批共用。"""
    included = fact_repo.open_facts_as_of(conn, day, as_of)
    truncated = fact_repo.open_facts_after(conn, day, as_of)
    return included, truncated


def preview(business_day: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = _resolve_day(conn, business_day)
        policy = pin_policy.effective_policy(settings_repo.get(conn, pin_policy.SETTING_KEY))
        cutoff = pin_policy.resolve_as_of(policy, as_of)
        included, truncated = _cutoff_set(conn, day, cutoff)
        total = round(sum(float(f["amount"]) for f in included), 2)
        return {
            "business_day": day,
            "cutoff_policy": policy,
            "as_of": cutoff,
            "open_count": len(included),
            "open_total": total,
            "truncated_count": len(truncated),
            "truncated_facts": truncated,
            "already_sealed": fact_repo.day_is_sealed(conn, day),
            "facts": included,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        existing = fact_repo.sealed_batch_for_day(conn, day)
        if existing:
            raise HTTPException(
                409,
                f"业务日 {day} 已有 sealed 钉扎批 #{existing['id']}（as_of={existing['as_of']}），"
                "已钉集合不可改写；as_of 之后到达的同日核销只能走未钉旁路",
            )
        policy = pin_policy.effective_policy(settings_repo.get(conn, pin_policy.SETTING_KEY))
        # AS_OF_PREFIX：请求带 as_of，否则服务端钉钟；FULL_DAY 带 as_of 会在此被拒。
        cutoff = pin_policy.resolve_as_of(policy, body.get("as_of"))

        # 落批集合与预览同源：occurred_at <= as_of 且仍 open。
        included, truncated = _cutoff_set(conn, day, cutoff)
        if not included:
            raise HTTPException(
                400,
                f"as_of={cutoff} 之前无可钉扎的 open 核销事实"
                + (f"；另有 {len(truncated)} 笔同日事实晚于 as_of，不得进入本批" if truncated else ""),
            )
        total = round(sum(float(f["amount"]) for f in included), 2)
        sealed_at = datetime.now().replace(microsecond=0).isoformat()
        bid = batch_repo.create_batch(
            conn,
            business_day=day,
            status="sealed",
            fact_count=len(included),
            total_amount=total,
            sealed_at=sealed_at,
            as_of=cutoff,
            cutoff_policy=policy,
            truncated_count=len(truncated),
            note=body.get("note") or "",
        )
        # 明细快照：钉入瞬间的纳入集合，sealed 后与 fact 状态解耦，晚到事件改不动它。
        fact_repo.insert_batch_items(conn, bid, included)
        fact_repo.mark_batched(conn, [int(f["id"]) for f in included], bid)
        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "cutoff_policy": policy,
            "as_of": cutoff,
            "fact_count": len(included),
            "truncated_count": len(truncated),
            "total_amount": total,
            "status": "sealed",
        }
    finally:
        conn.close()


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return batch_repo.list_batches(conn)
    finally:
        conn.close()


def get_batch(batch_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, f"批次 {batch_id} 不存在")
        # 明细取自不可变快照表，而非回查 redeem_facts 的当前状态。
        batch["items"] = fact_repo.list_batch_items(conn, batch_id)
        return batch
    finally:
        conn.close()
