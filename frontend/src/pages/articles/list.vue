<template>
  <view class="al-page">
    <view class="al-top">
      <view class="al-tabs">
        <text v-for="t in tabs" :key="t.k" class="al-tab" :class="{ on: link === t.k }" @tap="setLink(t.k)">{{ t.t }}</text>
        <text class="al-rank" @tap="goStats">公众号榜</text>
      </view>
      <scroll-view v-if="accounts.length > 1" class="al-accs" scroll-x>
        <view class="al-accs-row">
          <text class="al-acc" :class="{ on: !wxid }" @tap="setAccount('')">全部公众号</text>
          <text
            v-for="a in accounts"
            :key="a.wxid"
            class="al-acc"
            :class="{ on: wxid === a.wxid }"
            @tap="setAccount(a.wxid)"
          >{{ a.name || a.wxid }} {{ a.count }}</text>
        </view>
      </scroll-view>
      <view v-if="matchId" class="al-filter">
        <text>仅看本场相关文章</text>
        <text class="al-filter-x" @tap="clearMatch">查看全部</text>
      </view>
    </view>

    <scroll-view class="al-list" scroll-y @scrolltolower="loadMore">
      <view class="al-inner">
        <view v-if="loading && !items.length" class="al-state">加载中…</view>
        <view v-else-if="errText" class="al-state">{{ errText }}</view>
        <view v-else-if="!items.length" class="al-empty">
          <text class="al-empty-t">暂无文章</text>
          <text class="al-empty-d">关注的公众号发布新文章后,会自动推送到这里,并关联对应的比赛。</text>
        </view>

        <view v-for="a in items" :key="a.id" class="al-card" @tap="openDetail(a)">
          <view class="al-meta">
            <text class="al-acct">{{ a.account || '公众号' }}</text>
            <text class="al-time">{{ a.publishTime }}</text>
            <text v-if="a.status === 'pending' || a.status === 'processing'" class="al-st wait">分析中</text>
            <text v-else-if="a.status === 'failed'" class="al-st bad">分析失败</text>
            <text v-if="a.pickCount" class="al-st pick">推荐 {{ a.pickCount }}</text>
          </view>
          <text class="al-title">{{ a.title }}</text>
          <text v-if="a.summary" class="al-sum">{{ a.summary }}</text>

          <view v-if="a.matches.length" class="al-ms">
            <view v-for="m in a.matches" :key="m.matchId" class="al-m">
              <text class="al-m-t" :class="m.timing">{{ m.timing === 'review' ? '复盘' : '赛前' }}</text>
              <text class="al-m-n">{{ m.home }} vs {{ m.away }}</text>
              <text v-if="m.linkStatus === 'ambiguous'" class="al-m-flag">存疑</text>
              <text v-else-if="m.linkStatus === 'manual'" class="al-m-flag manual">手动</text>
            </view>
          </view>
          <view v-else-if="a.status === 'done'" class="al-unlinked">
            <text class="al-un-t">未关联到比赛</text>
            <text class="al-un-btn" @tap.stop="openLink(a)">手动关联</text>
          </view>
        </view>

        <view v-if="loadingMore" class="al-more">加载中…</view>
        <view v-else-if="items.length && items.length >= total" class="al-more">已显示全部 {{ total }} 篇</view>
      </view>
    </scroll-view>

    <!-- 手动关联 -->
    <view v-if="linkTarget" class="al-mask" @tap="closeLink"></view>
    <view v-if="linkTarget" class="al-sheet" @tap.stop>
      <view class="al-sheet-head">
        <text class="al-sheet-t">选择要关联的比赛</text>
        <text class="al-sheet-x" @tap="closeLink">关闭</text>
      </view>
      <text class="al-sheet-sub">{{ linkTarget.title }}</text>
      <scroll-view class="al-sheet-list" scroll-y>
        <view v-if="candLoading" class="al-state">读取候选比赛…</view>
        <view v-else-if="!cands.length" class="al-state">发布时间前后没有可选比赛</view>
        <view v-for="c in cands" :key="c.matchId" class="al-cand" @tap="doLink(c)">
          <view class="al-cand-main">
            <text class="al-cand-n">{{ c.home }} vs {{ c.away }}</text>
            <text class="al-cand-d">{{ c.league }} · {{ c.kickoff }}<template v-if="c.score"> · 已完赛 {{ c.score }}</template></text>
          </view>
          <text class="al-cand-go">关联</text>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { requireAuth } from '@/utils/auth'
import { listArticles, getAccounts, getCandidates, linkMatch } from '@/utils/wxArticles'

const tabs = [
  { k: 'all', t: '全部' },
  { k: 'linked', t: '已关联' },
  { k: 'unlinked', t: '未关联' },
]
const link = ref('all')
const wxid = ref('')
const matchId = ref('')
const accounts = ref([])
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loadingMore = ref(false)
const errText = ref('')
const linkTarget = ref(null)
const cands = ref([])
const candLoading = ref(false)
let seq = 0
let inited = false

async function load(reset = true) {
  if (reset) {
    page.value = 1
    loading.value = true
    errText.value = ''
  } else {
    loadingMore.value = true
  }
  const my = ++seq
  try {
    const res = await listArticles({
      link: link.value, wxid: wxid.value, match_id: matchId.value, page: page.value, size: 20,
    })
    if (my !== seq) return
    total.value = res.total || 0
    items.value = reset ? res.items || [] : items.value.concat(res.items || [])
  } catch (e) {
    if (my !== seq) return
    if (e?.statusCode !== 401) errText.value = e?.message || '加载失败'
  } finally {
    if (my === seq) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function loadMore() {
  if (loading.value || loadingMore.value || items.value.length >= total.value) return
  page.value += 1
  load(false)
}
function setLink(k) { if (link.value !== k) { link.value = k; load() } }
function setAccount(id) { if (wxid.value !== id) { wxid.value = id; load() } }
function clearMatch() { matchId.value = ''; load() }
function goStats() { uni.navigateTo({ url: '/pages/articles/stats' }) }
function openDetail(a) { uni.navigateTo({ url: `/pages/articles/detail?id=${a.id}` }) }

async function openLink(a) {
  linkTarget.value = a
  cands.value = []
  candLoading.value = true
  try {
    cands.value = (await getCandidates(a.id)).items || []
  } catch (e) {
    uni.showToast({ title: e?.message || '读取失败', icon: 'none' })
  } finally {
    candLoading.value = false
  }
}
function closeLink() { linkTarget.value = null }
function doLink(c) {
  const a = linkTarget.value
  if (!a) return
  uni.showModal({
    title: '关联比赛',
    content: `将《${a.title}》关联到 ${c.home} vs ${c.away}?`,
    confirmText: '关联',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await linkMatch(a.id, c.matchId)
        closeLink()
        uni.showToast({ title: '已关联', icon: 'success' })
        load()
      } catch (e) {
        uni.showToast({ title: e?.message || '关联失败', icon: 'none' })
      }
    },
  })
}

onLoad((q) => {
  matchId.value = q?.matchId || ''
  if (!requireAuth()) return
  inited = true
  getAccounts().then((r) => { accounts.value = r.items || [] }).catch(() => {})
  load()
})
onShow(() => {
  if (inited) load()      // 从详情返回后刷新(关联状态可能变化)
})
</script>

<style lang="scss" scoped>
.al-page {
  display: flex; flex-direction: column;
  height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
  background: #f0fdf9;
}
.al-top { flex-shrink: 0; background: #fff; border-bottom: 1rpx solid #e2e8f0; padding: 14rpx 24rpx 12rpx; }
.al-tabs { display: flex; gap: 12rpx; }
.al-tab {
  font-size: 24rpx; color: #475569; padding: 6rpx 22rpx; border-radius: 6rpx;
  background: #f1f5f9; border: 1rpx solid transparent;
  &.on { color: #0f766e; background: #f0fdfa; border-color: #5eead4; font-weight: 600; }
}
.al-rank { margin-left: auto; font-size: 23rpx; color: #7c3aed; background: #f5f3ff; border: 1rpx solid #ddd6fe; padding: 6rpx 20rpx; border-radius: 6rpx; font-weight: 600; }
.al-accs { white-space: nowrap; margin-top: 12rpx; }
.al-accs-row { display: inline-flex; gap: 10rpx; }
.al-acc {
  font-size: 21rpx; color: #64748b; padding: 4rpx 16rpx; border-radius: 6rpx;
  border: 1rpx solid #e2e8f0; white-space: nowrap;
  &.on { color: #0f766e; border-color: #5eead4; background: #f0fdfa; font-weight: 600; }
}
.al-filter {
  display: flex; justify-content: space-between; margin-top: 12rpx;
  font-size: 22rpx; color: #b45309; background: #fffbeb; border-radius: 6rpx; padding: 8rpx 14rpx;
}
.al-filter-x { color: #0d9488; font-weight: 600; }

.al-list { flex: 1; min-height: 0; }
.al-inner { padding: 20rpx 24rpx 40rpx; }
.al-state { text-align: center; color: #94a3b8; font-size: 24rpx; padding: 60rpx 0; }
.al-empty {
  display: flex; flex-direction: column; gap: 10rpx; align-items: center;
  background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 50rpx 30rpx; margin-top: 10rpx;
}
.al-empty-t { font-size: 28rpx; font-weight: 600; color: #0f172a; }
.al-empty-d { font-size: 23rpx; color: #64748b; text-align: center; line-height: 1.7; }

.al-card {
  background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx;
  padding: 20rpx 22rpx; margin-bottom: 18rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04);
  &:active { background: #fafffe; }
}
.al-meta { display: flex; align-items: center; gap: 12rpx; flex-wrap: wrap; }
.al-acct { font-size: 22rpx; font-weight: 600; color: #0f766e; }
.al-time { font-size: 21rpx; color: #94a3b8; }
.al-st {
  font-size: 19rpx; padding: 2rpx 10rpx; border-radius: 6rpx; color: #64748b; background: #f1f5f9;
  &.wait { color: #b45309; background: #fffbeb; }
  &.bad { color: #dc2626; background: #fef2f2; }
  &.pick { color: #7c3aed; background: #ede9fe; margin-left: auto; }
}
.al-title { display: block; font-size: 29rpx; font-weight: 700; color: #0f172a; line-height: 1.45; margin-top: 10rpx; }
.al-sum {
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  font-size: 23rpx; color: #475569; line-height: 1.65; margin-top: 8rpx;
}
.al-ms { display: flex; flex-direction: column; gap: 8rpx; margin-top: 14rpx; padding-top: 12rpx; border-top: 1rpx dashed #e2e8f0; }
.al-m { display: flex; align-items: center; gap: 10rpx; }
.al-m-t {
  font-size: 19rpx; font-weight: 600; padding: 2rpx 10rpx; border-radius: 6rpx; flex-shrink: 0;
  &.preview { color: #0f766e; background: #ccfbf1; }
  &.review { color: #64748b; background: #e2e8f0; }
}
.al-m-n { font-size: 24rpx; color: #1e293b; font-weight: 600; }
.al-m-flag { font-size: 19rpx; color: #b45309; background: #fef3c7; padding: 2rpx 8rpx; border-radius: 6rpx; &.manual { color: #1d4ed8; background: #dbeafe; } }
.al-unlinked {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 14rpx; padding-top: 12rpx; border-top: 1rpx dashed #e2e8f0;
}
.al-un-t { font-size: 22rpx; color: #94a3b8; }
.al-un-btn { font-size: 22rpx; color: #0d9488; font-weight: 600; padding: 6rpx 18rpx; border: 1rpx solid #99f6e4; border-radius: 6rpx; background: #f0fdfa; }
.al-more { text-align: center; font-size: 21rpx; color: #94a3b8; padding: 16rpx 0; }

.al-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); z-index: 90; }
.al-sheet {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 91; max-height: 72vh;
  background: #fff; border-radius: 12rpx 12rpx 0 0; padding: 22rpx 24rpx calc(22rpx + env(safe-area-inset-bottom));
  display: flex; flex-direction: column;
}
.al-sheet-head { display: flex; justify-content: space-between; align-items: center; }
.al-sheet-t { font-size: 29rpx; font-weight: 700; color: #0f172a; }
.al-sheet-x { font-size: 24rpx; color: #0d9488; padding: 6rpx 4rpx; }
.al-sheet-sub { font-size: 21rpx; color: #94a3b8; margin: 6rpx 0 12rpx; display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.al-sheet-list { flex: 1; min-height: 0; max-height: 56vh; }
.al-cand {
  display: flex; align-items: center; gap: 12rpx; padding: 16rpx 4rpx; border-bottom: 1rpx solid #f1f5f9;
  &:active { background: #f0fdfa; }
}
.al-cand-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.al-cand-n { font-size: 26rpx; font-weight: 600; color: #0f172a; }
.al-cand-d { font-size: 21rpx; color: #94a3b8; }
.al-cand-go { font-size: 22rpx; color: #0d9488; font-weight: 600; padding: 6rpx 18rpx; border: 1rpx solid #99f6e4; border-radius: 6rpx; background: #f0fdfa; }
</style>
