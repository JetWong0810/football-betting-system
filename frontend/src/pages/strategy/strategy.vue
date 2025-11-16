<template>
  <view class="page-wrapper">
    <scroll-view class="page" scroll-y>
    <view class="section">
      <view class="summary">
        <view>
          <view class="caption">实时余额</view>
          <view class="balance">{{ formatCurrency(statStore.balance) }}</view>
        </view>
        <view>
          <view class="caption">连续亏损</view>
          <view class="balance">{{ betStore.consecutiveLosses }} 场</view>
        </view>
      </view>
      <view class="inputs">
        <view class="input-item">
          <text>主观胜率 (%)</text>
          <input type="number" v-model.number="subjectiveWinRate" />
        </view>
        <view class="input-item">
          <text>盘口赔率</text>
          <input type="number" v-model.number="odds" />
        </view>
      </view>
    </view>

    <view class="section">
      <KellyCalc
        :bankroll="statStore.balance"
        :probability="subjectiveWinRate / 100"
        :odds="odds"
        :adjustment="config.kellyFactor"
      />
      <FixedRatioCalc :bankroll="statStore.balance" :ratio="config.fixedRatio" />
      <StopLossAlert
        :consecutive-losses="betStore.consecutiveLosses"
        :limit="config.stopLossLimit"
        :drawdown="statStore.drawdown"
      />
    </view>

    <view class="section final">
      <text class="section-title">综合建议</text>
      <view class="recommend">
        <view class="value">{{ formatCurrency(recommendedStake) }}</view>
        <view class="desc">取凯利与固定比例中的更保守值</view>
        <view class="risk" :class="{ danger: shouldPause }">
          {{ riskText }}
        </view>
      </view>
    </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import KellyCalc from '@/components/KellyCalc.vue'
import FixedRatioCalc from '@/components/FixedRatioCalc.vue'
import StopLossAlert from '@/components/StopLossAlert.vue'
import { useBetStore } from '@/stores/betStore'
import { useStatStore } from '@/stores/statStore'
import { useConfigStore } from '@/stores/configStore'
import { calcKellyStake } from '@/utils/kelly'
import { calcFixedRatioStake } from '@/utils/fixedRatio'
import { checkStopLoss } from '@/utils/stopLoss'
import { formatCurrency } from '@/utils/formatters'

const betStore = useBetStore()
const statStore = useStatStore()
const config = useConfigStore()

const subjectiveWinRate = ref(55)
const odds = ref(1.9)

const kellyStake = computed(() => calcKellyStake({
  bankroll: statStore.balance,
  odds: odds.value,
  probability: subjectiveWinRate.value / 100,
  adjustment: config.kellyFactor
}))

const fixedStake = computed(() => calcFixedRatioStake({
  bankroll: statStore.balance,
  ratio: config.fixedRatio
}))

const recommendedStake = computed(() => Math.min(kellyStake.value, fixedStake.value))

const stopLossStatus = computed(() => checkStopLoss({
  consecutiveLosses: betStore.consecutiveLosses,
  limit: config.stopLossLimit,
  drawdown: statStore.drawdown
}))

const shouldPause = computed(() => stopLossStatus.value.shouldPause)
const riskText = computed(() => {
  if (shouldPause.value) {
    return stopLossStatus.value.warnings.join('；')
  }
  return '状态稳定，可按建议额度执行。'
})

onShow(() => {
  uni.$emit('tab-active', 'strategy')
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.page-wrapper {
  min-height: 100vh;
  position: relative;
  padding-bottom: 32rpx;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
}

.page {
  padding: 24rpx;
  box-sizing: border-box;
}

.summary {
  @include card;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20rpx;
  padding: 20rpx;
}

.caption {
  font-size: 22rpx;
  color: #6b7280;
  margin-bottom: 6rpx;
}

.balance {
  font-size: 36rpx;
  font-weight: 600;
  color: #0d9488;
}

.inputs {
  margin-top: 16rpx;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16rpx;
}

.input-item {
  @include card;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  padding: 16rpx;
}

.input-item text {
  font-size: 24rpx;
  color: #374151;
  font-weight: 500;
}

.input-item input {
  background: #f9fafb;
  border-radius: 10rpx;
  padding: 12rpx;
  border: 1px solid rgba(13, 148, 136, 0.15);
  transition: all 0.3s;
  font-size: 26rpx;
}

.input-item input:focus {
  border-color: #0d9488;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
}

.section {
  margin-top: 24rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.section-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 12rpx;
}

.recommend {
  @include card;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  padding: 20rpx;
}

.recommend .value {
  font-size: 44rpx;
  font-weight: 700;
  color: #0d9488;
}

.recommend .desc {
  font-size: 24rpx;
  color: #6b7280;
}

.recommend .risk {
  padding: 12rpx;
  border-radius: 10rpx;
  background: linear-gradient(135deg, rgba(13, 148, 136, 0.1) 0%, rgba(20, 184, 166, 0.1) 100%);
  color: #0d9488;
  font-weight: 500;
  font-size: 24rpx;
  line-height: 1.6;
}

.recommend .risk.danger {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.1) 100%);
  color: #ef4444;
  font-weight: 500;
}
</style>
