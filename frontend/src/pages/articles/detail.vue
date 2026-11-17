<template>
  <view class="ad-page">
    <scroll-view class="ad-scroll" scroll-y>
      <view class="ad-inner">
        <view v-if="loading" class="ad-state">加载中…</view>
        <view v-else-if="errText" class="ad-state">{{ errText }}</view>
        <template v-else-if="a">
          <view class="ad-head">
            <text class="ad-title">{{ a.title }}</text>
            <view class="ad-meta">
              <text class="ad-acct">{{ a.account }}</text>
              <text class="ad-time">{{ a.publishTime }}</text>
              <text class="ad-orig" @tap="openOrig">查看原文</text>
            </view>
          </view>

          <view v-if="a.content" class="ad-body">
            <text class="ad-p" v-for="(p, i) in paras" :key="i">{{ p }}</text>
          </view>
          <view v-else class="ad-state">暂无正文,可点"查看原文"阅读</view>

          <view v-for="m in shownMatches" :key="m.matchId" class="ad-chat" @tap="goChat(m)">
            <text class="ad-chat-t">就这篇文章向 AI 提问 · {{ m.home }} vs {{ m.away }}</text>
            <text class="ad-chat-go">›</text>
          </view>
        </template>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { requireAuth } from '@/utils/auth'
import { getArticle } from '@/utils/wxArticles'

const a = ref(null)
const id = ref('')
const loading = ref(true)
const errText = ref('')
const paras = computed(() => String(a.value?.content || '').split(/\n+/).map((x) => x.trim()).filter(Boolean))
const onlyMatch = ref('')
const shownMatches = computed(() => (a.value?.matches || []).filter((m) => !onlyMatch.value || String(m.matchId) === String(onlyMatch.value)))

async function load() {
  loading.value = true
  errText.value = ''
  try {
    a.value = await getArticle(id.value)
  } catch (e) {
    if (e?.statusCode !== 401) errText.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openOrig() {
  const u = a.value?.url
  if (!u) return
  // #ifdef H5
  window.open(u, '_blank', 'noopener')
  // #endif
  // #ifndef H5
  uni.setClipboardData({ data: u })
  // #endif
}

function goChat(m) {
  const qs = [`matchId=${encodeURIComponent(m.matchId)}`, `home=${encodeURIComponent(m.home || '')}`,
    `away=${encodeURIComponent(m.away || '')}`, `league=${encodeURIComponent(m.league || '')}`,
    `time=${encodeURIComponent(m.kickoff || '')}`].join('&')
  uni.navigateTo({ url: `/pages/predict/match-chat?${qs}` })
}

onLoad((q) => {
  id.value = q?.id || ''
  onlyMatch.value = q?.matchId ? decodeURIComponent(q.matchId) : ''
  if (!requireAuth()) return
  load()
})
</script>

<style lang="scss" scoped>
.ad-page { display: flex; flex-direction: column; height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px)); background: #f0fdf9; }
.ad-scroll { flex: 1; min-height: 0; height: 0; }
.ad-inner { padding: 20rpx 24rpx 60rpx; }
.ad-state { text-align: center; color: #94a3b8; font-size: 24rpx; padding: 60rpx 0; }
.ad-head { background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 22rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04); }
.ad-title { display: block; font-size: 32rpx; font-weight: 700; color: #0f172a; line-height: 1.45; }
.ad-meta { display: flex; align-items: center; gap: 14rpx; margin-top: 12rpx; }
.ad-acct { font-size: 22rpx; font-weight: 600; color: #0f766e; }
.ad-time { font-size: 21rpx; color: #94a3b8; }
.ad-orig { margin-left: auto; font-size: 22rpx; color: #0d9488; font-weight: 600; padding: 4rpx 16rpx; border: 1rpx solid #99f6e4; border-radius: 6rpx; background: #f0fdfa; }
.ad-body { margin-top: 18rpx; background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 22rpx; }
.ad-p { display: block; font-size: 27rpx; color: #1e293b; line-height: 1.85; margin-bottom: 18rpx; word-break: break-all; }
.ad-chat { margin-top: 18rpx; display: flex; align-items: center; padding: 20rpx 22rpx; background: #f0fdfa; border: 1rpx solid #99f6e4; border-radius: 6rpx; &:active { background: #ccfbf1; } }
.ad-chat-t { flex: 1; min-width: 0; font-size: 25rpx; font-weight: 600; color: #0f766e; }
.ad-chat-go { font-size: 34rpx; color: #0d9488; }
</style>
