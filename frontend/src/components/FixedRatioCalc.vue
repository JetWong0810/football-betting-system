<template>
  <view class="calc-card">
    <view class="calc-header">
      <text class="title">固定比例法</text>
      <text class="tag">{{ (ratio * 100).toFixed(1) }}%</text>
    </view>
    <view class="value">{{ formattedStake }}</view>
    <view class="meta">当前余额 {{ formattedBankroll }}</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { calcFixedRatioStake } from '@/utils/fixedRatio'
import { formatCurrency } from '@/utils/formatters'

const props = defineProps({
  bankroll: {
    type: Number,
    default: 0
  },
  ratio: {
    type: Number,
    default: 0.03
  }
})

const stake = computed(() => calcFixedRatioStake({ bankroll: props.bankroll, ratio: props.ratio }))
const formattedStake = computed(() => formatCurrency(stake.value))
const formattedBankroll = computed(() => formatCurrency(props.bankroll))
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
