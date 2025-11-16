<template>
  <view class="alert" :class="{ danger: shouldPause }">
    <view class="header">
      <text class="title">止损控制</text>
      <text class="tag">限制 {{ limit }} 次</text>
    </view>
    <view class="content">
      <text>当前连败：{{ consecutiveLosses }} 场</text>
      <text>最大回撤：{{ (drawdown * 100).toFixed(1) }}%</text>
    </view>
    <view v-if="warnings.length" class="warnings">
      <view v-for="tip in warnings" :key="tip">• {{ tip }}</view>
    </view>
    <view v-else class="ok">状态稳定，可继续按计划执行。</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { checkStopLoss } from '@/utils/stopLoss'

const props = defineProps({
  consecutiveLosses: {
    type: Number,
    default: 0
  },
  limit: {
    type: Number,
    default: 3
  },
  drawdown: {
    type: Number,
    default: 0
  }
})

const status = computed(() => checkStopLoss({
  consecutiveLosses: props.consecutiveLosses,
  limit: props.limit,
  drawdown: props.drawdown
}))

const warnings = computed(() => status.value.warnings)
const shouldPause = computed(() => status.value.shouldPause)
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.alert {
  @include card;
  border-left: 6rpx solid $frbt-primary;
  padding: 20rpx;
}

.alert.danger {
  border-left-color: $frbt-negative;
}

.header {
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
  color: #9ca3af;
  font-weight: 500;
}

.content {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
  margin-bottom: 12rpx;
  font-size: 24rpx;
  color: #374151;
}

.warnings {
  color: $frbt-negative;
  line-height: 1.6;
  font-size: 24rpx;
}

.ok {
  color: $frbt-primary;
  font-size: 24rpx;
}
</style>
