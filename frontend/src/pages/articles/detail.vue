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

          <view v-if="a.status === 'pending' || a.status === 'processing'" class="ad-note wait">文章正在分析中,稍后刷新查看。</view>
          <view v-else-if="a.status === 'failed'" class="ad-note bad">
            分析失败{{ a.error ? ':' + a.error : '' }}
          </view>

          <view v-if="a.summary" class="ad-sum">
            <text class="ad-sum-l">AI 总结</text>
            <text class="ad-sum-t">{{ a.summary }}</text>
          </view>

          <view v-for="m in a.matches" :key="m.matchId" class="ad-match">
            <view class="ad-m-head">
              <text class="ad-m-t" :class="m.timing">{{ m.timing === 'review' ? '赛后复盘' : '赛前分析' }}</text>
              <text class="ad-m-n">{{ m.home }} vs {{ m.away }}</text>
              <text v-if="m.score" class="ad-m-s">{{ m.score }}</text>
            </view>
            <text class="ad-m-d">{{ m.league }} · {{ m.kickoff }}</text>
            <view class="ad-m-link">
              <text v-if="m.linkStatus === 'ambiguous'" class="ad-flag warn">关联存疑</text>
              <text v-else-if="m.linkStatus === 'manual'" class="ad-flag manual">手动关联</text>
              <text v-else class="ad-flag ok">自动关联 {{ m.confidence }}</text>
              <text class="ad-unlink" @tap="doUnlink(m)">取消关联</text>
            </view>
            <text v-if="m.evidence && m.linkStatus !== 'manual'" class="ad-evi">依据:{{ m.evidence }}</text>

            <view v-if="m.picks.length" class="ad-block">
              <text class="ad-b-t">作者倾向</text>
              <view v-for="(p, i) in m.picks" :key="i" class="ad-pick" :class="{ infer: !p.explicit }">
                <view class="ad-pick-top">
                  <text class="ad-pick-t">{{ pickText(p) }}</text>
                  <text class="ad-pick-r" :class="p.result">{{ resultText(p.result) }}</text>
                </view>
                <view class="ad-pick-tags">
                  <text class="ad-tag" :class="p.explicit ? 'ex' : 'in'">{{ p.explicit ? '作者明说' : 'AI推测' }}</text>
                  <text class="ad-tag st" :class="p.strength">强度 {{ STRENGTH[p.strength] || p.strength }}</text>
                  <text v-if="p.strength === 'weak'" class="ad-tag wk">不计入命中率</text>
                  <text v-if="p.lineSource === 'system'" class="ad-tag sys">按系统终盘亚盘 {{ p.line }} 结算</text>
                </view>
                <text v-if="p.reasoning" class="ad-pick-why">依据:{{ p.reasoning }}</text>
                <text v-if="p.quote" class="ad-pick-q">原文:{{ p.quote }}</text>
              </view>
              <text class="ad-pick-n">微信不允许公众号明说胜负和让球结果,多数倾向由 AI 根据文意推测,可能与作者本意不符。赛后自动结算,不代表本系统结论。</text>
            </view>

            <view v-if="m.claims.length" class="ad-block">
              <text class="ad-b-t">事实核实 <text class="ad-b-s">已证实 {{ cnt(m, 'confirmed') }} · 被反驳 {{ cnt(m, 'contradicted') }} · 未验证 {{ cnt(m, 'unverified') }}</text></text>
              <view v-for="(c, i) in m.claims" :key="i" class="ad-claim">
                <view class="ad-c-top">
                  <text class="ad-c-v" :class="V[c.verify].cls">{{ V[c.verify].text }}</text>
                  <text class="ad-c-text">{{ c.text }}</text>
                </view>
                <text v-if="c.note" class="ad-c-note">{{ c.note }}</text>
                <view v-if="impact(c)" class="ad-c-imp">
                  <text class="ad-c-imp-t" :class="c.impactDir">AI 评估:{{ impact(c) }}</text>
                </view>
              </view>
              <text class="ad-pick-n">核实依据联网搜索,影响评估为模型判断,仅供参考。</text>
            </view>
            <view v-else-if="!m.picks.length" class="ad-none">未提取到可核实的事实或推荐</view>

            <view class="ad-m-go">
              <text class="ad-go" @tap="goChat(m)">AI 聊天分析本场</text>
            </view>
          </view>

          <view v-if="!a.matches.length && a.status === 'done'" class="ad-empty">
            <text class="ad-empty-t">这篇文章没有关联到比赛</text>
            <text class="ad-empty-d">可能在讨论发布时间前后以外的比赛,或不是比赛分析。你可以回到列表手动关联。</text>
          </view>

          <view v-if="(a.otherMatches || []).length" class="ad-other">
            <text class="ad-b-t">文中提到的其他比赛(未在候选范围内)</text>
            <text v-for="(o, i) in a.otherMatches" :key="i" class="ad-other-i">· {{ o }}</text>
          </view>

          <view v-if="a.canReprocess" class="ad-re" @tap="doReprocess">重新分析</view>
        </template>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { requireAuth } from '@/utils/auth'
import { getArticle, unlinkMatch, reprocess, pickText, VERIFY, impactText, RESULT, STRENGTH } from '@/utils/wxArticles'

const V = VERIFY
const a = ref(null)
const id = ref('')
const loading = ref(true)
const errText = ref('')

const impact = impactText
const resultText = (r) => (RESULT[r] ? RESULT[r].text : r)
const cnt = (m, k) => m.claims.filter((c) => c.verify === k).length

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

function doUnlink(m) {
  uni.showModal({
    title: '取消关联',
    content: `取消与 ${m.home} vs ${m.away} 的关联?相关事实核实结果会保留在数据库,但不再显示。`,
    confirmText: '取消关联',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await unlinkMatch(a.value.id, m.matchId)
        await load()
      } catch (e) {
        uni.showToast({ title: e?.message || '操作失败', icon: 'none' })
      }
    },
  })
}

function doReprocess() {
  uni.showModal({
    title: '重新分析',
    content: '会重新调用模型并联网核实,有一定耗时和费用。确定吗?',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await reprocess(a.value.id)
        uni.showToast({ title: '已加入队列', icon: 'success' })
        await load()
      } catch (e) {
        uni.showToast({ title: e?.message || '操作失败', icon: 'none' })
      }
    },
  })
}

function goChat(m) {
  const qs = [`matchId=${encodeURIComponent(m.matchId)}`, `home=${encodeURIComponent(m.home || '')}`,
    `away=${encodeURIComponent(m.away || '')}`, `league=${encodeURIComponent(m.league || '')}`,
    `time=${encodeURIComponent(m.kickoff || '')}`].join('&')
  uni.navigateTo({ url: `/pages/predict/match-chat?${qs}` })
}

onLoad((q) => {
  id.value = q?.id || ''
  if (!requireAuth()) return
  load()
})
</script>

<style lang="scss" scoped>
.ad-page { height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px)); background: #f0fdf9; }
.ad-scroll { height: 100%; }
.ad-inner { padding: 20rpx 24rpx 60rpx; }
.ad-state { text-align: center; color: #94a3b8; font-size: 24rpx; padding: 80rpx 0; }
.ad-head { background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 22rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04); }
.ad-title { display: block; font-size: 32rpx; font-weight: 700; color: #0f172a; line-height: 1.45; }
.ad-meta { display: flex; align-items: center; gap: 14rpx; margin-top: 12rpx; }
.ad-acct { font-size: 22rpx; font-weight: 600; color: #0f766e; }
.ad-time { font-size: 21rpx; color: #94a3b8; }
.ad-orig { margin-left: auto; font-size: 22rpx; color: #0d9488; font-weight: 600; padding: 4rpx 16rpx; border: 1rpx solid #99f6e4; border-radius: 6rpx; background: #f0fdfa; }
.ad-note { font-size: 22rpx; border-radius: 6rpx; padding: 12rpx 16rpx; margin-top: 14rpx; &.wait { color: #b45309; background: #fffbeb; } &.bad { color: #dc2626; background: #fef2f2; } }
.ad-sum { margin-top: 16rpx; background: #f0fdfa; border-left: 6rpx solid #14b8a6; border-radius: 6rpx; padding: 16rpx 20rpx; }
.ad-sum-l { display: block; font-size: 20rpx; font-weight: 700; color: #0f766e; letter-spacing: 2rpx; margin-bottom: 6rpx; }
.ad-sum-t { font-size: 25rpx; color: #134e4a; line-height: 1.7; }

.ad-match { margin-top: 18rpx; background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 22rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04); }
.ad-m-head { display: flex; align-items: center; gap: 12rpx; }
.ad-m-t { font-size: 19rpx; font-weight: 600; padding: 3rpx 10rpx; border-radius: 6rpx; &.preview { color: #0f766e; background: #ccfbf1; } &.review { color: #64748b; background: #e2e8f0; } }
.ad-m-n { font-size: 29rpx; font-weight: 700; color: #0f172a; }
.ad-m-s { margin-left: auto; font-size: 26rpx; font-weight: 700; color: #475569; }
.ad-m-d { display: block; font-size: 21rpx; color: #94a3b8; margin-top: 6rpx; }
.ad-m-link { display: flex; align-items: center; gap: 12rpx; margin-top: 10rpx; }
.ad-flag { font-size: 19rpx; padding: 2rpx 10rpx; border-radius: 6rpx; &.ok { color: #047857; background: #d1fae5; } &.warn { color: #b45309; background: #fef3c7; } &.manual { color: #1d4ed8; background: #dbeafe; } }
.ad-unlink { margin-left: auto; font-size: 21rpx; color: #94a3b8; }
.ad-evi { display: block; font-size: 21rpx; color: #94a3b8; line-height: 1.6; margin-top: 8rpx; }
.ad-block { margin-top: 18rpx; padding-top: 14rpx; border-top: 1rpx solid #f1f5f9; display: flex; flex-direction: column; gap: 10rpx; }
.ad-b-t { font-size: 22rpx; font-weight: 700; color: #475569; letter-spacing: 1rpx; }
.ad-b-s { font-size: 20rpx; font-weight: 400; color: #94a3b8; margin-left: 8rpx; letter-spacing: 0; }
.ad-pick { display: flex; flex-direction: column; gap: 8rpx; background: #f5f3ff; border-radius: 6rpx; padding: 14rpx 16rpx; &.infer { background: #faf9ff; border: 1rpx dashed #c4b5fd; } }
.ad-pick-top { display: flex; align-items: center; justify-content: space-between; }
.ad-pick-t { font-size: 25rpx; font-weight: 600; color: #5b21b6; }
.ad-pick-r { font-size: 21rpx; color: #64748b; &.hit, &.hhit { color: #dc2626; font-weight: 700; } &.miss, &.hmiss { color: #059669; font-weight: 700; } }
.ad-pick-tags { display: flex; flex-wrap: wrap; gap: 8rpx; }
.ad-tag { font-size: 19rpx; padding: 2rpx 10rpx; border-radius: 6rpx; color: #64748b; background: #e2e8f0; &.ex { color: #047857; background: #d1fae5; } &.in { color: #7c3aed; background: #ede9fe; } &.st.strong { color: #b91c1c; background: #fee2e2; } &.st.medium { color: #b45309; background: #fef3c7; } &.wk { color: #94a3b8; background: #f1f5f9; } &.sys { color: #1d4ed8; background: #dbeafe; } }
.ad-pick-why { font-size: 21rpx; color: #6d28d9; line-height: 1.6; }
.ad-pick-q { font-size: 20rpx; color: #94a3b8; line-height: 1.6; }
.ad-pick-n { font-size: 19rpx; color: #94a3b8; line-height: 1.6; }
.ad-claim { background: #f8fafc; border-radius: 6rpx; padding: 14rpx 16rpx; display: flex; flex-direction: column; gap: 8rpx; }
.ad-c-top { display: flex; align-items: flex-start; gap: 10rpx; }
.ad-c-v { flex-shrink: 0; font-size: 19rpx; font-weight: 600; line-height: 1; padding: 5rpx 10rpx; border-radius: 6rpx; margin-top: 4rpx; &.ok { color: #047857; background: #d1fae5; } &.bad { color: #b91c1c; background: #fee2e2; } &.pend { color: #b45309; background: #fef3c7; } }
.ad-c-text { flex: 1; font-size: 24rpx; color: #1e293b; line-height: 1.6; font-weight: 600; }
.ad-c-note { font-size: 21rpx; color: #64748b; line-height: 1.6; }
.ad-c-imp-t { font-size: 20rpx; padding: 2rpx 10rpx; border-radius: 6rpx; color: #64748b; background: #e2e8f0; &.upper { color: #b91c1c; background: #fee2e2; } &.lower { color: #047857; background: #d1fae5; } }
.ad-none { margin-top: 14rpx; font-size: 22rpx; color: #94a3b8; }
.ad-m-go { margin-top: 16rpx; display: flex; justify-content: flex-end; }
.ad-go { font-size: 22rpx; color: #0f766e; font-weight: 600; padding: 8rpx 22rpx; border: 1rpx solid #99f6e4; border-radius: 6rpx; background: #f0fdfa; }
.ad-empty { margin-top: 18rpx; background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 36rpx 26rpx; display: flex; flex-direction: column; gap: 10rpx; align-items: center; }
.ad-empty-t { font-size: 27rpx; font-weight: 600; color: #0f172a; }
.ad-empty-d { font-size: 22rpx; color: #64748b; line-height: 1.7; text-align: center; }
.ad-other { margin-top: 18rpx; display: flex; flex-direction: column; gap: 6rpx; padding: 0 6rpx; }
.ad-other-i { font-size: 21rpx; color: #94a3b8; line-height: 1.6; }
.ad-re { margin: 26rpx auto 0; width: 240rpx; text-align: center; font-size: 24rpx; color: #475569; border: 1rpx solid #cbd5e1; border-radius: 6rpx; padding: 12rpx 0; background: #fff; }
</style>
