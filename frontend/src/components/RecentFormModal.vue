<template>
  <teleport to="body">
    <view v-if="open" class="rf-portal">
      <view class="app-mask rf-mask" @tap="close" />
      <view class="app-modal rf-modal show" @tap.stop>
        <view class="rf-head">
          <text class="rf-title">近期战绩</text>
          <text class="rf-close" @tap="close">关闭</text>
        </view>
        <view class="rf-body">
          <view class="rf-section">
            <text class="rf-section-title">{{ homeName }} 近期战绩</text>
            <view class="rf-filters">
              <view class="rf-chip" :class="{ on: homeFilters.venueOnly }" @tap="homeFilters.venueOnly = !homeFilters.venueOnly">
                <text>同主客</text>
              </view>
              <view class="rf-chip" :class="{ on: homeFilters.sameComp }" @tap="homeFilters.sameComp = !homeFilters.sameComp">
                <text>同赛事</text>
              </view>
              <view class="rf-chip" :class="{ on: homeFilters.count === 10 }" @tap="homeFilters.count = 10">
                <text>10场</text>
              </view>
              <view class="rf-chip" :class="{ on: homeFilters.count === 15 }" @tap="homeFilters.count = 15">
                <text>15场</text>
              </view>
            </view>
            <view class="h2h-table">
              <view class="h2h-th">
                <view class="col-event">赛事</view>
                <view class="col-teams">
                  <view class="team-left">主队</view>
                  <view class="score-wrap">比分</view>
                  <view class="team-right">客队</view>
                </view>
                <view class="col-asian">亚指</view>
              </view>
              <view v-for="(row, i) in homeVisible" :key="'h' + i" class="h2h-tr">
                <view class="col-event">
                  <text class="event-date">{{ row.dateShort }}</text>
                  <text class="event-name">{{ row.competition }}</text>
                </view>
                <view class="col-teams">
                  <view class="team-left">
                    <text class="team-name" :class="teamClass(row, 'home')">{{ row.homeTeam }}</text>
                  </view>
                  <view class="score-wrap">
                    <text class="match-score">{{ row.score }}</text>
                    <text v-if="row.halftimeScore" class="halftime-score">{{ row.halftimeScore }}</text>
                  </view>
                  <view class="team-right">
                    <text class="team-name" :class="teamClass(row, 'away')">{{ row.awayTeam }}</text>
                  </view>
                </view>
                <view class="col-asian">
                  <text class="data-value" :class="row.asianClass">{{ row.asian || '-' }}</text>
                  <text class="data-label" :class="row.asianClass">{{ row.asianLabel }}</text>
                </view>
              </view>
              <view v-if="!homeVisible.length" class="rf-empty"><text>无近期战绩</text></view>
            </view>
          </view>

          <view class="rf-section">
            <text class="rf-section-title">{{ awayName }} 近期战绩</text>
            <view class="rf-filters">
              <view class="rf-chip" :class="{ on: awayFilters.venueOnly }" @tap="awayFilters.venueOnly = !awayFilters.venueOnly">
                <text>同主客</text>
              </view>
              <view class="rf-chip" :class="{ on: awayFilters.sameComp }" @tap="awayFilters.sameComp = !awayFilters.sameComp">
                <text>同赛事</text>
              </view>
              <view class="rf-chip" :class="{ on: awayFilters.count === 10 }" @tap="awayFilters.count = 10">
                <text>10场</text>
              </view>
              <view class="rf-chip" :class="{ on: awayFilters.count === 15 }" @tap="awayFilters.count = 15">
                <text>15场</text>
              </view>
            </view>
            <view class="h2h-table">
              <view class="h2h-th">
                <view class="col-event">赛事</view>
                <view class="col-teams">
                  <view class="team-left">主队</view>
                  <view class="score-wrap">比分</view>
                  <view class="team-right">客队</view>
                </view>
                <view class="col-asian">亚指</view>
              </view>
              <view v-for="(row, i) in awayVisible" :key="'a' + i" class="h2h-tr">
                <view class="col-event">
                  <text class="event-date">{{ row.dateShort }}</text>
                  <text class="event-name">{{ row.competition }}</text>
                </view>
                <view class="col-teams">
                  <view class="team-left">
                    <text class="team-name" :class="teamClass(row, 'home')">{{ row.homeTeam }}</text>
                  </view>
                  <view class="score-wrap">
                    <text class="match-score">{{ row.score }}</text>
                    <text v-if="row.halftimeScore" class="halftime-score">{{ row.halftimeScore }}</text>
                  </view>
                  <view class="team-right">
                    <text class="team-name" :class="teamClass(row, 'away')">{{ row.awayTeam }}</text>
                  </view>
                </view>
                <view class="col-asian">
                  <text class="data-value" :class="row.asianClass">{{ row.asian || '-' }}</text>
                  <text class="data-label" :class="row.asianClass">{{ row.asianLabel }}</text>
                </view>
              </view>
              <view v-if="!awayVisible.length" class="rf-empty"><text>无近期战绩</text></view>
            </view>
          </view>
        </view>
      </view>
    </view>
  </teleport>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  homeName: { type: String, default: '主队' },
  awayName: { type: String, default: '客队' },
  homeRecent: { type: Array, default: () => [] },
  awayRecent: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

function close() {
  emit('close')
}

const homeFilters = reactive({ venueOnly: false, sameComp: false, count: 10 })
const awayFilters = reactive({ venueOnly: false, sameComp: false, count: 10 })

watch(() => props.open, (v) => {
  if (!v) return
  homeFilters.venueOnly = false
  homeFilters.sameComp = false
  homeFilters.count = 10
  awayFilters.venueOnly = false
  awayFilters.sameComp = false
  awayFilters.count = 10
})

function teamClass(row, side) {
  if (row.homeScore === row.awayScore) return 'team-draw'
  if (side === 'home') return row.homeScore > row.awayScore ? 'team-win' : 'team-lose'
  return row.awayScore > row.homeScore ? 'team-win' : 'team-lose'
}

function formatRecent(m, i) {
  const matchText = m.match || ''
  const scoreMatch = matchText.match(/(\d+):(\d+)/)
  const homeScore = scoreMatch ? parseInt(scoreMatch[1], 10) : 0
  const awayScore = scoreMatch ? parseInt(scoreMatch[2], 10) : 0
  const teams = matchText.replace(/\d+:\d+/, '|').split('|')
  const asianResult = (m.asianResult || '').trim()
  const ouResult = (m.ouResult || '').trim()
  const half = (m.halfScore || '').trim()
  return {
    id: i,
    dateShort: m.date,
    competition: m.competition || '-',
    homeTeam: teams[0] || '',
    awayTeam: teams[1] || '',
    score: scoreMatch ? `${homeScore}:${awayScore}` : '-',
    halftimeScore: half && half !== 'VS' ? `(${half})` : '',
    homeScore,
    awayScore,
    asian: m.handicap || '',
    asianClass: asianResult === '赢' || asianResult === '赢半' ? 'win'
      : asianResult === '输' || asianResult === '输半' ? 'lose' : 'draw',
    asianLabel: asianResult,
    ouClass: ouResult === '大' ? 'big' : ouResult === '小' ? 'small' : '',
    ouLabel: ouResult,
  }
}

function mostCommonComp(list) {
  const counts = {}
  list.forEach((m) => {
    if (m.competition) counts[m.competition] = (counts[m.competition] || 0) + 1
  })
  let max = ''
  let maxCount = 0
  Object.entries(counts).forEach(([k, v]) => {
    if (v > maxCount) {
      max = k
      maxCount = v
    }
  })
  return max
}

function applyFilters(list, teamName, side, filters) {
  let rows = list
  if (filters.venueOnly && teamName) {
    rows = side === 'home'
      ? rows.filter((m) => m.homeTeam && m.homeTeam.includes(teamName))
      : rows.filter((m) => m.awayTeam && m.awayTeam.includes(teamName))
  }
  if (filters.sameComp) {
    const comp = mostCommonComp(rows)
    if (comp) rows = rows.filter((m) => m.competition === comp)
  }
  return rows.slice(0, filters.count)
}

const homeFormatted = computed(() => (props.homeRecent || []).map((m, i) => formatRecent(m, i)))
const awayFormatted = computed(() => (props.awayRecent || []).map((m, i) => formatRecent(m, i)))
const homeVisible = computed(() => applyFilters(homeFormatted.value, props.homeName, 'home', homeFilters))
const awayVisible = computed(() => applyFilters(awayFormatted.value, props.awayName, 'away', awayFilters))
</script>

<style lang="scss" scoped>
.rf-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 210;
}
.rf-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  right: auto;
  width: min(398px, calc(100vw - 32px));
  max-height: min(88vh, 720px);
  background: #fff;
  border-radius: 12rpx;
  z-index: 211;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 16rpx 48rpx rgba(15, 23, 42, 0.18);
  transform: translate(-50%, -50%);
}
.rf-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16rpx 20rpx 12rpx;
  border-bottom: 1rpx solid #e2e8f0;
  flex-shrink: 0;
}
.rf-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1e293b;
}
.rf-close {
  font-size: 24rpx;
  color: #64748b;
  padding: 4rpx 0 4rpx 12rpx;
}
.rf-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: min(70vh, 560px);
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}
.rf-section {
  padding: 12rpx 0 8rpx;
}
.rf-section + .rf-section {
  border-top: 1rpx solid #e2e8f0;
}
.rf-section-title {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: #111827;
  padding: 4rpx 28rpx 10rpx;
}
.rf-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  padding: 0 28rpx 10rpx;
}
.rf-chip {
  font-size: 20rpx;
  color: #9ca3af;
  background: transparent;
  border: none;
  border-radius: 6rpx;
  padding: 4rpx 12rpx;
  &.on {
    color: #fff;
    background: #0d9488;
  }
}
.rf-empty {
  padding: 24rpx 16rpx;
  text-align: center;
  font-size: 22rpx;
  color: #94a3b8;
}
.h2h-table { background: #fff; }
.h2h-th, .h2h-tr {
  display: flex;
  align-items: center;
  padding: 12rpx 28rpx;
}
.h2h-th {
  font-size: 20rpx;
  color: #9ca3af;
}
.h2h-tr { font-size: 22rpx; }
.col-event {
  width: 90rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2rpx;
  padding-right: 8rpx;
}
.event-date {
  font-size: 20rpx;
  color: #6b7280;
  white-space: nowrap;
  line-height: 1.4;
}
.event-name {
  font-size: 20rpx;
  color: #111827;
  white-space: nowrap;
  line-height: 1.4;
}
.col-teams {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.team-left,
.team-right {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.team-left {
  display: flex;
  justify-content: flex-end;
  padding-right: 8rpx;
}
.team-right {
  display: flex;
  justify-content: flex-start;
  padding-left: 8rpx;
}
.team-name {
  max-width: 100%;
  font-size: 22rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
  &.team-win { color: #ef4444; }
  &.team-lose { color: #10b981; }
  &.team-draw { color: #374151; }
}
.score-wrap {
  width: 80rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2rpx;
}
.match-score { font-size: 24rpx; color: #111827; }
.halftime-score { font-size: 20rpx; color: #9ca3af; }
.col-asian {
  width: 72rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2rpx;
}
.data-value {
  font-size: 22rpx;
  color: #111827;
  &.win { color: #ef4444; }
  &.lose { color: #10b981; }
}
.data-label {
  font-size: 20rpx;
  &.win { color: #ef4444; }
  &.lose { color: #10b981; }
}
</style>
