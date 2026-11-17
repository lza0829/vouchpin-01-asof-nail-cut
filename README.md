# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销事实钉扎 → 过期/退回窗（后挖）→ 批次互证。

本地：
- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）
- 核对测试：`cd backend && DATA_DIR=$(mktemp -d) python tests/test_pin_cutoff.py`

## 钉扎时间截断：全局互斥，只贯彻 as-of 前缀

同一业务日的核销事件按 `occurred_at` 陆续入湖，钉扎取「全日标签集合」还是
「截到某一 as-of 的前缀」会算出不同的批笔数，且晚到同日事件会撬开已钉集合。
本系统把截断收成全局互斥的单一策略，截断配置、预览集合、批头/明细、晚到写入同源：

- 生效策略固定为 `as_of_prefix`（设置项 `pin_cutoff_policy`）；互斥对
  `full_day`（全日标签）经 `PUT /api/settings/pin-policy` 切换会被 409 拒绝，
  即使绕过 API 篡改落库值，钉扎入口也以 500 强制失败，绝不静默走另一套。
- 钉扎请求必须带 `as_of`；缺省由服务端钉钟（事务开始时刻，秒精度）补齐。
- 只纳入 `occurred_at <= as_of` 且仍 `open` 的核销事实；预览与落批共用同一查询
  （`facts.open_facts_as_of`），所见即所钉，截断改变的是落批集合而非列表排序。
- 批头快照 `as_of`、`cutoff_policy`、纳入笔数 `fact_count` 与截断笔数
  `truncated_count`；纳入集合另写入不可变明细表 `redeem_batch_items`，
  sealed 后与事实当前状态解耦，晚到事件无法改写。
- 日写闸：业务日已 sealed 后，`occurred_at <= 批 as_of` 的晚到核销一律 409 硬拒；
  仅 `occurred_at > 批 as_of` 的同日新事实允许写入，保持 `open`、不挂批次，
  走「未钉旁路」并在事件批注中标注批号与 as_of。
- 已 sealed 批的 `as_of` 与集合不接受二次钉扎（409），只能由后续新批次另行处理
  未钉旁路事实。
