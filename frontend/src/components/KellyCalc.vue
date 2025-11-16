<template>
  <view class="calc-card">
    <view class="calc-header">
      <text class="title">凯利公式建议</text>
      <text class="tag">{{ (probability * 100).toFixed(0) }}% 胜率</text>
    </view>
    <view class="value">{{ formattedStake }}</view>
    <view class="meta">资金占比 {{ ratioText }}</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { calcKellyStake } from '@/utils/kelly'
import { formatCurrency, formatPercent } from '@/utils/formatters'

const props = defineProps({
  bankroll: {
    type: Number,
    default: 0
  },
  odds: {
    type: Number,
    default: 1.8
  },
  probability: {
    type: Number,
    default: 0.55
  },
  adjustment: {
    type: Number,
    default: 0.5
  }
})

const stake = computed(() => calcKellyStake({
  bankroll: props.bankroll,
  odds: props.odds,
  probability: props.probability,
  adjustment: props.adjustment
}))

const formattedStake = computed(() => formatCurrency(stake.value))
const ratioText = computed(() => {
  if (!props.bankroll) return '0%'
  return formatPercent(stake.value / props.bankroll, 2)
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.calc-card {
  @include card;
  padding: 20rpx;
}

.calc-header {
  @extend .flex-between;
  margin-bottom: 12rpx;
}

.title {
  font-size: 26rpx;
  font-weight: 600;
  color: #111827;
}

.tag {
  font-size: 22rpx;
  color: $frbt-secondary;
  font-weight: 500;
}

.value {
  font-size: 40rpx;
  font-weight: 700;
  color: #0d9488;
  margin: 8rpx 0;
}

.meta {
  font-size: 24rpx;
  color: #6b7280;
}
</style>
