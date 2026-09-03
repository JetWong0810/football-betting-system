<template>
  <view v-if="data && (data.items || []).length" class="kelly-hint">
    <view class="kh-head">
      <text class="kh-title">官方凯利</text>
      <text class="kh-tag">参考</text>
    </view>
    <view class="kh-row kh-head-row">
      <text class="kh-lab"></text>
      <text class="kh-num">官方</text>
      <text class="kh-num">主流</text>
      <text class="kh-delta">差</text>
      <text class="kh-flag"></text>
    </view>
    <view
      v-for="item in data.items"
      :key="item.key"
      class="kh-row"
    >
      <text class="kh-lab">{{ item.label }}</text>
      <text class="kh-num">{{ fmt(item.official) }}</text>
      <text class="kh-num">{{ fmt(item.mainstream) }}</text>
      <text class="kh-delta" :class="deltaClass(item.delta)">{{ fmtDelta(item.delta) }}</text>
      <text class="kh-flag" :class="item.tag === '偏松' ? 'loose' : item.tag === '偏紧' ? 'tight' : ''">{{ item.tag || '' }}</text>
    </view>
    <text class="kh-line">{{ data.headline }}</text>
    <text class="kh-note">高于主流=该项赔付更松，可能迎合该结果。不进因子。</text>
  </view>
</template>

<script setup>
defineProps({
  data: { type: Object, default: null },
})

function fmt(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}

function fmtDelta(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  return (n > 0 ? '+' : '') + n.toFixed(2)
}

function deltaClass(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || Math.abs(n) < 0.03) return ''
  return n > 0 ? 'up' : 'down'
}
</script>

<style lang="scss" scoped>
.kelly-hint {
  margin: 16rpx 0 0;
  padding: 16rpx 18rpx;
  background: #f8fafb;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
}
.kh-head {
  display: flex;
  align-items: center;
  gap: 10rpx;
  margin-bottom: 10rpx;
}
.kh-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #0f766e;
}
.kh-tag {
  margin-left: auto;
  font-size: 18rpx;
  color: #0f766e;
  background: #ccfbf1;
  border-radius: 6rpx;
  padding: 2rpx 8rpx;
}
.kh-row {
  display: flex;
  align-items: center;
  gap: 8rpx;
  padding: 4rpx 0;
  font-size: 22rpx;
}
.kh-head-row {
  color: #94a3b8;
  font-size: 20rpx;
}
.kh-lab {
  width: 72rpx;
  color: #475569;
  flex-shrink: 0;
}
.kh-num {
  width: 88rpx;
  text-align: right;
  color: #1e293b;
  font-variant-numeric: tabular-nums;
}
.kh-delta {
  width: 88rpx;
  text-align: right;
  color: #64748b;
  font-variant-numeric: tabular-nums;
  &.up { color: #c2410c; }
  &.down { color: #0f766e; }
}
.kh-flag {
  width: 64rpx;
  text-align: right;
  font-size: 20rpx;
  color: #94a3b8;
  &.loose {
    color: #9a3412;
  }
  &.tight {
    color: #64748b;
  }
}
.kh-line {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #1e293b;
  line-height: 1.45;
}
.kh-note {
  display: block;
  margin-top: 6rpx;
  font-size: 20rpx;
  color: #94a3b8;
  line-height: 1.4;
}
</style>
