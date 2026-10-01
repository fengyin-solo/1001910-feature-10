<template>
  <section class="page" data-module="generator">
    <header class="page-head">
      <div>
        <h2>发电机管理</h2>
        <p class="page-desc">勾选多台发电机后一次提交检测结论：可整批判定合格，也能整批退回复检，提交后逐台给出结果。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记发电机</button>
        <button class="btn" type="button" @click="exportRows">导出发电机清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <label class="batch-select-all">
        <input
          type="checkbox"
          :checked="allVisibleSelected"
          :indeterminate.prop="someVisibleSelected"
          @change="toggleAllVisible"
        />
        全选本页
      </label>
      <span class="batch-count">已勾选 {{ selectedIds.size }} 台</span>
      <button
        class="btn primary"
        type="button"
        :disabled="!selectedIds.size || submitting"
        @click="submitBatch('合格')"
      >
        整批判定合格
      </button>
      <button
        class="btn"
        type="button"
        :disabled="!selectedIds.size || submitting"
        @click="submitBatch('退回复检')"
      >
        整批退回复检
      </button>
      <span v-if="batchMessage" class="batch-summary" :class="{ 'is-error': !batchOk }">{{ batchMessage }}</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="col-check">勾选</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="col-check">
            <input
              type="checkbox"
              :value="Number(row.id)"
              v-model="selected"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无发电机数据，可先登记发电机</td>
        </tr>
      </tbody>
    </table>

    <div v-if="batchResults.length" class="batch-result-panel">
      <h3>逐台结果（{{ batchConclusion }}）</h3>
      <ul>
        <li v-for="item in batchResults" :key="item.id" :class="item.ok ? 'result-ok' : 'result-fail'">
          <span class="result-name">{{ item.name ?? `#${item.id}` }}</span>
          <span class="result-mark">{{ item.ok ? '生效' : '拦截' }}</span>
          <span class="result-message">{{ item.message }}</span>
        </li>
      </ul>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条发电机记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BatchItem = {
  id: number
  name: string | null
  ok: boolean
  message: string
  entry: Row | null
}

const ENDPOINT = '/api/generator'
const columns = ["发电机编号", "所属机组", "额定电压", "绝缘电阻", "轴承温度", "上次检测日", "检测结论", "发电机状态"]
const actions = ["提交检测", "判定绝缘异常", "更换发电机"]

const stats = ref<{ label: string; value: number }[]>([
  { label: '待检测发电机', value: 0 },
  { label: '检测合格台数', value: 0 },
  { label: '绝缘偏低台数', value: 0 },
  { label: '已更换台数', value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selected = ref<number[]>([])
const submitting = ref(false)
const batchMessage = ref('')
const batchOk = ref(true)
const batchResults = ref<BatchItem[]>([])
const batchConclusion = ref('')

const selectedIds = computed(() => new Set(selected.value))
const allVisibleSelected = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.has(Number(row.id))),
)
const someVisibleSelected = computed(
  () => !allVisibleSelected.value && rows.value.some((row) => selectedIds.value.has(Number(row.id))),
)

function toggleAllVisible(event: Event): void {
  const checked = (event.target as HTMLInputElement).checked
  const visibleIds = rows.value.map((row) => Number(row.id))
  if (checked) {
    selected.value = Array.from(new Set([...selected.value, ...visibleIds]))
  } else {
    const visible = new Set(visibleIds)
    selected.value = selected.value.filter((id) => !visible.has(id))
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '发电机登记入口尚未接入审批流'
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const data = (await response.json()) as Record<string, number>
    stats.value = [
      { label: '待检测发电机', value: data.pending ?? 0 },
      { label: '检测合格台数', value: data.qualified ?? 0 },
      { label: '绝缘偏低台数', value: data.abnormal ?? 0 },
      { label: '已更换台数', value: data.replaced ?? 0 },
    ]
  } catch {
    // 统计卡片保持上一次的值，不影响列表操作
  }
}

async function submitBatch(conclusion: string) {
  if (!selected.value.length || submitting.value) return
  errorMessage.value = ''
  batchMessage.value = ''
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/batch-inspection`, {
      method: 'POST',
      body: JSON.stringify({ ids: Array.from(new Set(selected.value)), conclusion }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload) {
      throw new Error(payload?.detail ?? '批量提交未生效，请稍后重试')
    }
    batchOk.value = Boolean(payload.ok)
    batchMessage.value = payload.message
    batchResults.value = payload.results ?? []
    batchConclusion.value = payload.conclusion ?? conclusion
    // 全部生效或被拦截的项都从勾选里清掉，便于继续处理剩余项
    selected.value = []
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量提交失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('发电机动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电机操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('发电机列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 已翻页/筛选后，剔除不在当前列表里的勾选
    const visibleIds = new Set(rows.value.map((row: Row) => Number(row.id)))
    selected.value = selected.value.filter((id) => visibleIds.has(id))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电机列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.batch-select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.batch-count {
  font-size: 13px;
  color: var(--muted);
}
.batch-summary {
  font-size: 13px;
  color: #067647;
}
.batch-summary.is-error {
  color: #b42318;
}
.col-check {
  width: 44px;
  text-align: center;
}
.batch-result-panel {
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
}
.batch-result-panel h3 {
  margin: 0 0 8px;
  font-size: 14px;
}
.batch-result-panel ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.batch-result-panel li {
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.result-name {
  font-weight: 600;
  min-width: 96px;
}
.result-mark {
  border-radius: 4px;
  padding: 0 6px;
  font-size: 12px;
}
.result-ok .result-mark {
  background: #e7f6ee;
  color: #067647;
}
.result-fail .result-mark {
  background: #fdecec;
  color: #b42318;
}
.result-message {
  color: var(--muted);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
