from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import campaigns as camp_repo
from app.services import pin_policy


def list_campaigns() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return camp_repo.list_all(conn)
    finally:
        conn.close()


def list_events(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return event_repo.list_events(conn, day)
    finally:
        conn.close()


def add_event(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        et = body.get("event_type")
        if et not in {"issue", "redeem", "void"}:
            raise HTTPException(400, "event_type 须为 issue/redeem/void")
        code = (body.get("coupon_code") or "").strip()
        camp = (body.get("campaign_code") or "").strip()
        if not code or not camp:
            raise HTTPException(400, "coupon_code / campaign_code 必填")
        amount = float(body.get("amount") or 0)
        if et == "redeem" and amount <= 0:
            # default face value from campaign
            camps = {c["code"]: c for c in camp_repo.list_all(conn)}
            if camp in camps:
                amount = float(camps[camp]["face_value"])
        occurred = body.get("occurred_at") or datetime.now().replace(microsecond=0).isoformat()
        note = body.get("note") or ""

        # 日写闸 + as-of 前缀旁路（与钉扎截断同源：只认 sealed 批快照里的 as_of）。
        bypass = False
        sealed_batch = None
        if et == "redeem":
            sealed_batch = fact_repo.sealed_batch_for_day(conn, day)
            if sealed_batch:
                cutoff = sealed_batch["as_of"]
                if occurred <= cutoff:
                    # 晚到但落在钉钟之内：进批会改写已钉集合，硬拒。
                    raise HTTPException(
                        409,
                        f"业务日 {day} 已钉扎（批 #{sealed_batch['id']}，as_of={cutoff}）："
                        f"occurred_at={occurred} 不晚于 as_of，禁止写入；"
                        "已 sealed 批的 as_of/集合不得被事后到达事件改写",
                    )
                # 同日但 occurred_at 晚于 as_of：允许走未钉旁路，事实保持 open、不挂批次。
                bypass = True
                tag = f"[未钉旁路: 晚于批#{sealed_batch['id']} as_of={cutoff}]"
                note = f"{note} {tag}".strip()

        eid = event_repo.insert_event(
            conn,
            event_type=et,
            coupon_code=code,
            campaign_code=camp,
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=note,
        )
        fact_id = None
        if et == "redeem":
            try:
                # 旁路事实不写 batch_id、状态保持 open，天然不进任何已 sealed 批的快照。
                fact_id = fact_repo.insert_fact(
                    conn,
                    coupon_code=code,
                    campaign_code=camp,
                    amount=amount,
                    business_day=day,
                    event_id=eid,
                    occurred_at=occurred,
                    status="open",
                )
            except Exception as e:
                raise HTTPException(409, f"核销事实写入失败（可能券码已核销）: {e}") from e
        conn.commit()
        return {
            "event_id": eid,
            "fact_id": fact_id,
            "business_day": day,
            "bypassed_seal": bypass,
            "sealed_batch_id": sealed_batch["id"] if sealed_batch else None,
        }
    finally:
        conn.close()
