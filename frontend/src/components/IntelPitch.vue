<template>
  <view class="pitch-wrap">
    <view class="bar top">
      <text class="bar-team">{{ homeName }}</text>
      <text v-if="homeForm" class="bar-form">{{ homeForm }}</text>
      <text v-if="homeConf != null" class="bar-ai">模{{ homeConf }}%</text>
      <text v-if="homeMeta" class="bar-meta">{{ homeMeta }}</text>
    </view>
    <view class="pitch">
      <view class="mark mid" />
      <view class="mark circle" />
      <view class="mark spot" />
      <view class="mark box top" />
      <view class="mark six top" />
      <view class="mark spot-pen top" />
      <view class="mark box bot" />
      <view class="mark six bot" />
      <view class="mark spot-pen bot" />

      <view class="half home">
        <view v-for="(row, ri) in homeLines" :key="'h' + ri" class="line" :class="'n' + row.length">
          <view
            v-for="p in row"
            :key="'h-' + p.id"
            class="slot"
            :class="{ ace: p.role === '主力' }"
            @tap.stop="emit('pick', p)"
          >
            <text v-if="scoreText(p)" class="sc" :class="scoreTone(p)">{{ scoreText(p) }}</text>
            <view class="face">
              <text class="kit">{{ kit(p) }}</text>
            </view>
            <text class="nm">{{ label(p) }}</text>
          </view>
        </view>
      </view>

      <view class="half away">
        <view v-for="(row, ri) in awayLines" :key="'a' + ri" class="line" :class="'n' + row.length">
          <view
            v-for="p in row"
            :key="'a-' + p.id"
            class="slot"
            :class="{ ace: p.role === '主力' }"
            @tap.stop="emit('pick', p)"
          >
            <text v-if="scoreText(p)" class="sc" :class="scoreTone(p)">{{ scoreText(p) }}</text>
            <view class="face">
              <text class="kit">{{ kit(p) }}</text>
            </view>
            <text class="nm">{{ label(p) }}</text>
          </view>
        </view>
      </view>
    </view>
    <view class="bar bot">
      <text class="bar-team">{{ awayName }}</text>
      <text v-if="awayForm" class="bar-form">{{ awayForm }}</text>
      <text v-if="awayConf != null" class="bar-ai">模{{ awayConf }}%</text>
      <text v-if="awayMeta" class="bar-meta">{{ awayMeta }}</text>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  homeName: { type: String, default: '' },
  awayName: { type: String, default: '' },
  homeForm: { type: String, default: '' },
  awayForm: { type: String, default: '' },
  homeMeta: { type: String, default: '' },
  awayMeta: { type: String, default: '' },
  homeConf: { type: Number, default: null },
  awayConf: { type: Number, default: null },
  homePlayers: { type: Array, default: () => [] },
  awayPlayers: { type: Array, default: () => [] },
})
const emit = defineEmits(['pick'])

function parseLines(formation) {
  const parts = String(formation || '')
    .split(/[-–—]/)
    .map((x) => Number(x))
    .filter((n) => n > 0 && n < 8)
  if (!parts.length) return [1, 4, 3, 3]
  const sum = parts.reduce((a, b) => a + b, 0)
  if (sum === 10 || sum === 11) return sum === 11 ? parts : [1, ...parts]
  return [1, ...parts]
}

function assignRows(players, formation) {
  const xi = (players || []).filter((p) => p.inXi).slice(0, 11)
  const lines = parseLines(formation)
  const rows = []
  let i = 0
  for (const n of lines) {
    const row = []
    for (let k = 0; k < n && i < xi.length; k += 1, i += 1) row.push(xi[i])
    if (row.length) rows.push(row)
  }
  if (i < xi.length) rows.push(xi.slice(i))
  return rows
}

const homeLines = computed(() => assignRows(props.homePlayers, props.homeForm))
const awayLines = computed(() => assignRows(props.awayPlayers, props.awayForm))

function kit(n) {
  if (n.num != null && n.num !== '') return n.num
  const s = label(n)
  return s.slice(0, 1).toUpperCase() || '?'
}

function label(n) {
  const s = String(n.short || '').trim()
  if (s && !/^(jr|sr|ii|iii)\.?$/i.test(s)) return s
  const parts = String(n.name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2 && /^(jr|sr)\.?$/i.test(parts[parts.length - 1].replace(/\./g, ''))) {
    return parts[parts.length - 2]
  }
  return s || parts[parts.length - 1] || ''
}

function scoreText(n) {
  if (n.aiScore != null) {
    const v = Number(n.aiScore)
    if (Number.isNaN(v)) return ''
    const pct = v <= 1.5 ? v * 100 : v
    return `${Math.round(pct)}%`
  }
  if (n.score == null) return ''
  const v = Number(n.score)
  return Number.isNaN(v) ? '' : v.toFixed(1)
}

function scoreTone(n) {
  if (n.aiScore != null) {
    const v = Number(n.aiScore)
    const pct = v <= 1.5 ? v * 100 : v
    if (pct >= 70) return 'hi'
    if (pct >= 50) return 'mid'
    return 'lo'
  }
  const s = Number(n.score)
  if (s >= 7.2) return 'hi'
  if (s >= 6.5) return 'mid'
  return 'lo'
}
</script>

<style lang="scss" scoped>
.pitch-wrap { margin: 8rpx 0 4rpx; }
.bar {
  display: flex; align-items: baseline; gap: 8rpx;
  padding: 2rpx 4rpx 10rpx;
  min-width: 0;
  &.bot { padding: 12rpx 4rpx 0; }
}
.bar-team {
  font-size: 24rpx; font-weight: 700; color: #134e4a;
  flex-shrink: 0;
}
.bar-form {
  font-size: 18rpx; font-weight: 650; color: #0f766e;
  background: #ccfbf1; border-radius: 6rpx; padding: 0 8rpx;
  font-variant-numeric: tabular-nums; flex-shrink: 0;
}
.bar-meta {
  font-size: 18rpx; color: #64748b;
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.bar-ai {
  font-size: 18rpx; font-weight: 650; color: #b45309;
  background: #fff7ed; border-radius: 6rpx; padding: 0 8rpx;
  font-variant-numeric: tabular-nums; flex-shrink: 0;
}

.pitch {
  position: relative;
  height: 1120rpx;
  border-radius: 6rpx;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background:
    repeating-linear-gradient(
      180deg,
      #1f6b3d 0,
      #1f6b3d 80rpx,
      #1a5f36 80rpx,
      #1a5f36 160rpx
    );
  box-shadow: inset 0 0 0 3rpx rgba(236, 250, 248, 0.18);
}

.mark {
  position: absolute; pointer-events: none; z-index: 0;
  border: 2rpx solid rgba(236, 250, 248, 0.28);
}
.mark.mid {
  left: 0; right: 0; top: 50%; height: 0;
  border-top-width: 2rpx;
}
.mark.circle {
  width: 148rpx; height: 148rpx; border-radius: 50%;
  left: 50%; top: 50%; transform: translate(-50%, -50%);
}
.mark.spot {
  width: 8rpx; height: 8rpx; border-radius: 50%;
  left: 50%; top: 50%; transform: translate(-50%, -50%);
  background: rgba(236, 250, 248, 0.5); border: 0;
}
.mark.spot-pen {
  width: 6rpx; height: 6rpx; border-radius: 50%;
  left: 50%; transform: translateX(-50%);
  background: rgba(236, 250, 248, 0.4); border: 0;
  &.top { top: 70rpx; }
  &.bot { bottom: 70rpx; }
}
.mark.box {
  left: 18%; right: 18%; height: 108rpx;
  &.top { top: 0; border-top: 0; }
  &.bot { bottom: 0; border-bottom: 0; }
}
.mark.six {
  left: 31%; right: 31%; height: 46rpx;
  &.top { top: 0; border-top: 0; }
  &.bot { bottom: 0; border-bottom: 0; }
}

.half {
  position: relative;
  z-index: 1;
  flex: 1 1 50%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 8rpx 4rpx 28rpx;
}
.half.away {
  flex-direction: column-reverse;
  padding: 28rpx 4rpx 8rpx;
}

.line {
  display: flex;
  justify-content: space-evenly;
  align-items: center;
  min-width: 0;
  &.n1 { justify-content: center; }
  &.n2 { padding: 0 16%; }
  &.n3 { padding: 0 6%; }
}

.slot {
  flex: 0 1 18%;
  max-width: 120rpx;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rpx;
}
.line.n1 .slot { flex-basis: 22%; }
.line.n4 .slot { max-width: 104rpx; }
.line.n5 .slot { max-width: 88rpx; }

.face {
  width: 48rpx; height: 48rpx; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  border: 2rpx solid rgba(236, 250, 248, 0.42);
  box-sizing: border-box;
}
.home .face { background: #efe8d8; }
.away .face { background: #243044; }
.ace .face { box-shadow: 0 0 0 2rpx #c9a227; }
.kit {
  font-size: 20rpx; font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.home .kit { color: #243044; }
.away .kit { color: #f4f1ea; }

.sc {
  font-size: 20rpx; font-weight: 700;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  color: #d7e8dc;
  &.hi { color: #b7f0c8; }
  &.mid { color: #f3d98a; }
  &.lo { color: #f5b8b8; }
}
.nm {
  width: 100%;
  font-size: 18rpx; font-weight: 650; color: #e7f6ee;
  text-align: center;
  line-height: 1.15;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
