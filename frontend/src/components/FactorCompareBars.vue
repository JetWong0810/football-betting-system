<template>
  <view>
  <view v-if="isOdds && oddsRows.length" class="odds">
    <view class="od-row" v-for="row in oddsRows" :key="row.label" :class="{ hi: row.low }">
      <text class="od-lab">{{ row.label }}</text>
      <text class="od-n">{{ row.open }}</text>
      <text class="od-ar" :class="row.side">{{ row.arrow }}</text>
      <text class="od-n" :class="row.side">{{ row.close }}</text>
      <view class="od-track">
        <view class="od-mid" />
        <view class="od-bar" :class="row.side" :style="row.barStyle" />
      </view>
      <text class="od-d" :class="row.side">{{ row.diffLabel }}</text>
      <text v-if="row.low" class="od-tag">低赔</text>
      <text v-else class="od-tag od-tag-sp" />
    </view>
  </view>
  <view v-else-if="isStack && stackSegs.length" class="stack">
    <view class="stack-track">
      <view
        v-for="seg in stackSegs"
        :key="seg.label"
        class="seg"
        :class="seg.side"
        :style="{ width: seg.pct + '%' }"
      />
    </view>
    <view class="legend">
      <view class="lg" v-for="seg in stackSegs" :key="'l' + seg.label">
        <view class="pip" :class="seg.side" />
        <text class="lg-t" :class="seg.side">{{ seg.label }} {{ seg.value }}</text>
        <text class="lg-p">{{ seg.pctLabel }}</text>
        <text class="lg-s" v-if="seg.suffix">{{ seg.suffix }}</text>
      </view>
    </view>
  </view>
  <view v-else-if="rows.length" class="cmp">
    <view class="row" v-for="row in rows" :key="row.label">
      <text class="lab">{{ row.label }}</text>
      <view class="track" :class="row.side">
        <view class="fill" :class="row.side" :style="{ width: row.pct + '%' }" />
      </view>
      <text class="val" :class="row.side">{{ row.display }}</text>
    </view>
  </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  chart: { type: Object, default: () => ({}) },
})

const isStack = computed(() => props.chart?.type === 'stack')
const isOdds = computed(() => props.chart?.type === 'odds')

const oddsRows = computed(() => {
  const items = props.chart?.items || []
  const maxAbs = Math.max(0.05, ...items.map(i => Math.abs(Number(i.diff) || 0)))
  return items.map((it) => {
    const diff = Number(it.diff) || 0
    const pct = Math.abs(diff) <= 0.02
      ? 3
      : Math.min(46, Math.max(6, (Math.abs(diff) / maxAbs) * 46))
    let barStyle
    if (Math.abs(diff) <= 0.02) {
      barStyle = { left: '48%', width: '4%' }
    } else if (diff < 0) {
      barStyle = { left: `${50 - pct}%`, width: `${pct}%` }
    } else {
      barStyle = { left: '50%', width: `${pct}%` }
    }
    const side = it.side === 'lower' ? 'lower' : it.side === 'neutral' ? 'neutral' : 'upper'
    return {
      label: it.label,
      open: Number(it.open).toFixed(2),
      close: Number(it.close).toFixed(2),
      low: !!it.low,
      side,
      arrow: diff < -0.02 ? '↓' : diff > 0.02 ? '↑' : '→',
      diffLabel: `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`,
      barStyle,
    }
  })
})

const stackSegs = computed(() => {
  const items = props.chart?.items || []
  const total = Number(props.chart?.total) || items.reduce((s, i) => s + (Number(i.value) || 0), 0)
  if (!total) return []
  return items
    .filter(it => Number(it.value) > 0)
    .map((it) => {
      const value = Number(it.value) || 0
      const pct = (value / total) * 100
      return {
        label: it.label,
        value,
        side: it.side === 'lower' ? 'lower' : it.side === 'neutral' ? 'neutral' : 'upper',
        suffix: it.suffix || '',
        pct: Math.max(pct < 2 && pct > 0 ? 2 : pct, 0),
        pctLabel: `${Math.round(pct)}%`,
      }
    })
})

const rows = computed(() => {
  const t = props.chart?.type
  if (t === 'stack' || t === 'odds') return []
  const items = props.chart?.items || []
  const max = Number(props.chart?.max) || Math.max(...items.map(i => Number(i.value) || 0), 1)
  const unit = props.chart?.unit || ''
  return items.map((it) => {
    const value = Number(it.value) || 0
    const suffix = it.suffix || ''
    const num = Number.isInteger(value) ? String(value) : value.toFixed(2)
    const display = suffix && /[€￥$万]/.test(suffix)
      ? suffix
      : `${num}${unit}${suffix}`
    return {
      label: it.label,
      side: it.side === 'lower' ? 'lower' : 'upper',
      pct: Math.max(8, Math.min(100, max > 0 ? (value / max) * 100 : 0)),
      display,
    }
  })
})
</script>

<style lang="scss" scoped>
.cmp {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  margin: 8rpx 0 6rpx 28rpx;
}
.row {
  display: flex;
  align-items: center;
  gap: 12rpx;
}
.lab {
  width: 120rpx;
  flex-shrink: 0;
  font-size: 20rpx;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track {
  flex: 1;
  height: 8rpx;
  border-radius: 6rpx;
  overflow: hidden;
  &.upper { background: #fee2e2; }
  &.lower { background: #d1fae5; }
}
.fill {
  height: 100%;
  border-radius: 6rpx;
  transition: width 0.45s ease-out;
  &.upper { background: #dc2626; }
  &.lower { background: #059669; }
}
.val {
  width: 140rpx;
  flex-shrink: 0;
  text-align: right;
  font-size: 20rpx;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  &.upper { color: #dc2626; }
  &.lower { color: #059669; }
}

.stack {
  margin: 8rpx 0 6rpx 28rpx;
}
.stack-track {
  display: flex;
  height: 10rpx;
  border-radius: 6rpx;
  overflow: hidden;
  background: #e2e8f0;
}
.seg {
  height: 100%;
  &.upper { background: #dc2626; }
  &.lower { background: #059669; }
  &.neutral { background: #94a3b8; }
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx 20rpx;
  margin-top: 10rpx;
}
.lg {
  display: flex;
  align-items: center;
  gap: 6rpx;
}
.pip {
  width: 10rpx;
  height: 10rpx;
  border-radius: 6rpx;
  flex-shrink: 0;
  &.upper { background: #dc2626; }
  &.lower { background: #059669; }
  &.neutral { background: #94a3b8; }
}
.lg-t {
  font-size: 20rpx;
  font-weight: 600;
  &.upper { color: #dc2626; }
  &.lower { color: #059669; }
  &.neutral { color: #64748b; }
}
.lg-p {
  font-size: 20rpx;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}
.lg-s {
  font-size: 20rpx;
  color: #94a3b8;
}

.odds {
  margin: 8rpx 0 6rpx 28rpx;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}
.od-row {
  display: flex;
  align-items: center;
  gap: 8rpx;
  &.hi .od-lab { color: #dc2626; font-weight: 600; }
}
.od-lab {
  width: 32rpx;
  flex-shrink: 0;
  font-size: 20rpx;
  color: #64748b;
  font-weight: 600;
}
.od-n {
  width: 56rpx;
  flex-shrink: 0;
  font-size: 20rpx;
  color: #475569;
  font-variant-numeric: tabular-nums;
  &.upper { color: #dc2626; font-weight: 600; }
  &.lower { color: #059669; font-weight: 600; }
  &.neutral { color: #64748b; }
}
.od-ar {
  width: 24rpx;
  flex-shrink: 0;
  text-align: center;
  font-size: 18rpx;
  &.upper { color: #dc2626; }
  &.lower { color: #059669; }
  &.neutral { color: #94a3b8; }
}
.od-track {
  position: relative;
  flex: 1;
  height: 8rpx;
  background: #f1f5f9;
  border-radius: 6rpx;
  overflow: hidden;
}
.od-mid {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2rpx;
  background: #cbd5e1;
  z-index: 1;
}
.od-bar {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 6rpx;
  &.upper { background: #dc2626; }
  &.lower { background: #059669; }
  &.neutral { background: #cbd5e1; }
}
.od-d {
  width: 72rpx;
  flex-shrink: 0;
  text-align: right;
  font-size: 20rpx;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  &.upper { color: #dc2626; }
  &.lower { color: #059669; }
  &.neutral { color: #94a3b8; }
}
.od-tag {
  width: 52rpx;
  flex-shrink: 0;
  font-size: 18rpx;
  line-height: 1.4;
  text-align: center;
  color: #dc2626;
  background: #fef2f2;
  border-radius: 6rpx;
}
.od-tag-sp {
  background: transparent;
}
</style>
