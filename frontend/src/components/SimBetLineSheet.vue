<template>
  <view v-if="visible" class="sim-sheet-root">
    <view class="sim-mask" @tap="$emit('close')"></view>
    <view class="sim-sheet" :class="{ show: visible }">
      <view class="sheet-hd">
        <view class="hd-text">
          <text class="hd-title">亚盘模拟</text>
          <text class="hd-teams">{{ homeTeam }} vs {{ awayTeam }}</text>
        </view>
        <text class="hd-close" @tap="$emit('close')">关闭</text>
      </view>

      <view class="sheet-meta">
        <text class="meta-lab">主盘</text>
        <text class="meta-hc">{{ fmtAhLine(mainHc) }}</text>
        <text class="meta-sep">·</text>
        <text class="meta-dir" :class="f6Direction">{{ dirLabel }}</text>
        <text v-if="refScore != null" class="meta-ref">参考 {{ refScore }}</text>
        <text class="meta-hint">无赔率 · 分=同赔不输评估</text>
      </view>

      <scroll-view class="sheet-body" scroll-y>
        <view class="line-row" v-for="row in board" :key="row.line">
          <view
            class="line-cell"
            :class="cellClass(row.home, row.isMain)"
            @tap="pick(row.home)"
          >
            <text class="cell-side">主 {{ fmtAhLine(row.homeLine) }}</text>
            <text class="cell-score">{{ row.home.safetyScore }}</text>
            <text v-if="row.isMain" class="cell-tag">主盘</text>
          </view>
          <view
            class="line-cell"
            :class="cellClass(row.away, row.isMain)"
            @tap="pick(row.away)"
          >
            <text class="cell-side">客 {{ fmtAhLine(row.awayLine) }}</text>
            <text class="cell-score">{{ row.away.safetyScore }}</text>
            <text v-if="row.isMain" class="cell-tag">主盘</text>
          </view>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { buildLineScoreboard, fmtAhLine, isF6RecommendedSide } from '@/utils/simBet'

const props = defineProps({
  visible: { type: Boolean, default: false },
  homeTeam: { type: String, default: '' },
  awayTeam: { type: String, default: '' },
  mainHc: { type: Number, default: null },
  matches: { type: Array, default: () => [] },
  f6Direction: { type: String, default: 'neutral' },
  refScore: { type: Number, default: null },
  lowKey: { type: String, default: null },
  selectedSide: { type: String, default: null },
  selectedLine: { type: Number, default: null },
})

const emit = defineEmits(['close', 'pick'])

const board = computed(() =>
  buildLineScoreboard({
    ahHandicap: props.mainHc,
    matches: props.matches,
    f6Direction: props.f6Direction,
    refScore: props.refScore,
    lowKey: props.lowKey,
  })
)

const dirLabel = computed(() => {
  const d = props.f6Direction
  if (d === 'upper') return '同赔偏上盘'
  if (d === 'lower') return '同赔偏下盘'
  return '同赔中性'
})

function isSelected(cell) {
  return (
    props.selectedSide === cell.side &&
    props.selectedLine != null &&
    Math.abs(Number(props.selectedLine) - Number(cell.line)) < 1e-9
  )
}

function cellClass(cell, isMain) {
  const rec = isF6RecommendedSide(cell.side, props.f6Direction, props.mainHc, props.lowKey)
  return {
    main: isMain,
    recommend: rec,
    recUpper: rec && props.f6Direction === 'upper',
    recLower: rec && props.f6Direction === 'lower',
    selected: isSelected(cell),
  }
}

function pick(cell) {
  emit('pick', {
    side: cell.side,
    line: cell.line,
    safetyScore: cell.safetyScore,
    scoreSource: cell.source,
    sample: cell.sample,
    notLoseRate: cell.notLoseRate,
    expUnit: cell.expUnit,
  })
}
</script>

<style lang="scss" scoped>
.sim-sheet-root { position: fixed; inset: 0; z-index: 300; pointer-events: none; }
.sim-mask {
  position: absolute; inset: 0; background: rgba(15, 23, 42, 0.45);
  pointer-events: auto;
}
.sim-sheet {
  position: absolute; left: 0; right: 0; bottom: 0;
  max-height: 78vh;
  background: #fff;
  border-radius: 12rpx 12rpx 0 0;
  display: flex; flex-direction: column;
  transform: translateY(100%);
  transition: transform 0.22s ease;
  pointer-events: auto;
  &.show { transform: translateY(0); }
}
.sheet-hd {
  display: flex; justify-content: space-between; align-items: center;
  padding: 28rpx 36rpx 12rpx;
  .hd-title { font-size: 30rpx; font-weight: 600; color: #0f172a; display: block; }
  .hd-teams { font-size: 22rpx; color: #64748b; margin-top: 4rpx; display: block; }
  .hd-close { font-size: 24rpx; color: #0d9488; padding: 8rpx 4rpx 8rpx 16rpx; }
}
.sheet-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8rpx;
  padding: 8rpx 36rpx 16rpx;
  border-bottom: 1rpx solid #e2e8f0;
  .meta-lab { font-size: 22rpx; color: #94a3b8; }
  .meta-hc { font-size: 26rpx; font-weight: 600; color: #0f172a; font-variant-numeric: tabular-nums; }
  .meta-sep { color: #cbd5e1; }
  .meta-dir {
    font-size: 22rpx; padding: 2rpx 10rpx; border-radius: 6rpx; background: #f1f5f9; color: #64748b;
    &.upper { background: #fef2f2; color: #dc2626; }
    &.lower { background: #ecfdf5; color: #059669; }
  }
  .meta-ref { font-size: 22rpx; color: #64748b; }
  .meta-hint { font-size: 20rpx; color: #94a3b8; margin-left: auto; }
}
.sheet-body { flex: 1; max-height: 56vh; padding: 16rpx 28rpx 32rpx; box-sizing: border-box; }
.line-row {
  display: flex; gap: 12rpx; margin-bottom: 12rpx;
}
.line-cell {
  flex: 1;
  position: relative;
  background: #f8fafc;
  border: 2rpx solid #e2e8f0;
  border-radius: 6rpx;
  padding: 18rpx 16rpx;
  display: flex; flex-direction: column; align-items: center; gap: 6rpx;
  &.main { background: #f1f5f9; }
  &.recommend.recUpper { border-color: rgba(#dc2626, 0.55); background: rgba(#dc2626, 0.04); }
  &.recommend.recLower { border-color: rgba(#059669, 0.55); background: rgba(#059669, 0.04); }
  &.selected {
    border-color: #0d9488;
    background: #f0fdfa;
  }
  .cell-side { font-size: 24rpx; color: #334155; }
  .cell-score {
    font-size: 36rpx; font-weight: 700; color: #0f172a;
    font-variant-numeric: tabular-nums;
  }
  .cell-tag {
    position: absolute; top: 6rpx; right: 8rpx;
    font-size: 18rpx; color: #64748b;
  }
}
</style>
