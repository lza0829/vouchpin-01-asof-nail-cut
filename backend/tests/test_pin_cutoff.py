"""钉扎时间截断（as-of 前缀）端到端核对，仅依赖项目自身代码与标准库。

运行：DATA_DIR 指向临时目录后 `python tests/test_pin_cutoff.py`
覆盖：全局互斥策略、as-of 预览/落批同源、批头与明细快照不可变、
晚到同日写入的硬拒/未钉旁路、服务端钉钟、旧库迁移语义。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime

# 测试自身位置：backend/tests/，把 backend 放进 sys.path 后即可 import app。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="vp-test-"))

from fastapi import HTTPException  # noqa: E402

from app.seed import seed_if_empty  # noqa: E402
from app.db import connect  # noqa: E402
from app.repositories import settings as settings_repo  # noqa: E402
from app.services import pin_policy  # noqa: E402
from app.services import event_service, redeem_service, settings_service  # noqa: E402

DAY = "2026-10-15"


class PinCutoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        seed_if_empty()
        settings_service.set_day({"business_day": DAY})

    def _redeem(self, code: str, ts: str, amount: float = 10) -> dict:
        return event_service.add_event({
            "event_type": "redeem",
            "coupon_code": code,
            "campaign_code": "NEW10",
            "amount": amount,
            "business_day": DAY,
            "occurred_at": ts,
        })

    def test_01_policy_is_global_mutex(self) -> None:
        pol = settings_service.get_pin_policy()
        self.assertEqual(pol["active_policy"], pin_policy.AS_OF_PREFIX)
        self.assertTrue(pol["mutually_exclusive"])
        with self.assertRaises(HTTPException) as cm:
            settings_service.set_pin_policy({"pin_cutoff_policy": pin_policy.FULL_DAY})
        self.assertEqual(cm.exception.status_code, 409)
        # 互斥对语义留档：full_day 下显式携带 as_of 必须明示拒绝。
        with self.assertRaises(HTTPException) as cm2:
            pin_policy.resolve_as_of(pin_policy.FULL_DAY, f"{DAY}T12:00:00")
        self.assertEqual(cm2.exception.status_code, 400)
        # 绕过 API 篡改落库值：钉扎入口强制 500，而非静默走另一套。
        conn = connect()
        try:
            settings_repo.set_(conn, pin_policy.SETTING_KEY, pin_policy.FULL_DAY)
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(HTTPException) as cm3:
            redeem_service.preview(DAY, f"{DAY}T12:00:00")
        self.assertEqual(cm3.exception.status_code, 500)
        conn = connect()
        try:
            settings_repo.set_(conn, pin_policy.SETTING_KEY, pin_policy.AS_OF_PREFIX)
            conn.commit()
        finally:
            conn.close()

    def test_02_preview_and_seal_share_one_cutoff_set(self) -> None:
        self._redeem("T-A1", f"{DAY}T10:00:00")
        self._redeem("T-A2", f"{DAY}T11:00:00")
        self._redeem("T-A3", f"{DAY}T12:00:00")
        cutoff = f"{DAY}T11:30:00"
        pv = redeem_service.preview(DAY, cutoff)
        self.assertEqual(pv["cutoff_policy"], pin_policy.AS_OF_PREFIX)
        self.assertEqual(pv["as_of"], cutoff)
        self.assertEqual([f["coupon_code"] for f in pv["facts"]], ["T-A1", "T-A2"])
        self.assertEqual(pv["open_count"], 2)
        self.assertEqual(pv["truncated_count"], 1)
        self.assertEqual([f["coupon_code"] for f in pv["truncated_facts"]], ["T-A3"])

        sealed = redeem_service.seal({"business_day": DAY, "as_of": cutoff, "note": "首批"})
        self.bid = sealed["batch_id"]
        self.assertEqual(sealed["fact_count"], 2)
        self.assertEqual(sealed["truncated_count"], 1)
        self.assertEqual(sealed["as_of"], cutoff)
        # 截断真实改变了落批集合，而非只改排序。
        self.assertLess(sealed["fact_count"], 3)

        detail = redeem_service.get_batch(self.bid)
        self.assertEqual(detail["cutoff_policy"], pin_policy.AS_OF_PREFIX)
        self.assertEqual([i["coupon_code"] for i in detail["items"]], ["T-A1", "T-A2"])
        self.assertTrue(all(i["occurred_at"] <= cutoff for i in detail["items"]))

    def test_03_reseal_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            redeem_service.seal({"business_day": DAY, "as_of": f"{DAY}T23:59:59"})
        self.assertEqual(cm.exception.status_code, 409)
        with self.assertRaises(HTTPException) as cm:
            redeem_service.seal({"business_day": DAY})
        self.assertEqual(cm.exception.status_code, 409)

    def test_04_late_same_day_writes_gate(self) -> None:
        # 晚于批 as_of：未钉旁路，事实保持 open、不挂批次、带批注。
        late = event_service.add_event({
            "event_type": "redeem", "coupon_code": "T-A4", "campaign_code": "NEW10",
            "amount": 10, "business_day": DAY, "occurred_at": f"{DAY}T14:00:00",
        })
        self.assertTrue(late["bypassed_seal"])
        conn = connect()
        try:
            note = conn.execute(
                "SELECT note FROM coupon_events WHERE coupon_code='T-A4' ORDER BY id DESC LIMIT 1"
            ).fetchone()["note"]
        finally:
            conn.close()
        self.assertIn("未钉旁路", note)
        # 落在 as_of 之内的晚到事件：硬拒，防止撬开已钉集合。
        with self.assertRaises(HTTPException) as cm:
            event_service.add_event({
                "event_type": "redeem", "coupon_code": "T-A5", "campaign_code": "NEW10",
                "amount": 10, "business_day": DAY, "occurred_at": f"{DAY}T10:30:00",
            })
        self.assertEqual(cm.exception.status_code, 409)

    def test_05_sealed_set_is_immutable(self) -> None:
        bid = redeem_service.list_batches()[0]["id"]
        before = redeem_service.get_batch(bid)
        # 再来一笔旁路事实，批快照不得变化。
        event_service.add_event({
            "event_type": "redeem", "coupon_code": "T-A6", "campaign_code": "NEW10",
            "amount": 10, "business_day": DAY, "occurred_at": f"{DAY}T15:00:00",
        })
        after = redeem_service.get_batch(bid)
        self.assertEqual(after["as_of"], before["as_of"])
        self.assertEqual(after["fact_count"], before["fact_count"])
        self.assertEqual(after["truncated_count"], before["truncated_count"])
        self.assertEqual(
            [i["coupon_code"] for i in after["items"]],
            [i["coupon_code"] for i in before["items"]],
        )
        facts = {f["coupon_code"]: f for f in redeem_service.list_facts(DAY)}
        self.assertEqual(facts["T-A1"]["status"], "sealed")
        self.assertEqual(facts["T-A1"]["batch_id"], bid)
        self.assertEqual(facts["T-A3"]["status"], "open")
        self.assertIsNone(facts["T-A3"]["batch_id"])
        self.assertEqual(facts["T-A4"]["status"], "open")
        self.assertIsNone(facts["T-A4"]["batch_id"])

    def test_06_server_pin_clock_on_missing_as_of(self) -> None:
        day2 = "2026-10-16"
        settings_service.set_day({"business_day": day2})
        event_service.add_event({
            "event_type": "redeem", "coupon_code": "T-B1", "campaign_code": "TEA5",
            "amount": 5, "business_day": day2, "occurred_at": f"{day2}T00:00:00",
        })
        sealed = redeem_service.seal({"business_day": day2})  # 不带 as_of -> 服务端钉钟
        self.assertEqual(sealed["cutoff_policy"], pin_policy.AS_OF_PREFIX)
        self.assertEqual(len(sealed["as_of"]), 19)
        detail = redeem_service.get_batch(sealed["batch_id"])
        self.assertEqual(detail["as_of"], sealed["as_of"])
        self.assertEqual([i["coupon_code"] for i in detail["items"]], ["T-B1"])
        settings_service.set_day({"business_day": DAY})

    def test_07_bad_as_of_rejected(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            pin_policy.resolve_as_of(pin_policy.AS_OF_PREFIX, "not-a-timestamp")
        self.assertEqual(cm.exception.status_code, 400)

    def test_08_server_clock_format(self) -> None:
        clock = pin_policy.server_pin_clock()
        datetime.strptime(clock, pin_policy.CLOCK_FMT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
