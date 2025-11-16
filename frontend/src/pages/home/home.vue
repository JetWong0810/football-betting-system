<template>
  <view class="page-wrapper">
    <scroll-view class="page" scroll-y>
    <view class="hero">
      <view class="hero-top">
        <view>
          <text class="caption">账户余额</text>
          <view class="balance">{{ formatCurrency(balance) }}</view>
        </view>
        <view class="chip">
          <text>目标完成度</text>
          <text class="chip-value">{{ formatPercent(targetProgress) }}</text>
        </view>
      </view>
      <view class="hero-sub">
        <view>
          <text class="mini-label">累计盈亏</text>
          <text class="mini-value" :class="{ up: betStore.totalProfit >= 0, down: betStore.totalProfit < 0 }">
            {{ formatCurrency(betStore.totalProfit) }}
          </text>
        </view>
        <view>
          <text class="mini-label">胜率</text>
          <text class="mini-value">{{ formatPercent(betStore.winningRate) }}</text>
        </view>
        <view>
          <text class="mini-label">ROI</text>
          <text class="mini-value">{{ formatPercent(statStore.roi) }}</text>
        </view>
      </view>
      <button class="quick-record-btn" @tap="goRecord">
        <text class="btn-icon">+</text>
        <text class="btn-text">快速记录</text>
      </button>
    </view>

    <view class="section">
      <text class="section-title">数据概览</text>
      <view class="stat-grid">
        <StatCard
          v-for="card in summaryCards"
          :key="card.title"
          :title="card.title"
          :value="card.value"
          :subtitle="card.subtitle"
          :positive="card.positive"
          :negative="card.negative"
        />
      </view>
    </view>

    <view class="section">
      <text class="section-title">盈利趋势</text>
      <view class="card surface">
        <ChartProfit :series="statStore.trendSeries" />
      </view>
    </view>

    <view class="section">
      <text class="section-title">风控雷达</text>
      <view class="card risk">
        <view class="risk-row">
          <text>连续亏损</text>
          <text>{{ betStore.consecutiveLosses }} / {{ config.stopLossLimit }} 场</text>
        </view>
        <view class="risk-row">
          <text>最大回撤</text>
          <text>{{ formatPercent(statStore.drawdown) }}</text>
        </view>
      </view>
    </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useBetStore } from '@/stores/betStore'
import { useConfigStore } from '@/stores/configStore'
import { useStatStore } from '@/stores/statStore'
import StatCard from '@/components/StatCard.vue'
import ChartProfit from '@/components/ChartProfit.vue'
import { formatCurrency, formatPercent } from '@/utils/formatters'

const betStore = useBetStore()
const config = useConfigStore()
const statStore = useStatStore()

const balance = computed(() => statStore.balance)
const targetProgress = computed(() => Math.min(Math.max(statStore.targetProgress, 0), 2))

const summaryCards = computed(() => [
  {
    title: '总投入',
    value: formatCurrency(betStore.totalStake),
    subtitle: `${betStore.bets.length} 场`,
    positive: false,
    negative: false
  },
  {
    title: '累计盈亏',
    value: formatCurrency(betStore.totalProfit),
    subtitle: betStore.totalProfit >= 0 ? '趋势向上' : '注意回撤',
    positive: betStore.totalProfit >= 0,
    negative: betStore.totalProfit < 0
  },
  {
    title: '胜率',
    value: formatPercent(betStore.winningRate),
    subtitle: `${betStore.winCount} 胜 / ${betStore.bets.length} 场`,
    positive: betStore.winningRate >= 0.5,
    negative: betStore.winningRate < 0.5
  },
  {
    title: '投资回报率',
    value: formatPercent(statStore.roi),
    subtitle: statStore.roi >= 0 ? '盈利区间' : '亏损区间',
    positive: statStore.roi >= 0,
    negative: statStore.roi < 0
  }
])

function goRecord() {
  uni.navigateTo({ url: '/pages/record/record' })
}

onShow(() => {
  uni.$emit('tab-active', 'home')
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.page-wrapper {
  position: relative;
  min-height: 100vh;
  padding-bottom: 32rpx;
}

.page {
  padding: 24rpx;
  box-sizing: border-box;
  background: linear-gradient(180deg, #0d9488 0%, #0d9488 200rpx, #e8f8f5 200rpx);
}

.hero {
  @include card;
  color: #fff;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  margin-bottom: 24rpx;
  padding: 24rpx;
  box-shadow: 0 8rpx 24rpx rgba(13, 148, 136, 0.25);
}

.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20rpx;
}

.caption {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 6rpx;
}

.balance {
  font-size: 52rpx;
  font-weight: 700;
  line-height: 1.2;
}

.chip {
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(10px);
  border-radius: 16rpx;
  padding: 12rpx 18rpx;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
  flex-shrink: 0;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.chip text:first-child {
  font-size: 20rpx;
  color: rgba(255, 255, 255, 0.8);
}

.chip-value {
  font-size: 28rpx;
  font-weight: 600;
}

.hero-sub {
  margin-top: 24rpx;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20rpx;
  padding-bottom: 20rpx;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.mini-label {
  font-size: 20rpx;
  color: rgba(255, 255, 255, 0.65);
}

.mini-value {
  display: block;
  margin-top: 6rpx;
  font-size: 28rpx;
  font-weight: 600;
}

.mini-value.up {
  color: #86efac;
}

.mini-value.down {
  color: #f87171;
}

.quick-record-btn {
  margin-top: 20rpx;
  width: 100%;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-radius: 14rpx;
  padding: 12rpx 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  border: none;
  box-shadow: 0 4rpx 12rpx rgba(0, 0, 0, 0.08);
  transition: all 0.3s;
  height: 72rpx;
}

.quick-record-btn:active {
  transform: scale(0.98);
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.08);
}

.btn-icon {
  font-size: 30rpx;
  font-weight: 700;
  color: #0d9488;
  line-height: 1;
}

.btn-text {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
}

.section {
  margin-bottom: 28rpx;
}

.section-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 16rpx;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280rpx, 1fr));
  gap: 16rpx;
}

.card.surface {
  padding: 20rpx;
}

.card.risk {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  padding: 20rpx;
}

.risk-row {
  display: flex;
  justify-content: space-between;
  font-size: 26rpx;
  color: #374151;
}

.risk-row text:last-child {
  font-weight: 600;
  color: #0d9488;
}
</style>
