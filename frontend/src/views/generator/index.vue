<template>
  <section class="page" data-module="generator">
    <header class="page-head">
      <div>
        <h2>发电机管理</h2>
        <p class="page-desc">维护发电机，围绕发电机编号、所属机组、额定电压、绝缘电阻做登记、筛选与状态流转；可勾选多台后一次提交检测结论。</p>
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
      <label class="select-all">
        <input type="checkbox" :checked="allOnPageSelected" @change="toggleSelectAll" />
        全选本页
      </label>
      <span class="batch-summary">已勾选 {{ selectedIds.length }} 台</span>
      <button class="btn primary" type="button" :disabled="!selectedIds.length || submitting" @click="submitBatch('合格')">
        整批判定合格
      </button>
      <button class="btn warn" type="button" :disabled="!selectedIds.length || submitting" @click="submitBatch('退回复检')">
        整批退回复检
      </button>
      <button v-if="selectedIds.length" class="btn ghost" type="button" :disabled="submitting" @click="selectedIds = []">
        清空勾选
      </button>
    </div>

    <div v-if="batchResult" class="batch-result" :class="{ partial: batchResult.failed_count }">
      <p class="batch-head">
        {{ batchResult.message }}
      </p>
      <ul v-if="batchResult.succeeded.length" class="result-list ok">
        <li v-for="item in batchResult.succeeded" :key="`ok-${item.id}`">✓ {{ item.message }}</li>
      </ul>
      <ul v-if="batchResult.failed.length" class="result-list blocked">
        <li v-for="item in batchResult.failed" :key="`fail-${item.id}`">✕ {{ item.message }}</li>
      </ul>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">勾选</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input type="checkbox" :value="Number(row.id)" v-model="selectedIds" />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] === '' || row[column] == null ? '—' : row[column] }}</td>
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
  code?: string | null
  message: string
  entry?: Row | null
}

type BatchResult = {
  ok: boolean
  message: string
  total: number
  succeeded_count: number
  failed_count: number
  succeeded: BatchItem[]
  failed: BatchItem[]
}

type Stats = {
  pending: number
  qualified: number
  abnormal: number
  month_checked: number
}

const ENDPOINT = '/api/generator'
const columns = ['发电机编号', '所属机组', '额定电压', '绝缘电阻', '轴承温度', '上次检测日', '检测结论', '发电机状态']
const actions = ['提交检测', '判定绝缘异常', '更换发电机']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selectedIds = ref<number[]>([])
const submitting = ref(false)
const batchResult = ref<BatchResult | null>(null)

const stats = ref([
  { label: '待检测发电机', value: 0 },
  { label: '合格数', value: 0 },
  { label: '绝缘偏低台数', value: 0 },
  { label: '本月检测数', value: 0 },
])

const allOnPageSelected = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.includes(Number(row.id))),
)

function toggleSelectAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const pageIds = rows.value.map((row) => Number(row.id))
  if (checked) {
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...pageIds]))
  } else {
    selectedIds.value = selectedIds.value.filter((id) => !pageIds.includes(id))
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

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('发电机动作未生效，请稍后重试')
    }
    const payload = await response.json()
    if (payload && payload.ok === false) {
      throw new Error(payload.message || '发电机动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电机操作失败'
  }
}

async function submitBatch(verdict: string) {
  if (!selectedIds.value.length) {
    errorMessage.value = '请先勾选需要提交结论的发电机'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  batchResult.value = null
  try {
    const response = await request(`${ENDPOINT}/batch-actions`, {
      method: 'POST',
      body: JSON.stringify({ ids: selectedIds.value, verdict }),
    })
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      throw new Error(detail?.detail || '批量提交失败，请稍后重试')
    }
    batchResult.value = (await response.json()) as BatchResult
    // 重复提交只留最新结论：勾选项重新拉取后再保留仍然有效（未被拦）的选择
    const failedIds = new Set(batchResult.value.failed.map((item) => item.id))
    selectedIds.value = selectedIds.value.filter((id) => failedIds.has(id))
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量提交失败'
  } finally {
    submitting.value = false
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as Stats
    stats.value = [
      { label: '待检测发电机', value: payload.pending ?? 0 },
      { label: '合格数', value: payload.qualified ?? 0 },
      { label: '绝缘偏低台数', value: payload.abnormal ?? 0 },
      { label: '本月检测数', value: payload.month_checked ?? 0 },
    ]
  } catch {
    // 统计读不出来时保留上一次的值，不阻断列表操作
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
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电机列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 12px;
}

.batch-summary {
  color: #475467;
  font-size: 13px;
}

.btn.warn {
  border-color: #b54708;
  color: #b54708;
  background: #fff;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.check-col {
  width: 40px;
  text-align: center;
}

.select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.batch-result {
  border: 1px solid var(--border);
  border-left: 4px solid var(--brand);
  border-radius: 6px;
  background: #fff;
  padding: 8px 12px;
  margin-bottom: 12px;
}

.batch-result.partial {
  border-left-color: #b54708;
}

.batch-head {
  margin: 0 0 6px;
  font-weight: 600;
  font-size: 13px;
}

.result-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 13px;
  line-height: 1.8;
}

.result-list.ok {
  color: #027a48;
}

.result-list.blocked {
  color: #b42318;
}
</style>
