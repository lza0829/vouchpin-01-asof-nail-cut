from __future__ import annotations
from fastapi import APIRouter
from app.services import settings_service as svc

router = APIRouter(tags=["settings"])


@router.get("/settings/day")
def get_day():
    return svc.get_day()


@router.put("/settings/day")
def put_day(body: dict):
    return svc.set_day(body)


@router.get("/settings/pin-policy")
def get_pin_policy():
    return svc.get_pin_policy()


@router.put("/settings/pin-policy")
def put_pin_policy(body: dict):
    return svc.set_pin_policy(body)
