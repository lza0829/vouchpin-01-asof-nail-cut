<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref([])
const detail = ref({})
const err = ref('')
async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
async function toggle(id) {
  if (detail.value[id]) { delete detail.value[id]; return }
  try { detail.value = { ...detail.value, [id]: await api.batch(id) } } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead>
        <tr><th>批次</th><th>业务日</th><th>状态</th><th>截断策略</th><th>as_of 快照</th><th>纳入笔数</th><th>截断笔数</th><th>合计</th><th>钉扎时刻</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="b in rows" :key="b.id">
          <td>{{ b.id }}</td>
          <td>{{ b.business_day }}</td>
          <td><span class="tag ok">{{ b.status }}</span></td>
          <td>{{ b.cutoff_policy }}</td>
          <td>{{ b.as_of }}</td>
          <td>{{ b.fact_count }}</td>
          <td>{{ b.truncated_count }}</td>
          <td>{{ b.total_amount }}</td>
          <td>{{ b.sealed_at }}</td>
          <td><button type="button" class="ghost" @click="toggle(b.id)">{{ detail[b.id] ? '收起' : '明细' }}</button></td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="panel" v-for="b in rows" :key="'d'+b.id" v-show="detail[b.id]">
    <h3>批 #{{ b.id }} 明细快照（sealed 后不可变，晚到事件改不动）</h3>
    <table v-if="detail[b.id]">
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>occurred_at</th></tr></thead>
      <tbody>
        <tr v-for="i in detail[b.id].items" :key="i.id">
          <td>{{ i.fact_id }}</td>
          <td>{{ i.coupon_code }}</td>
          <td>{{ i.campaign_code }}</td>
          <td>{{ i.amount }}</td>
          <td>{{ i.occurred_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
