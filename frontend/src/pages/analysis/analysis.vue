<template>
  <scroll-view class="page" scroll-y>
    <view class="section">
      <text class="section-title">盈亏趋势</text>
      <ChartProfit :series="statStore.trendSeries" />
    </view>

    <view class="section">
      <text class="section-title">玩法盈亏占比</text>
      <ChartPie :dataset="statStore.pieDataset" />
    </view>

    <view class="section">
      <text class="section-title">周度盈亏</text>
      <view v-if="!weekList.length" class="empty">暂无数据</view>
      <view v-else class="weekly">
        <view v-for="row in weekList" :key="row.week" class="weekly-row">
          <view class="week">{{ row.week }}</view>
          <view class="meta">投入 {{ formatCurrency(row.stake) }}</view>
          <view class="meta" :class="{ win: row.profit >= 0, lose: row.profit < 0 }">
            盈亏 {{ formatCurrency(row.profit) }}
          </view>
        </view>
      </view>
    </view>

    <!-- 预测准确率 -->
    <view class="section">
      <text class="section-title">预测准确率</text>
      <view v-if="!accuracy.total" class="empty">暂无已结算的预测记录</view>
      <block v-else>
        <view class="stat-row">
          <StatCard title="总预测" :value="String(accuracy.total)" :subtitle="`命中 ${accuracy.hit} · 未中 ${accuracy.miss}`" />
          <StatCard title="命中率" :value="hitRateText" :subtitle="`走水 ${accuracy.push}场`" :positive="hitRatePositive" />
        </view>
        <view class="sub-title">按置信度区间</view>
        <ChartAccuracy :bands="accuracy.byConfidence" />
        <view class="sub-title">各因子准确率</view>
        <view class="factor-list">
          <view
            v-for="f in sortedFactors"
            :key="f.name"
            class="factor-row"
          >
            <text class="factor-name">{{ f.name }}</text>
            <view class="factor-bar-wrap">
              <view class="factor-bar" :style="{ width: factorPct(f) + '%', background: factorColor(f) }"></view>
            </view>
            <text class="factor-pct" :style="{ color: factorColor(f) }">{{ factorPct(f) }}%</text>
            <text class="factor-sample">{{ f.hit }}/{{ f.total }}</text>
          </view>
        </view>
      </block>
    </view>

    <!-- 信心档命中率(复盘主观信心) -->
    <view class="section">
      <text class="section-title">信心档命中率</text>
      <view v-if="tierTotal === 0" class="empty">暂无已结算的信心档记录</view>
      <view v-else class="factor-list">
        <view v-for="t in tierRows" :key="t.key" class="factor-row">
          <text class="factor-name">{{ t.label }}</text>
          <view class="factor-bar-wrap">
            <view class="factor-bar" :style="{ width: t.pct + '%', background: t.color }"></view>
          </view>
          <text class="factor-pct" :style="{ color: t.color }">{{ t.pct }}%</text>
          <text class="factor-sample">{{ t.hit }}/{{ t.total }}</text>
        </view>
      </view>
      <text class="field-hint">对比你主观选的信心档与实际命中率,检验主观信心是否准确</text>
    </view>
  </scroll-view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import ChartPie from '@/components/ChartPie.vue'
import ChartProfit from '@/components/ChartProfit.vue'
import ChartAccuracy from '@/components/ChartAccuracy.vue'
import StatCard from '@/components/StatCard.vue'
import { useStatStore } from '@/stores/statStore'
import { formatCurrency } from '@/utils/formatters'
import { requireAuth } from '@/utils/auth'
import { request } from '@/utils/http'

const statStore = useStatStore()
const accuracy = ref({ total: 0, hit: 0, miss: 0, push: 0, byConfidence: [], byFactor: [] })

onShow(() => {
  // 检查登录状态
  if (!requireAuth()) {
    return
  }
  fetchAccuracy()
})

async function fetchAccuracy() {
  try {
    const data = await request({ url: '/api/review-stats?days=30', method: 'GET' })
    accuracy.value = data || { total: 0, hit: 0, miss: 0, push: 0, byConfidence: [], byFactor: [] }
  } catch (e) {
    // 静默失败，预测准确率为可选模块
  }
}

const hitRateText = computed(() => {
  if (accuracy.value.hitRate == null) return '--'
  return Math.round(accuracy.value.hitRate * 100) + '%'
})

const hitRatePositive = computed(() => (accuracy.value.hitRate || 0) >= 0.5)

const sortedFactors = computed(() => {
  return [...(accuracy.value.byFactor || [])]
    .filter((f) => f.total > 0)
    .sort((a, b) => (b.hitRate || 0) - (a.hitRate || 0))
})

function factorPct(f) {
  return f.hitRate == null ? 0 : Math.round(f.hitRate * 100)
}

function factorColor(f) {
  const r = factorPct(f)
  if (r >= 60) return '#0d9488'
  if (r >= 50) return '#f59e0b'
  return '#ef4444'
}

const weekList = computed(() => {
  return Object.entries(statStore.periodStats)
    .map(([week, payload]) => ({ week, ...payload }))
    .sort((a, b) => a.week.localeCompare(b.week))
})

// 信心档命中率(低/中/高),用于复盘主观信心准不准
const tierRows = computed(() => {
  const ta = statStore.tierAccuracy
  const rows = [
    { key: 'low', label: '低信心' },
    { key: 'mid', label: '中信心' },
    { key: 'high', label: '高信心' },
  ]
  return rows.map(r => {
    const t = ta[r.key] || { hit: 0, total: 0, hitRate: 0 }
    const pct = t.total > 0 ? Math.round(t.hitRate * 100) : 0
    const color = t.total === 0 ? '#d1d5db' : (pct >= 60 ? '#0d9488' : pct >= 50 ? '#f59e0b' : '#ef4444')
    return { ...r, hit: t.hit, total: t.total, pct, color }
  })
})
const tierTotal = computed(() => {
  const ta = statStore.tierAccuracy
  return (ta.low?.total || 0) + (ta.mid?.total || 0) + (ta.high?.total || 0)
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.page {
  padding: 24rpx;
  box-sizing: border-box;
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
}

.section {
  margin-bottom: 32rpx;
}

.section-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 16rpx;
}

.weekly {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.weekly-row {
  @include card;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16rpx 20rpx;
}

.week {
  font-size: 26rpx;
  font-weight: 600;
  color: #111827;
}

.meta {
  font-size: 24rpx;
  color: #6b7280;
}

.meta.win { 
  color: $frbt-positive;
  font-weight: 500;
}

.meta.lose { 
  color: $frbt-negative;
  font-weight: 500;
}

.empty {
  text-align: center;
  padding: 60rpx 0;
  color: #9ca3af;
  font-size: 26rpx;
}

.stat-row {
  display: flex;
  gap: 16rpx;
  margin-bottom: 20rpx;

  :deep(.stat-card) {
    flex: 1;
    min-width: 0;
  }
}

.sub-title {
  font-size: 24rpx;
  color: #6b7280;
  margin: 20rpx 0 12rpx;
}

.factor-list {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.factor-row {
  @include card;
  display: flex;
  align-items: center;
  padding: 14rpx 20rpx;
  gap: 12rpx;
}

.factor-name {
  font-size: 24rpx;
  color: #333;
  width: 140rpx;
  flex-shrink: 0;
}

.factor-bar-wrap {
  flex: 1;
  height: 12rpx;
  background: #f3f4f6;
  border-radius: 6rpx;
  overflow: hidden;
}

.factor-bar {
  height: 100%;
  border-radius: 6rpx;
}

.factor-pct {
  font-size: 24rpx;
  font-weight: 600;
  width: 80rpx;
  text-align: right;
}

.factor-sample {
  font-size: 20rpx;
  color: #aaa;
  width: 90rpx;
  text-align: right;
}

.field-hint {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 12rpx;
  display: block;
}
</style>
