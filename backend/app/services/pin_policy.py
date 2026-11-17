"""钉扎时间截断策略：全局互斥，只贯彻一种。

本系统固定采用 AS_OF_PREFIX（as-of 前缀）策略，FULL_DAY（全日标签）
作为互斥对被显式拒绝，二者不允许在不同入口各走一套。

所有截断语义的唯一来源集中在本模块：
- 预览集合（redeem_service.preview）
- 落批集合与批头快照（redeem_service.seal）
- 晚到同日写闸（event_service.add_event）
都必须经这里的函数取策略/取集合，禁止在别处另写一份 WHERE 条件。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

# 互斥策略对。当前只允许 AS_OF_PREFIX 生效。
AS_OF_PREFIX = "as_of_prefix"
FULL_DAY = "full_day"
SUPPORTED_POLICIES = (AS_OF_PREFIX, FULL_DAY)

# settings 表中的全局开关 key；同一时刻只能有一个值。
SETTING_KEY = "pin_cutoff_policy"
ACTIVE_POLICY = AS_OF_PREFIX

# 服务端钉钟使用的时刻精度（秒），与 occurred_at 的落库格式对齐。
CLOCK_FMT = "%Y-%m-%dT%H:%M:%S"


def effective_policy(stored: str | None) -> str:
    """返回当前生效策略；本构建只贯彻 AS_OF_PREFIX，任何其他落库值都视为配置违约。"""
    if stored and stored not in SUPPORTED_POLICIES:
        raise HTTPException(500, f"未知钉扎截断策略: {stored}")
    if stored == FULL_DAY:
        raise HTTPException(
            500,
            "settings.pin_cutoff_policy=full_day 不被本构建支持（全局互斥，只贯彻 as_of_prefix）；"
            "请通过 /api/settings/pin-policy 改回 as_of_prefix",
        )
    return stored or ACTIVE_POLICY


def server_pin_clock() -> str:
    """服务端钉钟：请求未带 as_of 时使用，等价于钉扎事务开始时刻。"""
    return datetime.now().replace(microsecond=0).strftime(CLOCK_FMT)


def resolve_as_of(policy: str, raw_as_of: Any) -> str:
    """按互斥策略解析钉扎请求里的 as_of。

    AS_OF_PREFIX：必须带 as_of，缺省走服务端钉钟；带了全日标签语义不适用的
    参数不会被静默吞掉——这里 as_of 是该策略的合法参数，仅做格式校验。
    FULL_DAY：忽略 as_of；若请求显式携带 as_of，按互斥规则拒绝（400），
    避免调用方误以为截断生效。
    """
    if policy == FULL_DAY:
        if raw_as_of not in (None, ""):
            raise HTTPException(
                400,
                "当前钉扎截断策略为 full_day（全日标签）：按 business_day 收全量 open 事实，"
                "as_of 不被接受；如需 as-of 前缀截断，请先切换全局 pin_cutoff_policy",
            )
        return ""
    # AS_OF_PREFIX
    if raw_as_of in (None, ""):
        return server_pin_clock()
    text = str(raw_as_of).strip()
    try:
        # 兼容 "YYYY-MM-DDTHH:MM:SS" 与带时区/毫秒的 ISO 串，统一截到秒。
        return datetime.fromisoformat(text).replace(microsecond=0).strftime(CLOCK_FMT)
    except ValueError as exc:
        raise HTTPException(400, f"as_of 须为 ISO 8601 时刻（如 2026-11-18T15:00:00）: {text}") from exc


def validate_cutoff_change(target: str) -> str:
    """全局策略切换的互斥校验。当前构建只放行 AS_OF_PREFIX。"""
    value = (target or "").strip()
    if value not in SUPPORTED_POLICIES:
        raise HTTPException(400, f"pin_cutoff_policy 须为 {SUPPORTED_POLICIES} 之一")
    if value != ACTIVE_POLICY:
        raise HTTPException(
            409,
            "本构建只贯彻 as_of_prefix 单一策略；full_day 为互斥对，禁止启用"
            "（全日标签会让晚到同日事件撬开已钉集合）",
        )
    return value
