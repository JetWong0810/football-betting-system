<template>
  <view class="bd-page">
    <view class="bd-top">
      <view class="bd-note">北单场次。盘口赔率、交锋、近期战绩不会定时抓取,进入某场聊天、需要时再说"抓取本场最新盘口赔率"或"关联本场交锋和近期战绩"才会抓取并存库。</view>
      <scroll-view class="bd-leagues" scroll-x>
        <view class="bd-leagues-row">
          <text class="bd-chip" :class="{ on: !league }" @tap="league = ''">全部 {{ matches.length }}</text>
          <text v-for="l in leagues" :key="l.name" class="bd-chip" :class="{ on: league === l.name }" @tap="league = l.name">{{ l.name }} {{ l.count }}</text>
        </view>
      </scroll-view>
      <view class="bd-bar">
        <text class="bd-tab" :class="{ on: show === 'todo' }" @tap="show = 'todo'">未开赛</text>
        <text class="bd-tab" :class="{ on: show === 'done' }" @tap="show = 'done'">已开赛</text>
        <text class="bd-refresh" @tap="load(true)">{{ loading ? '刷新中…' : '刷新列表' }}</text>
      </view>
    </view>

    <scroll-view class="bd-list" scroll-y>
      <view class="bd-inner">
        <view v-if="loading && !matches.length" class="bd-state">加载中…</view>
        <view v-else-if="errText" class="bd-state">{{ errText }}</view>
        <view v-else-if="!shown.length" class="bd-state">暂无场次</view>
        <view v-for="g in groups" :key="g.day">
          <text class="bd-day">{{ g.day }}</text>
          <view v-for="m in g.items" :key="m.matchId" class="bd-card" @tap="open(m)">
            <view class="bd-row1">
              <text class="bd-lg">{{ m.league }}</text>
              <text class="bd-time">{{ (m.kickoff || '').slice(11) }}</text>
              <text class="bd-num">场次 {{ m.num }}</text>
              <text v-if="m.score" class="bd-score">{{ m.score }}</text>
            </view>
            <view class="bd-row2">
              <text class="bd-team">{{ m.homeTeam }}</text>
              <text class="bd-vs">vs</text>
              <text class="bd-team r">{{ m.awayTeam }}</text>
            </view>
            <view class="bd-row3">
              <text v-if="m.ahText" class="bd-tag">亚盘 {{ m.ahText }}</text>
              <text v-if="m.rq" class="bd-tag dim">北单让球 {{ m.rq }}</text>
            </view>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { requireAuth } from '@/utils/auth'
import { request } from '@/utils/http'

const matches = ref([])
const leagues = ref([])
const league = ref('')
const show = ref('todo')
const loading = ref(false)
const errText = ref('')

const nowSec = () => Math.floor(Date.now() / 1000)
const shown = computed(() => matches.value.filter((m) => {
  if (league.value && m.league !== league.value) return false
  const started = m.score || (m.kickoffTs && m.kickoffTs <= nowSec())
  return show.value === 'done' ? !!started : !started
}))
const groups = computed(() => {
  const map = new Map()
  for (const m of shown.value) {
    const d = (m.kickoff || '').slice(0, 10)
    if (!map.has(d)) map.set(d, [])
    map.get(d).push(m)
  }
  return [...map.entries()].map(([day, items]) => ({ day, items }))
})

async function load(force = false) {
  if (loading.value) return
  loading.value = true
  errText.value = ''
  try {
    const r = await request({ url: `/api/bd/matches${force ? '?refresh=1' : ''}`, timeout: 40000 })
    matches.value = r.matches || []
    leagues.value = r.leagues || []
    const st = r.listStatus || {}
    if (st.ok === false && matches.value.length) uni.showToast({ title: '列表刷新失败,显示已存数据', icon: 'none' })
    if (!matches.value.length && st.ok === false) errText.value = '北单列表获取失败,稍后再试'
  } catch (e) {
    errText.value = '北单列表加载失败'
  } finally {
    loading.value = false
  }
}

function open(m) {
  const q = [
    `matchId=${encodeURIComponent(m.matchId)}`,
    `home=${encodeURIComponent(m.homeTeam)}`,
    `away=${encodeURIComponent(m.awayTeam)}`,
    `league=${encodeURIComponent(m.league || '')}`,
    `time=${encodeURIComponent((m.kickoff || '').slice(5))}`,
  ].join('&')
  uni.navigateTo({ url: `/pages/predict/match-chat?${q}` })
}

onLoad(() => {
  if (!requireAuth()) return
  load(false)
})
</script>

<style lang="scss" scoped>
.bd-page { display: flex; flex-direction: column; height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px)); background: #f0fdf9; }
.bd-top { flex-shrink: 0; background: #fff; border-bottom: 1rpx solid #e2e8f0; padding: 14rpx 24rpx 12rpx; }
.bd-note { font-size: 21rpx; color: #64748b; line-height: 1.5; margin-bottom: 12rpx; }
.bd-leagues { white-space: nowrap; }
.bd-leagues-row { display: inline-flex; gap: 10rpx; }
.bd-chip { font-size: 22rpx; color: #475569; padding: 6rpx 18rpx; border-radius: 6rpx; background: #f1f5f9; border: 1rpx solid transparent; white-space: nowrap;
  &.on { color: #0f766e; background: #f0fdfa; border-color: #5eead4; font-weight: 600; } }
.bd-bar { display: flex; align-items: center; gap: 12rpx; margin-top: 12rpx; }
.bd-tab { font-size: 24rpx; color: #475569; padding: 6rpx 22rpx; border-radius: 6rpx; background: #f1f5f9; border: 1rpx solid transparent;
  &.on { color: #0f766e; background: #f0fdfa; border-color: #5eead4; font-weight: 600; } }
.bd-refresh { margin-left: auto; font-size: 23rpx; color: #0d9488; padding: 6rpx 18rpx; border: 1rpx solid #99f6e4; border-radius: 6rpx; }
.bd-list { flex: 1; min-height: 0; }
.bd-inner { padding: 16rpx 24rpx 40rpx; }
.bd-state { text-align: center; color: #94a3b8; font-size: 24rpx; padding: 60rpx 0; }
.bd-day { display: block; font-size: 23rpx; font-weight: 600; color: #0f766e; margin: 14rpx 0 10rpx; }
.bd-card { background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 18rpx 22rpx; margin-bottom: 14rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04);
  &:active { background: #fafffe; } }
.bd-row1 { display: flex; align-items: center; gap: 14rpx; }
.bd-lg { font-size: 21rpx; color: #0f766e; font-weight: 600; }
.bd-time { font-size: 21rpx; color: #475569; }
.bd-num { font-size: 20rpx; color: #94a3b8; }
.bd-score { margin-left: auto; font-size: 22rpx; color: #b45309; font-weight: 600; }
.bd-row2 { display: flex; align-items: center; margin: 10rpx 0 8rpx; }
.bd-team { flex: 1; font-size: 28rpx; color: #0f172a; font-weight: 600; &.r { text-align: right; } }
.bd-vs { font-size: 22rpx; color: #94a3b8; margin: 0 16rpx; }
.bd-row3 { display: flex; gap: 10rpx; }
.bd-tag { font-size: 20rpx; color: #0f766e; background: #f0fdfa; border: 1rpx solid #99f6e4; border-radius: 6rpx; padding: 2rpx 12rpx; &.dim { color: #64748b; background: #f8fafc; border-color: #e2e8f0; } }
</style>
