<template>
  <view class="page-wrapper">
    <scroll-view class="page" scroll-y>
      <!-- 资金状态卡片 -->
      <view class="hero">
        <view class="hero-row">
          <view class="hero-main">
            <text class="hero-caption">可用资金</text>
            <text class="hero-balance">{{ formatCurrency(bankroll) }}</text>
            <text class="hero-sub">有效资金 {{ formatCurrency(betStore.effectiveBankroll) }}(仓位基准)</text>
          </view>
          <view class="hero-badge">
            <text class="badge-label">{{ strategyLabel }}</text>
          </view>
        </view>

        <view class="hero-stats">
          <view class="stat-item">
            <text class="stat-value" :class="{ up: betStore.totalProfit >= 0, down: betStore.totalProfit < 0 }">{{ formatCurrency(betStore.totalProfit) }}</text>
            <text class="stat-label">累计盈亏</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-value">{{ formatPercent(betStore.winningRate) }}</text>
            <text class="stat-label">胜率</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-value">{{ formatPercent(statStore.roi) }}</text>
            <text class="stat-label">ROI</text>
          </view>
        </view>

        <!-- 月目标进度 -->
        <view class="progress-bar">
          <view class="progress-fill" :style="{ width: progressWidth }"></view>
        </view>
        <text class="progress-text">月目标进度 {{ formatPercent(targetProgress) }}</text>
      </view>

      <!-- 出金阀提示 -->
      <view v-if="withdrawInfo.trigger" class="withdraw-card" @tap="doWithdraw">
        <view class="withdraw-main">
          <text class="withdraw-title">盈利出金提示</text>
          <text class="withdraw-desc">盈利金已达本金 {{ formatPercent(config.withdrawThreshold) }},建议提取 ¥{{ withdrawInfo.amount }} 落袋</text>
        </view>
        <text class="withdraw-action">提取</text>
      </view>

      <!-- 系统建议 -->
      <view class="advice-card" :class="advice.warning ? 'warning' : ''">
        <view class="advice-header">
          <text class="advice-title">系统建议</text>
          <text class="advice-level" :class="riskStatus.level">{{ riskStatus.level === 'safe' ? '正常' : riskStatus.level === 'warning' ? '注意' : '警告' }}</text>
        </view>
        <text class="advice-text">{{ advice.text }}</text>
        <view class="advice-stake" v-if="!advice.warning">
          <text class="stake-label">三档金额(低/中/高)</text>
          <text class="stake-range">¥{{ tieredStakes.low.amount }} / ¥{{ tieredStakes.mid.amount }} / ¥{{ tieredStakes.high.amount }}</text>
        </view>
      </view>

      <!-- 快捷操作 -->
      <view class="actions-row">
        <view class="action-card" @tap="goPredict">
          <text class="action-label">去预测</text>
          <text class="action-desc">选赛分析</text>
        </view>
        <view class="action-card" @tap="goRecord">
          <text class="action-label">快速记录</text>
          <text class="action-desc">手动投注</text>
        </view>
      </view>

      <!-- 本周概览 -->
      <view class="section">
        <text class="section-title">本周概览</text>
        <view class="week-card">
          <view class="week-item">
            <text class="week-value">¥{{ weekStats.stake }}</text>
            <text class="week-label">投入</text>
          </view>
          <view class="week-item">
            <text class="week-value" :class="{ up: weekStats.profit >= 0, down: weekStats.profit < 0 }">{{ weekStats.profit >= 0 ? '+' : '' }}¥{{ weekStats.profit }}</text>
            <text class="week-label">盈亏</text>
          </view>
          <view class="week-item">
            <text class="week-value">{{ weekStats.count }}</text>
            <text class="week-label">注数</text>
          </view>
        </view>
      </view>

      <!-- 盈利趋势 -->
      <view class="section">
        <text class="section-title">盈利趋势</text>
        <view class="chart-card">
          <ChartProfit :series="statStore.trendSeries" />
        </view>
      </view>

      <!-- 风控状态 -->
      <view class="section">
        <text class="section-title">风控状态</text>
        <view class="risk-card">
          <view class="risk-item">
            <text class="risk-label">连败</text>
            <view class="risk-bar-wrap">
              <view class="risk-bar" :style="{ width: lossBarWidth }" :class="riskStatus.level"></view>
            </view>
            <text class="risk-num">{{ betStore.consecutiveLosses }}/{{ config.stopLossLimit }}</text>
          </view>
          <view class="risk-item">
            <text class="risk-label">回撤</text>
            <view class="risk-bar-wrap">
              <view class="risk-bar" :style="{ width: drawdownBarWidth }" :class="drawdownLevel"></view>
            </view>
            <text class="risk-num">{{ formatPercent(statStore.drawdown) }}</text>
          </view>
          <view class="risk-item" v-if="controlStore.controlAlert.level !== 'normal'">
            <text class="risk-label">控手</text>
            <view class="risk-bar-wrap">
              <view class="risk-bar" :style="{ width: controlBarWidth }" :class="controlStore.controlAlert.level"></view>
            </view>
            <text class="risk-num">{{ betStore.consecutiveLosses }}/{{ controlStore.controlAlert.strongAt }}</text>
          </view>
          <view class="risk-item" v-if="controlStore.isPaused">
            <text class="risk-label">冷静</text>
            <view class="risk-bar-wrap">
              <view class="risk-bar pause" :style="{ width: '100%' }"></view>
            </view>
            <text class="risk-num">暂停中</text>
          </view>
        </view>
      </view>
    </scroll-view>

    <BetRecordDialog v-model:visible="showDialog" @success="handleRecordSuccess" />
    <CoolDownAlert />

    <!-- 数据查询助手 -->
    <DataQueryFab @open="showQueryPanel = true" />
    <DataQueryPanel :visible="showQueryPanel" @close="showQueryPanel = false" />

    <!-- 快速记录入口 -->
    <QuickRecordFab />
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useBetStore } from '@/stores/betStore'
import { useConfigStore } from '@/stores/configStore'
import { useStatStore } from '@/stores/statStore'
import ChartProfit from '@/components/ChartProfit.vue'
import BetRecordDialog from '@/components/BetRecordDialog.vue'
import DataQueryFab from '@/components/DataQueryFab.vue'
import DataQueryPanel from '@/components/DataQueryPanel.vue'
import QuickRecordFab from '@/components/QuickRecordFab.vue'
import { formatCurrency, formatPercent } from '@/utils/formatters'
import { getStrategyPreset, generateAdvice, checkRiskStatus, calcTieredStakes } from '@/utils/strategyEngine'
import { suggestWithdraw } from '@/utils/bankrollLayer'
import CoolDownAlert from '@/components/CoolDownAlert.vue'
import { useControlStore } from '@/stores/controlStore'
import dayjs from 'dayjs'

const betStore = useBetStore()
const config = useConfigStore()
const statStore = useStatStore()
const controlStore = useControlStore()
const showDialog = ref(false)
const showQueryPanel = ref(false)

const bankroll = computed(() => betStore.bankroll)
const targetProgress = computed(() => Math.min(Math.max(statStore.targetProgress, 0), 2))
const progressWidth = computed(() => `${Math.min(targetProgress.value * 100, 100)}%`)

// 自定义策略配置（仅 custom 模式）
const customConfig = computed(() => {
  if (config.riskTolerance !== 'custom') return null
  return {
    fixedRatio: config.fixedRatio,
    kellyFactor: config.kellyFactor,
    stopLossLimit: config.stopLossLimit,
    maxDrawdown: config.maxDrawdown,
    minConfidence: config.minConfidence,
  }
})

const strategyLabel = computed(() => {
  const preset = getStrategyPreset(config.riskTolerance, customConfig.value)
  return preset.label
})

const consecutiveWins = computed(() => {
  let streak = 0
  const settled = betStore.bets.filter(b => b.status === 'settled')
  for (const bet of settled) {
    const r = bet.result
    if (r === 'win' || r === 'half-win') streak++
    else if (r === 'lose' || r === 'half-lose') break
    // push/走水中性，不累加不中断
  }
  return streak
})

const advice = computed(() => generateAdvice({
  consecutiveWins: consecutiveWins.value,
  consecutiveLosses: betStore.consecutiveLosses,
  drawdown: statStore.drawdown,
  riskLevel: config.riskTolerance,
  customConfig: customConfig.value
}))

const riskStatus = computed(() => checkRiskStatus({
  consecutiveLosses: betStore.consecutiveLosses,
  drawdown: statStore.drawdown,
  riskLevel: config.riskTolerance,
  customConfig: customConfig.value
}))

const tieredStakes = computed(() => calcTieredStakes({
  effectiveBankroll: betStore.effectiveBankroll,
  riskLevel: config.riskTolerance,
  customConfig: customConfig.value,
}))

// 出金阀:盈利金达本金阈值时提示提取
const withdrawInfo = computed(() => {
  const layer = betStore.bankrollLayer
  return suggestWithdraw({
    profitPool: layer.profitPool,
    principal: layer.principal,
    threshold: config.withdrawThreshold,
    ratio: config.withdrawRatio,
  })
})

// 控手进度条宽度(连不中 / strongAt 阈值)
const controlBarWidth = computed(() => {
  const a = controlStore.controlAlert
  const ratio = a.strongAt > 0 ? betStore.consecutiveLosses / a.strongAt : 0
  return `${Math.min(ratio * 100, 100)}%`
})

const weekStats = computed(() => {
  const startOfWeek = dayjs().startOf('week').format('YYYY-MM-DD')
  const thisWeek = betStore.bets.filter(b =>
    (b.status === 'betting' || b.status === 'settled') &&
    dayjs(b.betTime).format('YYYY-MM-DD') >= startOfWeek
  )
  const stake = thisWeek.reduce((s, b) => s + Number(b.stake || 0), 0)
  const profit = thisWeek.filter(b => b.status === 'settled').reduce((s, b) => s + Number(b.profit || 0), 0)
  return {
    stake: parseFloat(stake.toFixed(2)),
    profit: parseFloat(profit.toFixed(2)),
    count: thisWeek.length
  }
})

const lossBarWidth = computed(() => {
  const ratio = betStore.consecutiveLosses / config.stopLossLimit
  return `${Math.min(ratio * 100, 100)}%`
})

const drawdownBarWidth = computed(() => {
  const preset = getStrategyPreset(config.riskTolerance, customConfig.value)
  const ratio = Math.abs(statStore.drawdown) / Math.abs(preset.maxDrawdown)
  return `${Math.min(ratio * 100, 100)}%`
})

const drawdownLevel = computed(() => {
  const preset = getStrategyPreset(config.riskTolerance, customConfig.value)
  const ratio = Math.abs(statStore.drawdown) / Math.abs(preset.maxDrawdown)
  if (ratio >= 1) return 'danger'
  if (ratio >= 0.6) return 'warning'
  return 'safe'
})

function goPredict() {
  uni.navigateTo({ url: '/pages/predict/predict' })
}

function goRecord() {
  if (controlStore.isPaused) {
    uni.showToast({ title: '下注已暂停,请先冷静恢复', icon: 'none' })
    return
  }
  showDialog.value = true
}

function doWithdraw() {
  const info = withdrawInfo.value
  if (!info.trigger) return
  uni.showModal({
    title: '盈利出金提示',
    content: `盈利金已达本金 ${(config.withdrawThreshold * 100).toFixed(0)}%,建议提取 ¥${info.amount} 落袋。确认后已提取盈利增加,有效资金与仓位回落。`,
    success: (res) => {
      if (res.confirm) {
        config.updateConfig({ realizedWithdraw: Number(config.realizedWithdraw) + info.amount })
        uni.showToast({ title: `已记录出金 ¥${info.amount}`, icon: 'none' })
      }
    },
  })
}

function handleRecordSuccess() {
  setTimeout(() => {
    uni.switchTab({ url: '/pages/record/record' })
  }, 500)
}

onShow(() => {
  uni.$emit('tab-active', 'home')
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.page-wrapper {
  min-height: 100vh;
  background: #f4f5f7;
}

.page {
  padding: 24rpx;
  box-sizing: border-box;
  min-height: 100vh;
}

/* 资金状态卡片 */
.hero {
  background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
  border-radius: 6rpx;
  padding: 28rpx 24rpx;
  margin-bottom: 20rpx;
  color: #fff;
}

.hero-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.hero-caption {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.7);
}

.hero-balance {
  font-size: 48rpx;
  font-weight: 700;
  margin-top: 4rpx;
  display: block;
}

.hero-sub {
  font-size: 20rpx;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 6rpx;
  display: block;
}

/* 出金阀提示 */
.withdraw-card {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-left: 4px solid #f59e0b;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 20rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
}

.withdraw-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.withdraw-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #92400e;
}

.withdraw-desc {
  font-size: 22rpx;
  color: #b45309;
}

.withdraw-action {
  font-size: 24rpx;
  font-weight: 600;
  color: #fff;
  background: #f59e0b;
  padding: 10rpx 24rpx;
  border-radius: 6rpx;
  flex-shrink: 0;
}

.hero-badge {
  background: rgba(255, 255, 255, 0.18);
  padding: 8rpx 16rpx;
  border-radius: 4rpx;
  border: 1px solid rgba(255, 255, 255, 0.25);
}

.badge-label {
  font-size: 22rpx;
  font-weight: 600;
}

.hero-stats {
  display: flex;
  align-items: center;
  margin-top: 24rpx;
  padding-top: 20rpx;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
}

.stat-item {
  flex: 1;
  text-align: center;
}

.stat-value {
  font-size: 28rpx;
  font-weight: 600;
  display: block;

  &.up { color: #86efac; }
  &.down { color: #fca5a5; }
}

.stat-label {
  font-size: 20rpx;
  color: rgba(255, 255, 255, 0.65);
  margin-top: 4rpx;
  display: block;
}

.stat-divider {
  width: 1px;
  height: 32rpx;
  background: rgba(255, 255, 255, 0.2);
}

.progress-bar {
  margin-top: 20rpx;
  height: 6rpx;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3rpx;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #86efac;
  border-radius: 3rpx;
  transition: width 0.3s;
}

.progress-text {
  font-size: 20rpx;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 8rpx;
  display: block;
}

/* 系统建议 */
.advice-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 20rpx;
  border-left: 4px solid #0d9488;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);

  &.warning {
    border-left-color: #f59e0b;
  }
}

.advice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10rpx;
}

.advice-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #374151;
}

.advice-level {
  font-size: 20rpx;
  font-weight: 500;
  padding: 4rpx 12rpx;
  border-radius: 4rpx;

  &.safe { color: #059669; background: #ecfdf5; }
  &.warning { color: #d97706; background: #fffbeb; }
  &.danger { color: #dc2626; background: #fef2f2; }
}

.advice-text {
  font-size: 24rpx;
  color: #4b5563;
  line-height: 1.6;
}

.advice-stake {
  margin-top: 12rpx;
  padding-top: 12rpx;
  border-top: 1px solid #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stake-label {
  font-size: 22rpx;
  color: #6b7280;
}

.stake-range {
  font-size: 26rpx;
  font-weight: 600;
  color: #0d9488;
}

/* 快捷操作 */
.actions-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12rpx;
  margin-bottom: 24rpx;
}

.action-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 24rpx 20rpx;
  text-align: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: transform 0.15s;

  &:active { transform: scale(0.97); }
}

.action-label {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  display: block;
}

.action-desc {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 4rpx;
  display: block;
}

/* 通用 section */
.section {
  margin-bottom: 24rpx;
}

.section-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12rpx;
}

/* 本周概览 */
.week-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.week-item {
  text-align: center;
}

.week-value {
  font-size: 28rpx;
  font-weight: 600;
  color: #1f2937;
  display: block;

  &.up { color: #059669; }
  &.down { color: #dc2626; }
}

.week-label {
  font-size: 20rpx;
  color: #9ca3af;
  margin-top: 4rpx;
  display: block;
}

/* 趋势图 */
.chart-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

/* 风控状态 */
.risk-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.risk-item {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.risk-label {
  font-size: 24rpx;
  color: #6b7280;
  width: 60rpx;
  flex-shrink: 0;
}

.risk-bar-wrap {
  flex: 1;
  height: 8rpx;
  background: #f3f4f6;
  border-radius: 4rpx;
  overflow: hidden;
}

.risk-bar {
  height: 100%;
  border-radius: 4rpx;
  transition: width 0.3s;

  &.safe { background: #0d9488; }
  &.warning { background: #f59e0b; }
  &.danger { background: #ef4444; }
  &.strong { background: #f59e0b; }
  &.pause { background: #ef4444; }
}

.risk-num {
  font-size: 22rpx;
  color: #374151;
  font-weight: 500;
  width: 80rpx;
  text-align: right;
  flex-shrink: 0;
}
</style>
