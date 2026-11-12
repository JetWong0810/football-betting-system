<template>
  <view class="st-page">
    <scroll-view class="st-scroll" scroll-y>
      <view class="st-inner">
        <view class="st-intro">
          <text class="st-intro-t">按作者赛前倾向的实际赛果统计命中率。微信不允许明说结果,多数倾向由 AI 根据文意推测,所以分“作者明说”和“AI 推测”两种口径。倾向入库后不可修改,发布晚于开赛的不计入,强度为“弱”的不计入。已结算不足 {{ minSample }} 条的号只显示数据,不下结论。</text>
        </view>

        <view v-if="loading" class="st-state">加载中…</view>
        <view v-else-if="errText" class="st-state">{{ errText }}</view>
        <view v-else-if="!items.length" class="st-state">暂无公众号数据</view>

        <view v-for="a in items" :key="a.wxid" class="st-card">
          <view class="st-head">
            <text class="st-name">{{ a.name || a.wxid }}</text>
            <text class="st-n">{{ a.articles }} 篇文章</text>
          </view>

          <view class="st-main">
            <view class="st-rate-box">
              <text class="st-rate" :class="{ dim: !a.enough }">{{ a.rate === null ? '--' : a.rate + '%' }}</text>
              <text class="st-rate-l">倾向命中率</text>
            </view>
            <view class="st-cnt">
              <text class="st-cnt-l">已结算 <text class="st-cnt-n">{{ a.picks.decided }}</text> 条</text>
              <text class="st-cnt-d">命中 {{ a.picks.hit }} · 赢半 {{ a.picks.hhit }} · 输半 {{ a.picks.hmiss }} · 未中 {{ a.picks.miss }}</text>
              <text class="st-cnt-d">走水 {{ a.picks.push }} · 待结算 {{ a.picks.pending }}<template v-if="a.picks.void"> · 无法结算 {{ a.picks.void }}</template></text>
            </view>
          </view>
          <view v-if="a.ci" class="st-ci">
            <view class="st-ci-bar"><view class="st-ci-rng" :style="{ left: a.ci[0] + '%', width: (a.ci[1] - a.ci[0]) + '%' }"></view>
              <view class="st-ci-dot" :style="{ left: a.rate + '%' }"></view></view>
            <text class="st-ci-t">95% 置信区间 {{ a.ci[0] }}% – {{ a.ci[1] }}%</text>
          </view>
          <view v-if="!a.enough" class="st-warn">样本不足({{ a.picks.decided }}/{{ minSample }}),命中率仅供参考,区间很宽。</view>

          <view class="st-split">
            <view class="st-sp">
              <text class="st-sp-l">作者明说</text>
              <text class="st-sp-v">{{ a.split.explicit.rate === null ? '--' : a.split.explicit.rate + '%' }}</text>
              <text class="st-sp-n">{{ a.split.explicit.decided }} 条</text>
            </view>
            <view class="st-sp infer">
              <text class="st-sp-l">AI 推测</text>
              <text class="st-sp-v">{{ a.split.inferred.rate === null ? '--' : a.split.inferred.rate + '%' }}</text>
              <text class="st-sp-n">{{ a.split.inferred.decided }} 条</text>
            </view>
          </view>
          <text v-if="a.weakExcluded" class="st-wk">另有 {{ a.weakExcluded }} 条强度为“弱”的倾向,未计入以上统计。</text>

          <view v-if="a.byMarket.length" class="st-mk">
            <text v-for="m in a.byMarket" :key="m.market" class="st-mk-i">{{ MARKET[m.market] || m.market }} {{ m.rate === null ? '--' : m.rate + '%' }}({{ m.decided }})</text>
          </view>

          <view class="st-claims">
            <text class="st-cl-l">事实核实</text>
            <text class="st-cl ok">已证实 {{ a.claims.confirmed }}</text>
            <text class="st-cl bad">被反驳 {{ a.claims.contradicted }}</text>
            <text class="st-cl pend">未验证 {{ a.claims.unverified }}</text>
          </view>

          <view v-if="a.recent.length" class="st-rec">
            <view class="st-rec-h" @tap="toggle(a.wxid)">
              <text>最近倾向 {{ a.recent.length }} 条</text>
              <text class="st-rec-a">{{ open[a.wxid] ? '收起' : '展开' }}</text>
            </view>
            <view v-if="open[a.wxid]">
              <view v-for="(r, i) in a.recent" :key="i" class="st-r" @tap="goArticle(r.articleId)">
                <view class="st-r-main">
                  <text class="st-r-m">{{ r.home }} vs {{ r.away }}<template v-if="r.score"> {{ r.score }}</template></text>
                  <text class="st-r-p">{{ pickText(r) }}</text>
                </view>
                <text class="st-r-res" :class="RESULT[r.result] ? RESULT[r.result].cls : ''">{{ RESULT[r.result] ? RESULT[r.result].text : r.result }}</text>
              </view>
            </view>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { requireAuth } from '@/utils/auth'
import { getStats, pickText, RESULT, MARKET_NAME } from '@/utils/wxArticles'

const MARKET = MARKET_NAME
const items = ref([])
const minSample = ref(30)
const loading = ref(true)
const errText = ref('')
const open = reactive({})

const toggle = (k) => { open[k] = !open[k] }
const goArticle = (id) => uni.navigateTo({ url: `/pages/articles/detail?id=${id}` })

onLoad(async () => {
  if (!requireAuth()) return
  try {
    const res = await getStats()
    items.value = res.items || []
    minSample.value = res.minSample || 30
  } catch (e) {
    if (e?.statusCode !== 401) errText.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<style lang="scss" scoped>
.st-page { display: flex; flex-direction: column; height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px)); background: #f0fdf9; }
.st-scroll { flex: 1; min-height: 0; height: 0; }
.st-inner { padding: 20rpx 24rpx 60rpx; }
.st-state { text-align: center; color: #94a3b8; font-size: 24rpx; padding: 70rpx 0; }
.st-intro { background: #fffbeb; border-radius: 6rpx; padding: 14rpx 18rpx; margin-bottom: 18rpx; }
.st-intro-t { font-size: 21rpx; color: #92400e; line-height: 1.7; }
.st-card { background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 22rpx; margin-bottom: 18rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04); }
.st-head { display: flex; align-items: baseline; justify-content: space-between; }
.st-name { font-size: 30rpx; font-weight: 700; color: #0f172a; }
.st-n { font-size: 21rpx; color: #94a3b8; }
.st-main { display: flex; align-items: center; gap: 28rpx; margin-top: 16rpx; }
.st-rate-box { display: flex; flex-direction: column; align-items: center; min-width: 170rpx; }
.st-rate { font-size: 52rpx; font-weight: 800; color: #0f766e; font-variant-numeric: tabular-nums; &.dim { color: #94a3b8; } }
.st-rate-l { font-size: 20rpx; color: #94a3b8; margin-top: 2rpx; }
.st-cnt { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.st-cnt-l { font-size: 24rpx; color: #475569; }
.st-cnt-n { font-weight: 700; color: #0f172a; font-size: 28rpx; }
.st-cnt-d { font-size: 21rpx; color: #64748b; }
.st-ci { margin-top: 16rpx; }
.st-ci-bar { position: relative; height: 10rpx; border-radius: 6rpx; background: #e2e8f0; }
.st-ci-rng { position: absolute; top: 0; bottom: 0; background: #99f6e4; border-radius: 6rpx; }
.st-ci-dot { position: absolute; top: -4rpx; width: 18rpx; height: 18rpx; margin-left: -9rpx; border-radius: 50%; background: #0d9488; }
.st-ci-t { display: block; font-size: 20rpx; color: #94a3b8; margin-top: 10rpx; }
.st-warn { font-size: 21rpx; color: #b45309; background: #fffbeb; border-radius: 6rpx; padding: 8rpx 14rpx; margin-top: 12rpx; }
.st-split { display: flex; gap: 14rpx; margin-top: 14rpx; }
.st-sp { flex: 1; display: flex; align-items: baseline; gap: 8rpx; background: #ecfdf5; border-radius: 6rpx; padding: 10rpx 14rpx; &.infer { background: #f5f3ff; } }
.st-sp-l { font-size: 20rpx; color: #64748b; }
.st-sp-v { font-size: 28rpx; font-weight: 700; color: #0f172a; }
.st-sp-n { margin-left: auto; font-size: 19rpx; color: #94a3b8; }
.st-wk { display: block; font-size: 20rpx; color: #94a3b8; margin-top: 10rpx; }
.st-mk { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 14rpx; }
.st-mk-i { font-size: 20rpx; color: #475569; background: #f1f5f9; padding: 3rpx 12rpx; border-radius: 6rpx; }
.st-claims { display: flex; align-items: center; gap: 10rpx; margin-top: 16rpx; padding-top: 14rpx; border-top: 1rpx dashed #e2e8f0; flex-wrap: wrap; }
.st-cl-l { font-size: 21rpx; color: #64748b; font-weight: 600; }
.st-cl { font-size: 20rpx; padding: 2rpx 10rpx; border-radius: 6rpx; &.ok { color: #047857; background: #d1fae5; } &.bad { color: #b91c1c; background: #fee2e2; } &.pend { color: #b45309; background: #fef3c7; } }
.st-rec { margin-top: 16rpx; }
.st-rec-h { display: flex; justify-content: space-between; font-size: 22rpx; color: #475569; font-weight: 600; }
.st-rec-a { color: #0d9488; }
.st-r { display: flex; align-items: center; gap: 12rpx; padding: 14rpx 4rpx; border-bottom: 1rpx solid #f1f5f9; &:active { background: #f8fafc; } }
.st-r-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.st-r-m { font-size: 24rpx; color: #1e293b; font-weight: 600; }
.st-r-p { font-size: 21rpx; color: #7c3aed; }
.st-r-res { font-size: 22rpx; font-weight: 700; color: #64748b; &.hit { color: #dc2626; } &.miss { color: #059669; } &.pend { color: #94a3b8; font-weight: 500; } }
</style>
