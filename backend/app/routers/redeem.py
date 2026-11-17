from __future__ import annotations
from fastapi import APIRouter, Query
from app.services import redeem_service as svc

router = APIRouter(tags=["redeem"])


@router.get("/facts")
def facts(business_day: str | None = Query(None)):
    return svc.list_facts(business_day)


@router.get("/redeem/preview")
def preview(
    business_day: str | None = Query(None),
    as_of: str | None = Query(None, description="as-of 钉钟；缺省由服务端钉钟补齐"),
):
    return svc.preview(business_day, as_of)


@router.post("/redeem/seal")
def seal(body: dict):
    return svc.seal(body)


@router.get("/batches")
def batches():
    return svc.list_batches()


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: int):
    return svc.get_batch(batch_id)
