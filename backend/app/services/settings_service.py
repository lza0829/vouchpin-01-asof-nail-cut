from __future__ import annotations
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.services import pin_policy


def get_day() -> dict[str, Any]:
    conn = connect()
    try:
        return {"business_day": settings_repo.get(conn, "business_day")}
    finally:
        conn.close()


def set_day(body: dict[str, Any]) -> dict[str, Any]:
    day = (body.get("business_day") or "").strip()
    if len(day) != 10:
        raise HTTPException(400, "business_day 格式 YYYY-MM-DD")
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, "business_day", day)
        conn.commit()
        return {"business_day": day}
    finally:
        conn.close()


def get_pin_policy() -> dict[str, Any]:
    conn = connect()
    try:
        stored = settings_repo.get(conn, pin_policy.SETTING_KEY)
        return {
            "key": pin_policy.SETTING_KEY,
            # 展示用原始落库值；实际钉扎入口由 pin_policy.effective_policy 强制互斥。
            "stored_policy": stored or pin_policy.ACTIVE_POLICY,
            "active_policy": pin_policy.ACTIVE_POLICY,
            "enforced": pin_policy.ACTIVE_POLICY,
            "supported": list(pin_policy.SUPPORTED_POLICIES),
            "mutually_exclusive": True,
            "violation": bool(stored) and stored != pin_policy.ACTIVE_POLICY,
        }
    finally:
        conn.close()


def set_pin_policy(body: dict[str, Any]) -> dict[str, Any]:
    target = pin_policy.validate_cutoff_change(str(body.get("pin_cutoff_policy") or ""))
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, pin_policy.SETTING_KEY, target)
        conn.commit()
        return {"key": pin_policy.SETTING_KEY, "active_policy": target}
    finally:
        conn.close()
