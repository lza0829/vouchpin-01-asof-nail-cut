<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const day = ref('')
const policy = ref(null)
const target = ref('as_of_prefix')
const msg = ref('')
const err = ref('')
async function load() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.getDay()
    day.value = r.business_day
    policy.value = await api.getPinPolicy()
    target.value = policy.value.active_policy
  } catch (e) { err.value = e.message }
}
async function saveDay() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setDay(day.value)
    msg.value = `业务日已设为 ${r.business_day}`
  } catch (e) { err.value = e.message }
}
async function savePolicy() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setPinPolicy(target.value)
    msg.value = `截断策略已生效：${r.active_policy}`
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>业务日 <input v-model="day" placeholder="YYYY-MM-DD" /></label>
      <button type="button" @click="saveDay">保存</button>
    </div>
  </div>
  <div class="panel" v-if="policy">
    <p class="msg">
      钉扎时间截断为<strong>全局互斥</strong>，同一时刻只贯彻一种。当前生效：
      <strong class="tag ok">{{ policy.active_policy }}</strong>
      （as-of 前缀：钉扎必须带 as_of 或走服务端钉钟）。互斥对 full_day（全日标签）在本构建中禁止启用。
    </p>
    <div class="row">
      <label>截断策略
        <select v-model="target">
          <option value="as_of_prefix">as_of_prefix（as-of 前缀 · 生效）</option>
          <option value="full_day">full_day（全日标签 · 互斥禁用）</option>
        </select>
      </label>
      <button type="button" @click="savePolicy">尝试切换</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
