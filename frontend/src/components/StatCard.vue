<template>
  <view class="stat-card">
    <view class="title">{{ title }}</view>
    <view class="value">{{ value }}</view>
    <view v-if="subtitle" class="subtitle" :class="{ positive, negative }">
      {{ subtitle }}
    </view>
  </view>
</template>

<script setup>
const props = defineProps({
  title: String,
  value: {
    type: String,
    default: '--'
  },
  subtitle: {
    type: String,
    default: ''
  },
  positive: Boolean,
  negative: Boolean
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.stat-card {
  @include card;
  min-width: 260rpx;
  padding: 18rpx;
}

.title {
  font-size: 24rpx;
  color: #6b7280;
  font-weight: 500;
  margin-bottom: 8rpx;
}

.value {
  font-size: 36rpx;
  font-weight: 600;
  margin: 8rpx 0;
  color: #0d9488;
}

.subtitle {
  font-size: 22rpx;
  color: #9ca3af;
  line-height: 1.4;
}

.subtitle.positive {
  color: $frbt-positive;
}

.subtitle.negative {
  color: $frbt-negative;
}
</style>
