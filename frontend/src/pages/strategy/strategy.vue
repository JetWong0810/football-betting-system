<template>
  <view class="page-wrapper">
    <scroll-view class="page" scroll-y>
      <!-- 当前策略概览 -->
      <view class="strategy-header">
        <view class="strategy-info">
          <text class="strategy-label">当前策略</text>
          <text class="strategy-name">{{ currentPreset.label }}</text>
        </view>
        <view class="strategy-link" @tap="goSettings">
          <text>切换</text>
        </view>
      </view>

      <!-- 下一注推荐 -->
      <view class="section">
        <text class="section-title">下一注推荐</text>
        <view class="recommend-card">
          <view class="odds-table">
            <view class="odds-row header">
              <text class="odds-cell">赔率</text>
              <text class="odds-cell">置信60%</text>
              <text class="odds-cell">置信70%</text>
              <text class="odds-cell">置信80%</text>
            </view>
            <view v-for="row in oddsTable" :key="row.odds" class="odds-row">
              <text class="odds-cell label">{{ row.odds }}</text>
              <text class="odds-cell">¥{{ row.c60 }}</text>
              <text class="odds-cell">¥{{ row.c70 }}</text>
              <text class="odds-cell">¥{{ row.c80 }}</text>
            </view>
          </view>
          <text class="recommend-hint">基于有效资金 ¥{{ betStore.effectiveBankroll }} 和{{ currentPreset.label }}策略计算(凯利参考,主决策用信心档三档金额)</text>
        </view>
      </view>

      <!-- 风险状态 -->
      <view class="section">
        <text class="section-title">风险状态</text>
        <view class="risk-panel">
          <view class="risk-item">
            <view class="risk-head">
              <text class="risk-name">连败</text>
              <text class="risk-status" :class="lossStatus">{{ betStore.consecutiveLosses }} / {{ config.stopLossLimit }}</text>
            </view>
            <view class="risk-bar-wrap">
              <view class="risk-bar" :class="lossStatus" :style="{ width: lossBarWidth }"></view>
            </view>
          </view>

          <view class="risk-item">
            <view class="risk-head">
              <text class="risk-name">回撤</text>
              <text class="risk-status" :class="drawdownStatus">{{ formatPercent(statStore.drawdown) }}</text>
            </view>
            <view class="risk-bar-wrap">
              <view class="risk-bar" :class="drawdownStatus" :style="{ width: drawdownBarWidth }"></view>
            </view>
          </view>

          <view class="risk-item">
            <view class="risk-head">
              <text class="risk-name">本月投注</text>
              <text class="risk-status safe">{{ monthBetCount }} 注</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 手动计算器 -->
      <view class="section">
        <text class="section-title">手动计算</text>
        <view class="calc-card">
          <view class="calc-inputs">
            <view class="calc-field">
              <text class="calc-label">胜率 (%)</text>
              <input type="digit" v-model.number="manualWinRate" placeholder="60" />
            </view>
            <view class="calc-field">
              <text class="calc-label">赔率</text>
              <input type="digit" v-model.number="manualOdds" placeholder="1.90" />
            </view>
          </view>
          <view class="calc-result" v-if="manualResult.amount > 0">
            <text class="calc-amount">建议金额：¥{{ manualResult.amount }}</text>
            <text class="calc-method">{{ manualResult.method }}（Kelly ¥{{ manualResult.kelly }} / 固定 ¥{{ manualResult.fixed }}）</text>
          </view>
          <view class="calc-result" v-else>
            <text class="calc-empty">输入胜率和赔率查看建议金额</text>
          </view>
        </view>
      </view>

      <!-- 策略参数明细 -->
      <view class="section">
        <text class="section-title">策略参数</text>
        <view class="params-card">
          <view class="param-row">
            <text class="param-label">单注上限</text>
            <text class="param-value">{{ (currentPreset.maxRatio * 100).toFixed(0) }}%</text>
          </view>
          <view class="param-row">
            <text class="param-label">Kelly系数</text>
            <text class="param-value">{{ currentPreset.kellyFactor }}</text>
          </view>
          <view class="param-row">
            <text class="param-label">连败止损</text>
            <text class="param-value">{{ currentPreset.stopLossLimit }} 场</text>
          </view>
          <view class="param-row">
            <text class="param-label">最大回撤</text>
            <text class="param-value">{{ (Math.abs(currentPreset.maxDrawdown) * 100).toFixed(0) }}%</text>
          </view>
          <view class="param-row">
            <text class="param-label">最低置信度</text>
            <text class="param-value">{{ currentPreset.minConfidence }}%</text>
          </view>
          <view class="param-row">
            <text class="param-label">信心档(低/中/高)</text>
            <text class="param-value">{{ (currentPreset.tierRatios.low * 100).toFixed(1) }}% / {{ (currentPreset.tierRatios.mid * 100).toFixed(1) }}% / {{ (currentPreset.tierRatios.high * 100).toFixed(1) }}%</text>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useBetStore } from '@/stores/betStore'
import { useStatStore } from '@/stores/statStore'
import { useConfigStore } from '@/stores/configStore'
import { getStrategyPreset, calcRecommendedStake } from '@/utils/strategyEngine'
import { loadCalibration } from '@/utils/calibration'
import { formatCurrency, formatPercent } from '@/utils/formatters'
import { requireAuth } from '@/utils/auth'
import dayjs from 'dayjs'

const betStore = useBetStore()
const statStore = useStatStore()
const config = useConfigStore()

const manualWinRate = ref(null)
const manualOdds = ref(null)

const bankroll = computed(() => betStore.bankroll)

// 自定义策略配置
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

const currentPreset = computed(() => getStrategyPreset(config.riskTolerance, customConfig.value))

// 校准数据（命中率分桶），用于把置信度校准为真实概率
const calibrationData = ref(null)

// 策略页进入时预加载校准数据
loadCalibration().then((cal) => { calibrationData.value = cal })

const oddsTable = computed(() => {
  const b = bankroll.value
  const level = config.riskTolerance
  const cc = customConfig.value
  const cal = calibrationData.value
  const rows = [1.70, 1.85, 1.90, 2.00, 2.10, 2.30]
  return rows.map(odds => ({
    odds: odds.toFixed(2),
    c60: calcRecommendedStake({ bankroll: b, odds, confidence: 60, riskLevel: level, customConfig: cc, calibration: cal }).amount,
    c70: calcRecommendedStake({ bankroll: b, odds, confidence: 70, riskLevel: level, customConfig: cc, calibration: cal }).amount,
    c80: calcRecommendedStake({ bankroll: b, odds, confidence: 80, riskLevel: level, customConfig: cc, calibration: cal }).amount,
  }))
})

const manualResult = computed(() => {
  if (!manualWinRate.value || !manualOdds.value) return { amount: 0, kelly: 0, fixed: 0, method: '' }
  // 手动计算器：用户直接输入胜率，视为真实概率，跳过校准
  return calcRecommendedStake({
    bankroll: bankroll.value,
    odds: manualOdds.value,
    probability: Number(manualWinRate.value) / 100,
    riskLevel: config.riskTolerance,
    customConfig: customConfig.value,
  })
})

const monthBetCount = computed(() => {
  const startOfMonth = dayjs().startOf('month').format('YYYY-MM-DD')
  return betStore.bets.filter(b =>
    (b.status === 'betting' || b.status === 'settled') &&
    dayjs(b.betTime).format('YYYY-MM-DD') >= startOfMonth
  ).length
})

const lossBarWidth = computed(() => {
  const ratio = betStore.consecutiveLosses / config.stopLossLimit
  return `${Math.min(ratio * 100, 100)}%`
})

const lossStatus = computed(() => {
  const ratio = betStore.consecutiveLosses / config.stopLossLimit
  if (ratio >= 1) return 'danger'
  if (ratio >= 0.6) return 'warning'
  return 'safe'
})

const drawdownBarWidth = computed(() => {
  const ratio = Math.abs(statStore.drawdown) / Math.abs(currentPreset.value.maxDrawdown)
  return `${Math.min(ratio * 100, 100)}%`
})

const drawdownStatus = computed(() => {
  const ratio = Math.abs(statStore.drawdown) / Math.abs(currentPreset.value.maxDrawdown)
  if (ratio >= 1) return 'danger'
  if (ratio >= 0.6) return 'warning'
  return 'safe'
})

function goSettings() {
  uni.navigateTo({ url: '/pages/settings/settings' })
}

onShow(() => {
  if (!requireAuth()) return
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

/* 策略头部 */
.strategy-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 24rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.strategy-label {
  font-size: 22rpx;
  color: #6b7280;
  display: block;
}

.strategy-name {
  font-size: 32rpx;
  font-weight: 700;
  color: #0d9488;
  display: block;
  margin-top: 4rpx;
}

.strategy-link {
  padding: 8rpx 20rpx;
  border: 1px solid #e5e7eb;
  border-radius: 4rpx;

  text {
    font-size: 24rpx;
    color: #6b7280;
  }

  &:active {
    background: #f9fafb;
  }
}

/* 通用 */
.section {
  margin-bottom: 24rpx;
}

.section-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12rpx;
}

/* 推荐卡片 */
.recommend-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.odds-table {
  display: flex;
  flex-direction: column;
}

.odds-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  padding: 12rpx 0;
  border-bottom: 1px solid #f3f4f6;

  &.header {
    border-bottom: 1px solid #e5e7eb;
  }

  &:last-child {
    border-bottom: none;
  }
}

.odds-cell {
  font-size: 24rpx;
  color: #374151;
  text-align: center;

  .header & {
    font-size: 22rpx;
    color: #9ca3af;
    font-weight: 500;
  }

  &.label {
    font-weight: 600;
    color: #0d9488;
  }
}

.recommend-hint {
  font-size: 20rpx;
  color: #9ca3af;
  margin-top: 12rpx;
  display: block;
}

/* 风险面板 */
.risk-panel {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.risk-item {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.risk-name {
  font-size: 24rpx;
  color: #6b7280;
}

.risk-status {
  font-size: 24rpx;
  font-weight: 500;

  &.safe { color: #059669; }
  &.warning { color: #d97706; }
  &.danger { color: #dc2626; }
}

.risk-bar-wrap {
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
}

/* 手动计算器 */
.calc-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.calc-inputs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16rpx;
  margin-bottom: 16rpx;
}

.calc-field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.calc-label {
  font-size: 22rpx;
  color: #6b7280;
}

.calc-field input {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6rpx;
  padding: 14rpx 16rpx;
  font-size: 26rpx;
  color: #1f2937;

  &:focus {
    border-color: #0d9488;
    background: #fff;
  }
}

.calc-result {
  padding: 16rpx;
  background: #f0fdfa;
  border-radius: 6rpx;
  text-align: center;
}

.calc-amount {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  display: block;
}

.calc-method {
  font-size: 22rpx;
  color: #6b7280;
  margin-top: 6rpx;
  display: block;
}

.calc-empty {
  font-size: 24rpx;
  color: #9ca3af;
}

/* 参数明细 */
.params-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  display: flex;
  flex-direction: column;
  gap: 14rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.param-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.param-label {
  font-size: 24rpx;
  color: #6b7280;
}

.param-value {
  font-size: 24rpx;
  color: #1f2937;
  font-weight: 500;
}
</style>
