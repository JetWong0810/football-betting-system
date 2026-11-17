<template>
  <view v-if="visible">
    <view class="app-mask ai-mask" @tap="emit('close')"></view>
    <view class="app-modal ai-modal show" @tap.stop>
      <view class="ai-head">
        <view class="ai-head-row">
          <view class="ai-titles">
            <text class="ai-title">AI情报</text>
            <text class="ai-tag">参考</text>
            <text v-if="flagLabel" class="ai-flag" :class="data.flag">{{ flagLabel }}</text>
            <text v-if="leanLabel" class="ai-lean" :class="data.lean">{{ leanLabel }}</text>
          </view>
          <text class="ai-close" @tap="emit('close')">关闭</text>
        </view>
        <text class="ai-vs">{{ data.homeTeam || '' }} vs {{ data.awayTeam || '' }}</text>
        <text class="ai-sub">{{ subLine }}</text>
      </view>

      <view class="ai-body">
        <view v-if="loading" class="ai-state">读取简报…</view>
        <view v-else-if="errText" class="ai-state">{{ errText }}</view>
        <view v-else-if="!data.available" class="ai-state">{{ emptyText }}</view>
        <view v-else class="ai-content">
          <text v-if="data.headline" class="ai-headline">{{ data.headline }}</text>
          <text v-if="data.conclusion" class="ai-conc">{{ data.conclusion }}</text>
          <view v-if="bullets.length" class="ai-points">
            <text v-for="(p, i) in bullets" :key="i" class="ai-point">{{ i + 1 }}. {{ p }}</text>
          </view>
          <text class="ai-foot">{{ footLine }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { prefetchAiIntel } from '@/utils/intelPrefetch'

const props = defineProps({
  visible: { type: Boolean, default: false },
  matchId: { type: String, default: '' },
})
const emit = defineEmits(['close', 'loaded'])

const loading = ref(false)
const errText = ref('')
const data = ref({})

const bullets = computed(() => data.value.bullets || [])
const flagLabel = computed(() => {
  if (data.value.flag === 'trap') return '诱盘'
  if (data.value.flag === 'upset') return '冷门'
  return ''
})
const leanLabel = computed(() => {
  const l = data.value.lean
  if (l === 'upper') return '利上'
  if (l === 'lower') return '利下'
  return ''
})
const subLine = computed(() => {
  const bits = [data.value.league, data.value.kickoff, data.value.handicapLabel].filter(Boolean)
  return bits.join(' · ')
})
const emptyText = computed(() => {
  if (data.value.reason === 'pending') return '简报生成中，稍后查看'
  if (data.value.reason === 'error') return '情报读取失败'
  return '暂无影响比赛的情报'
})
const footLine = computed(() => {
  const n = data.value.itemN || data.value.keptN || 0
  const t = String(data.value.updatedAt || data.value.fetchedAt || '').replace('T', ' ').slice(5, 16)
  return `来源 ${n} 条${t ? ' · ' + t : ''} · 不进七因子`
})

async function load(id) {
  if (!id) return
  loading.value = true
  errText.value = ''
  data.value = {}
  try {
    const res = await prefetchAiIntel(id)
    if (props.matchId === id) {
      data.value = res || {}
      emit('loaded', { matchId: id, data: data.value })
    }
  } catch (e) {
    if (props.matchId === id) {
      errText.value = e?.message || '加载失败'
      emit('loaded', { matchId: id, data: { available: false } })
    }
  } finally {
    if (props.matchId === id) loading.value = false
  }
}

watch(
  () => [props.visible, props.matchId],
  ([vis, id]) => {
    if (vis && id) load(id)
  },
)
</script>

<style lang="scss" scoped>
.ai-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); z-index: 230; }
.ai-modal {
  position: fixed; top: 50%; left: 50%;
  width: min(398px, calc(100vw - 32px));
  max-height: min(88vh, 720px);
  background: #fff; border-radius: 12rpx; z-index: 231;
  display: flex; flex-direction: column; overflow: hidden;
  transform: translate(-50%, -50%);
  box-shadow: 0 16rpx 48rpx rgba(15, 23, 42, 0.18);
}
.ai-head {
  padding: 18rpx 22rpx 12rpx; border-bottom: 1rpx solid #e2e8f0; flex-shrink: 0;
}
.ai-head-row { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.ai-titles { display: flex; align-items: center; gap: 8rpx; min-width: 0; flex-wrap: wrap; }
.ai-title { font-size: 28rpx; font-weight: 650; color: #0f172a; }
.ai-tag {
  font-size: 18rpx; color: #0f766e; background: #ccfbf1;
  border-radius: 6rpx; padding: 2rpx 8rpx;
}
.ai-flag {
  font-size: 18rpx; border-radius: 6rpx; padding: 2rpx 8rpx; font-weight: 650;
  &.trap { color: #b45309; background: #fffbeb; }
  &.upset { color: #7c3aed; background: #f5f3ff; }
}
.ai-lean {
  font-size: 18rpx; border-radius: 6rpx; padding: 2rpx 8rpx; font-weight: 650;
  &.upper { color: #dc2626; background: #fef2f2; }
  &.lower { color: #059669; background: #ecfdf5; }
}
.ai-close { font-size: 24rpx; color: #0d9488; padding: 6rpx 4rpx; }
.ai-vs { display: block; margin-top: 8rpx; font-size: 24rpx; font-weight: 650; color: #334155; }
.ai-sub { display: block; margin-top: 2rpx; font-size: 20rpx; color: #94a3b8; }
.ai-body {
  flex: 1 1 auto; min-height: 0; max-height: min(70vh, 560px);
  padding: 16rpx 22rpx 24rpx;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.ai-state { padding: 60rpx 20rpx; text-align: center; font-size: 24rpx; color: #94a3b8; }
.ai-headline {
  display: block; font-size: 28rpx; font-weight: 700; color: #0f172a; line-height: 1.4; margin-bottom: 8rpx;
}
.ai-conc {
  display: block; font-size: 26rpx; color: #0f172a; line-height: 1.55; margin-bottom: 14rpx;
}
.ai-points { margin-bottom: 16rpx; }
.ai-point { display: block; font-size: 24rpx; color: #334155; line-height: 1.55; }
.ai-foot { display: block; margin-top: 8rpx; font-size: 18rpx; color: #94a3b8; }
</style>
