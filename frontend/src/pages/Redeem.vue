<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const preview = ref(null)
const asOf = ref('')
const msg = ref('')
const err = ref('')

function localNowInput() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

async function load() {
  err.value = ''
  try {
    // 留空时由服务端钉钟补齐；带值即按该 as_of 做前缀截断。
    preview.value = await api.preview(undefined, asOf.value || undefined)
    if (!asOf.value) asOf.value = preview.value.as_of
  } catch (e) { err.value = e.message }
}
async function seal() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.seal({ as_of: asOf.value || undefined })
    msg.value = `已钉扎批次 #${r.batch_id} · as_of=${r.as_of} · 纳入 ${r.fact_count} 笔 · 截断 ${r.truncated_count} 笔 · 合计 ${r.total_amount}`
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(() => { asOf.value = localNowInput(); load() })
</script>
<template>
  <div class="panel" v-if="preview">
    <p class="msg">全局截断策略（互斥）：<strong>{{ preview.cutoff_policy }}</strong> —— 只纳入 occurred_at ≤ as_of 且仍 open 的核销事实，晚到同日事件不进本批。</p>
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ preview.business_day }}</div></div>
      <div class="stat"><div class="k">as_of 钉钟</div><div class="v ticket">{{ preview.as_of }}</div></div>
      <div class="stat"><div class="k">纳入前缀笔数</div><div class="v ticket">{{ preview.open_count }}</div></div>
      <div class="stat"><div class="k">截断笔数（同日晚于 as_of）</div><div class="v">{{ preview.truncated_count }}</div></div>
      <div class="stat"><div class="k">纳入合计</div><div class="v ticket">{{ preview.open_total }}</div></div>
      <div class="stat"><div class="k">已钉扎</div><div class="v">{{ preview.already_sealed ? '是' : '否' }}</div></div>
    </div>
    <div class="row">
      <label>as_of
        <input v-model="asOf" type="datetime-local" step="1" />
      </label>
      <button type="button" @click="seal" :disabled="preview.already_sealed || preview.open_count===0">按 as_of 前缀钉扎</button>
      <button type="button" class="ghost" @click="load">按 as_of 刷新预览</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
  <div class="panel">
    <h3>纳入集合（occurred_at ≤ as_of · open · 钉扎即快照）</h3>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>occurred_at</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in (preview?.facts || [])" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td>{{ f.occurred_at }}</td>
          <td><span class="tag warn">{{ f.status }}</span></td>
        </tr>
        <tr v-if="preview && preview.facts.length===0"><td colspan="6" class="msg">as_of 之前无 open 事实（调整 as_of 可放宽前缀）</td></tr>
      </tbody>
    </table>
  </div>
  <div class="panel">
    <h3>截断集合（同日 open · occurred_at &gt; as_of · 不得进入本批）</h3>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>occurred_at</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in (preview?.truncated_facts || [])" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td>{{ f.occurred_at }}</td>
          <td><span class="tag">{{ f.status }}</span></td>
        </tr>
        <tr v-if="preview && preview.truncated_facts.length===0"><td colspan="6" class="msg">无截断事实</td></tr>
      </tbody>
    </table>
  </div>
</template>
