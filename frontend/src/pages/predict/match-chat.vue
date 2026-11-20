<template>
  <view class="mc-page">
    <!-- 比赛信息条:对话时始终可见 -->
    <view class="mc-head">
      <view class="mc-teams">
        <text class="mc-team">{{ home || '主队' }}</text>
        <text class="mc-vs">vs</text>
        <text class="mc-team">{{ away || '客队' }}</text>
        <view class="mc-clear" :class="{ off: !messages.length || streaming }" @tap="confirmClear">
          <view class="ico ico-trash"></view>
        </view>
      </view>
      <view class="mc-meta">
        <text v-if="league" class="mc-tag">{{ league }}</text>
        <text v-if="time" class="mc-tag">{{ time }}</text>
        <text v-if="ahText" class="mc-tag strong">亚盘 {{ ahText }}</text>
        <text v-if="f6Text" class="mc-tag" :class="f6dir">{{ f6Text }}</text>
      </view>
    </view>

    <scroll-view
      class="mc-list"
      scroll-y
      :scroll-top="scrollTop"
      :scroll-with-animation="false"
      @scroll="onScroll"
    >
      <view class="mc-inner">
        <view v-if="loadingHistory" class="mc-state">读取会话…</view>
        <view v-else-if="storeError" class="mc-state">{{ storeError }}</view>

        <view v-else-if="!messages.length && !streaming" class="cx">
          <text class="cx-title">已载入本场数据</text>
          <text class="cx-sub">不会自动联网或查询,直接提问即可</text>
          <view class="cx-list">
            <view v-for="r in ctxRows" :key="r.k" class="cx-row" :class="{ off: !r.ok }">
              <text class="cx-k">{{ r.k }}</text>
              <text class="cx-v">{{ r.v }}</text>
            </view>
          </view>
          <text v-if="ctxText" class="cx-view" @tap="showCtx = !showCtx">{{ showCtx ? '收起数据' : '查看喂给 AI 的全部数据' }}</text>
          <text v-if="showCtx" class="cx-raw">{{ ctxText }}</text>
          <view class="cx-ex">
            <text v-for="q in examples" :key="q" class="cx-q" @tap="send(q)">{{ q }}</text>
          </view>
        </view>

        <view v-for="m in messages" :key="m.id || m.tmp" class="mc-msg" :class="m.role">
          <view v-if="m.role === 'user'" class="mc-user">
            <text class="mc-user-text">{{ m.content }}</text>
            <text v-if="m.attachments" class="mc-user-att">含 {{ m.attachments }} 张图片</text>
          </view>
          <view v-else class="mc-ai">
            <view class="mc-body">
              <view class="mc-md" v-html="renderMd(m.content)"></view>
            </view>
          </view>
        </view>

        <!-- 正在生成 -->
        <view v-if="streaming" class="mc-msg assistant">
          <view class="mc-ai">
            <view class="mc-steps">
              <text v-for="(s, i) in steps" :key="i" class="mc-step" :class="{ last: i === steps.length - 1 }">{{ s }}</text>
            </view>
            <view v-if="liveText" class="mc-md" v-html="renderMd(liveText)"></view>
            <view v-if="!liveText" class="mc-wait">
              <view class="mc-dot"></view><view class="mc-dot"></view><view class="mc-dot"></view>
            </view>
          </view>
        </view>

        <view v-if="notice" class="mc-notice">{{ notice }}</view>
        <view v-if="errText" class="mc-error">{{ errText }}</view>
        <view class="mc-tail"></view>
      </view>
    </scroll-view>

    <view class="mc-bottom">
      <view class="mc-composer" :class="{ focus: focused, busy: streaming }">
        <view v-if="images.length" class="mc-previews">
          <view v-for="(im, i) in images" :key="i" class="mc-prev">
            <image class="mc-prev-img" :src="im.preview" mode="aspectFill" />
            <view class="mc-prev-x" @tap="images.splice(i, 1)"><view class="ico ico-x"></view></view>
          </view>
        </view>
        <textarea
          v-model="draft"
          class="mc-ta"
          :disabled="streaming"
          placeholder="就本场数据提问,或粘贴文章内容"
          placeholder-class="mc-ph"
          auto-height
          :maxlength="4000"
          :show-confirm-bar="false"
          cursor-spacing="20"
          @focus="focused = true"
          @blur="focused = false"
        />
        <view class="mc-tools">
          <view class="mc-tool" :class="{ off: streaming || images.length >= 3 }" @tap="pickImage">
            <view class="ico ico-image"></view>
            <text>图片</text>
          </view>
          <view class="mc-tool" :class="{ on: web }" @tap="web = !web">
            <view class="ico ico-globe"></view>
            <text>联网{{ web ? '开' : '关' }}</text>
          </view>
          <view class="mc-grow"></view>
          <view v-if="streaming" class="mc-send stop" @tap="stop">
            <view class="ico ico-stop"></view><text>停止</text>
          </view>
          <view v-else class="mc-send" :class="{ off: !canSend }" @tap="send()">
            <text>发送</text><view class="ico ico-send"></view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import { onLoad, onReady } from '@dcloudio/uni-app'
import { requireAuth } from '@/utils/auth'
import { renderMarkdown } from '@/utils/miniMarkdown'
import { fetchHistory, clearHistory, streamChat, compressImage, fetchContext } from '@/utils/matchChat'

const matchId = ref('')
const home = ref('')
const away = ref('')
const league = ref('')
const time = ref('')
const ahOpen = ref('')
const ahClose = ref('')
const f6dir = ref('')
const f6score = ref('')

const messages = ref([])
const loadingHistory = ref(true)
const storeError = ref('')
const draft = ref('')
const images = ref([])
const web = ref(false)
const streaming = ref(false)
const liveText = ref('')
const steps = ref([])
const notice = ref('')
const errText = ref('')
const scrollTop = ref(0)
const focused = ref(false)

let ctrl = null
let stick = true
let listH = 0
let tmpSeq = 0

const ctx = ref(null)
const ctxText = ref('')
const showCtx = ref(false)
const examples = ['这场盘口和赔率有什么矛盾?', '近期状态和交锋怎么看?', '同赔样本可靠吗?', '关联文章里哪些观点可信?']
const ctxRows = computed(() => {
  const c = ctx.value
  if (!c) return []
  return [
    { k: '亚盘', ok: c.ah, v: c.ah ? '初盘/终盘及变动' : '暂无' },
    { k: '竞彩赔率', ok: c.jczq, v: c.jczq ? '胜平负、让球胜平负及变动' : '暂无' },
    { k: '历史同赔', ok: c.f6 > 0, v: c.f6 > 0 ? `${c.f6} 场样本及盘路统计` : '无匹配样本' },
    { k: '七因子预测', ok: c.prediction, v: c.prediction ? '已存预测' : '暂无' },
    { k: '交锋历史', ok: c.h2h > 0, v: c.h2h > 0 ? `共 ${c.h2h} 场,取最近 10 场` : '暂无' },
    { k: '近期战绩', ok: c.homeRecent + c.awayRecent > 0, v: `主 ${c.homeRecent} / 客 ${c.awayRecent} 场,取最近 10 场及未来赛程` },
    { k: '关联文章', ok: c.articles > 0, v: c.articles > 0 ? `${c.articles} 篇公众号文章` : '无' },
  ]
})

const ahText = computed(() => {
  const f = (v) => {
    if (v === '' || v === null || v === undefined || v === 'null') return ''
    const n = Number(v)
    return Number.isNaN(n) ? '' : (n > 0 ? `+${n}` : String(n))
  }
  const o = f(ahOpen.value)
  const c = f(ahClose.value)
  if (!o && !c) return ''
  return o && c && o !== c ? `${o} → ${c}` : (c || o)
})
const f6Text = computed(() => {
  const m = { upper: '同赔偏上盘', lower: '同赔偏下盘', neutral: '同赔中性' }
  if (!f6dir.value) return ''
  return m[f6dir.value] + (f6score.value ? ` ${f6score.value}` : '')
})
const canSend = computed(() => !streaming.value && (draft.value.trim() || images.value.length))

async function loadCtx() {
  try {
    const r = await fetchContext(matchId.value)
    ctx.value = r.summary || null
    ctxText.value = r.text || ''
  } catch (e) { /* 概览失败不影响提问 */ }
}

function renderMd(t) {
  return renderMarkdown(t)
}

function toBottom(force = false) {
  if (!force && !stick) return
  nextTick(() => { scrollTop.value = scrollTop.value + 100000 })
}

function onScroll(e) {
  const d = e.detail || {}
  stick = d.scrollHeight - d.scrollTop - (listH || 600) < 140
}

function toggleSrc(m) {
  m._open = !m._open
}

function openLink(u) {
  if (!u) return
  // #ifdef H5
  window.open(u, '_blank', 'noopener')
  // #endif
  // #ifndef H5
  uni.setClipboardData({ data: u })
  // #endif
}

async function loadHistory() {
  loadingHistory.value = true
  storeError.value = ''
  try {
    const res = await fetchHistory(matchId.value)
    messages.value = (res.messages || []).map((m) => reactive({ ...m, _open: false }))
  } catch (e) {
    if (e?.statusCode === 503) storeError.value = '会话功能尚未初始化'
    else if (e?.statusCode !== 401) storeError.value = e?.message || '读取会话失败'
  } finally {
    loadingHistory.value = false
    toBottom(true)
  }
}

async function pickImage() {
  if (streaming.value || images.value.length >= 3) return
  uni.chooseImage({
    count: 3 - images.value.length,
    sizeType: ['compressed'],
    success: async (res) => {
      const files = res.tempFiles || []
      for (const f of files) {
        try {
          images.value.push(await compressImage(f))
        } catch (e) {
          uni.showToast({ title: e.message || '图片处理失败', icon: 'none' })
        }
      }
    },
  })
}

async function send(preset) {
  if (streaming.value) return
  const text = (typeof preset === 'string' ? preset : draft.value).trim()
  if (!text && !images.value.length) return
  if (!requireAuth()) return

  const imgs = images.value.map((i) => ({ media_type: i.media_type, data: i.data }))
  messages.value.push(reactive({ tmp: ++tmpSeq, role: 'user', content: text || '(仅图片)', attachments: imgs.length }))
  draft.value = ''
  images.value = []
  streaming.value = true
  liveText.value = ''
  steps.value = []
  notice.value = ''
  errText.value = ''
  stick = true
  toBottom(true)

  let sources = []
  let finalText = ''
  let failed = false
  ctrl = new AbortController()
  try {
    await streamChat(matchId.value, { message: text, images: imgs, web: web.value }, (ev) => {
      if (ev.type === 'delta') {
        liveText.value += ev.text
        toBottom()
      } else if (ev.type === 'status') {
        if (steps.value[steps.value.length - 1] !== ev.text) steps.value.push(ev.text)
        if (steps.value.length > 6) steps.value.shift()
        toBottom()
      } else if (ev.type === 'sources') {
        sources = ev.items || []
      } else if (ev.type === 'notice') {
        notice.value = ev.text
      } else if (ev.type === 'done') {
        finalText = ev.text || ''
      } else if (ev.type === 'error') {
        failed = true
        errText.value = ev.text || '分析失败'
      }
    }, ctrl.signal)
  } catch (e) {
    if (e?.name === 'AbortError') {
      notice.value = '已停止'
    } else {
      failed = true
      if (e?.statusCode === 401) requireAuth()
      errText.value = e?.message || '网络异常'
    }
  }
  const body = finalText || (failed ? '' : liveText.value)
  if (body) {
    messages.value.push(reactive({ tmp: ++tmpSeq, role: 'assistant', content: body, sources, _open: false }))
  }
  streaming.value = false
  liveText.value = ''
  steps.value = []
  ctrl = null
  toBottom()
}

function stop() {
  if (ctrl) ctrl.abort()
}

function confirmClear() {
  if (streaming.value || !messages.value.length) return
  uni.showModal({
    title: '清空会话',
    content: '清空后本场的对话记录将删除,无法恢复。',
    confirmText: '清空',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await clearHistory(matchId.value)
        messages.value = []
        notice.value = ''
        errText.value = ''
      } catch (e) {
        uni.showToast({ title: e?.message || '清空失败', icon: 'none' })
      }
    },
  })
}

onLoad((q) => {
  matchId.value = q.matchId || ''
  home.value = decodeURIComponent(q.home || '')
  away.value = decodeURIComponent(q.away || '')
  league.value = decodeURIComponent(q.league || '')
  time.value = decodeURIComponent(q.time || '')
  ahOpen.value = q.ahOpen ?? ''
  ahClose.value = q.ahClose ?? ''
  f6dir.value = q.f6dir || ''
  f6score.value = q.f6score || ''
  if (home.value && away.value) {
    uni.setNavigationBarTitle({ title: 'AI分析' })
  }
  if (!requireAuth()) return
  loadHistory()
  loadCtx()
})

onReady(() => {
  uni.createSelectorQuery().select('.mc-list').boundingClientRect((r) => {
    if (r) listH = r.height
  }).exec()
})

onBeforeUnmount(() => { if (ctrl) ctrl.abort() })
</script>

<style lang="scss" scoped>
.mc-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
  background: #f0fdf9;
}

/* ===== SVG 图标(mask,颜色跟随 currentColor) ===== */
.ico {
  display: inline-block; flex-shrink: 0;
  width: 32rpx; height: 32rpx;
  background-color: currentColor;
  -webkit-mask: var(--ico) center / contain no-repeat;
  mask: var(--ico) center / contain no-repeat;
}
.ico-trash { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6'/%3E%3C/svg%3E"); }
.ico-image { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='4' width='18' height='16' rx='2'/%3E%3Ccircle cx='9' cy='10' r='1.6'/%3E%3Cpath d='m21 16-5-5-8 8'/%3E%3C/svg%3E"); }
.ico-globe { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18'/%3E%3C/svg%3E"); }
.ico-send { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M22 2 11 13M22 2l-7 20-4-9-9-4Z'/%3E%3C/svg%3E"); }
.ico-stop { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect x='6' y='6' width='12' height='12' rx='2' fill='%23000'/%3E%3C/svg%3E"); }
.ico-spark { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linejoin='round' stroke-linecap='round'%3E%3Cpath d='M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z'/%3E%3Cpath d='M19 3v4M17 5h4'/%3E%3C/svg%3E"); }
.ico-x { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='3' stroke-linecap='round'%3E%3Cpath d='M6 6l12 12M18 6 6 18'/%3E%3C/svg%3E"); }

/* ===== 顶部比赛条 ===== */
.mc-head {
  flex-shrink: 0;
  padding: 18rpx 24rpx 16rpx;
  background: #fff;
  border-bottom: 1rpx solid #e2e8f0;
  box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04);
}
.mc-teams { display: flex; align-items: center; gap: 14rpx; }
.mc-team { font-size: 30rpx; font-weight: 700; color: #0f172a; }
.mc-vs { font-size: 20rpx; color: #94a3b8; }
.mc-clear {
  margin-left: auto; width: 52rpx; height: 52rpx; border-radius: 6rpx;
  border: 1rpx solid #cbd5e1; color: #64748b;
  display: flex; align-items: center; justify-content: center;
  &.off { opacity: 0.35; }
}
.mc-meta { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 10rpx; }
.mc-tag {
  font-size: 20rpx; color: #475569; background: #f1f5f9;
  padding: 2rpx 12rpx; border-radius: 6rpx;
  &.strong { color: #0f172a; font-weight: 600; }
  &.upper { color: #dc2626; background: #fef2f2; }
  &.lower { color: #059669; background: #ecfdf5; }
}

/* ===== 消息列表 ===== */
.mc-list { flex: 1; min-height: 0; }
.mc-inner { padding: 20rpx 24rpx 12rpx; }
.mc-state { text-align: center; color: #94a3b8; font-size: 24rpx; padding: 60rpx 0; }
.mc-msg { margin-bottom: 22rpx; display: flex; }
.mc-msg.user { justify-content: flex-end; }
.mc-user {
  max-width: 82%; background: #0d9488; color: #fff;
  border-radius: 6rpx; padding: 16rpx 20rpx;
  display: flex; flex-direction: column; gap: 6rpx;
}
.mc-user-text { font-size: 26rpx; line-height: 1.6; word-break: break-all; }
.mc-user-att { font-size: 20rpx; opacity: 0.85; }
.mc-ai {
  width: 100%; background: #fff; border: 1rpx solid #e2e8f0; border-radius: 6rpx;
  padding: 18rpx 22rpx; box-shadow: 0 2rpx 10rpx rgba(15, 23, 42, 0.04);
}

/* markdown */
.mc-md {
  font-size: 25rpx; color: #1e293b; line-height: 1.75; word-break: break-word;
  :deep(.md-p) { margin: 0 0 10rpx; display: block; }
  :deep(.md-h) { font-weight: 700; color: #0f172a; margin: 16rpx 0 8rpx; }
  :deep(.md-h2) { font-size: 28rpx; color: #0f766e; }
  :deep(.md-h3) { font-size: 26rpx; }
  :deep(.md-h4) { font-size: 25rpx; }
  :deep(.md-list) { margin: 0 0 10rpx; padding-left: 34rpx; }
  :deep(.md-list li) { margin-bottom: 4rpx; }
  :deep(.md-hr) { height: 1rpx; background: #e2e8f0; margin: 14rpx 0; }
  :deep(.md-code) { background: #f1f5f9; padding: 0 8rpx; border-radius: 6rpx; font-size: 23rpx; }
  :deep(.md-a) { color: #0d9488; text-decoration: underline; }
  :deep(.md-table-wrap) { overflow-x: auto; margin: 6rpx 0 12rpx; }
  :deep(.md-table) { border-collapse: collapse; font-size: 22rpx; min-width: 100%; }
  :deep(.md-table th), :deep(.md-table td) { border: 1rpx solid #e2e8f0; padding: 8rpx 12rpx; text-align: left; vertical-align: top; }
  :deep(.md-table th) { background: #f8fafc; font-weight: 600; }
}

/* 生成中 */
.mc-steps { display: flex; flex-direction: column; gap: 4rpx; margin-bottom: 10rpx; }
.mc-step { font-size: 21rpx; color: #94a3b8; &.last { color: #0d9488; } }
.mc-wait { display: flex; gap: 8rpx; padding: 8rpx 0; }
.mc-dot {
  width: 10rpx; height: 10rpx; border-radius: 50%; background: #94a3b8;
  animation: mc-blink 1.2s infinite ease-in-out;
  &:nth-child(2) { animation-delay: 0.2s; }
  &:nth-child(3) { animation-delay: 0.4s; }
}
@keyframes mc-blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

.mc-notice { font-size: 22rpx; color: #b45309; background: #fffbeb; border-radius: 6rpx; padding: 10rpx 16rpx; margin-bottom: 14rpx; }
.mc-error { font-size: 22rpx; color: #dc2626; background: #fef2f2; border-radius: 6rpx; padding: 10rpx 16rpx; margin-bottom: 14rpx; }
.mc-tail { height: 8rpx; }

/* ===== 底部输入区 ===== */
.mc-bottom { flex-shrink: 0; background: #fff; border-top: 1rpx solid #e2e8f0; padding-bottom: env(safe-area-inset-bottom); }

/* ===== 底部输入区 ===== */
.mc-composer {
  margin: 14rpx 24rpx 16rpx; background: #f8fafc;
  border: 1rpx solid #cbd5e1; border-radius: 6rpx; overflow: hidden;
  transition: border-color 0.15s, background 0.15s;
  &.focus { border-color: #14b8a6; background: #fff; }
  &.busy { opacity: 0.85; }
}
.mc-previews { display: flex; gap: 12rpx; padding: 14rpx 18rpx 0; }
.mc-prev { position: relative; width: 96rpx; height: 96rpx; border-radius: 6rpx; overflow: hidden; border: 1rpx solid #e2e8f0; }
.mc-prev-img { width: 100%; height: 100%; }
.mc-prev-x {
  position: absolute; top: 0; right: 0; width: 34rpx; height: 34rpx;
  background: rgba(15, 23, 42, 0.65); color: #fff;
  display: flex; align-items: center; justify-content: center;
  .ico { width: 18rpx; height: 18rpx; }
}
.mc-ta {
  display: block; width: 100%; min-height: 56rpx; max-height: 240rpx;
  padding: 18rpx 20rpx 6rpx; box-sizing: border-box;
  font-size: 26rpx; line-height: 1.5; color: #0f172a; background: transparent;
}
.mc-ph { color: #94a3b8; }
.mc-tools { display: flex; align-items: center; gap: 10rpx; padding: 8rpx 14rpx 12rpx; }
.mc-grow { flex: 1; }
.mc-tool {
  height: 52rpx; padding: 0 14rpx; border-radius: 6rpx;
  display: flex; align-items: center; gap: 6rpx;
  font-size: 21rpx; color: #64748b; border: 1rpx solid #e2e8f0; background: #fff;
  .ico { width: 24rpx; height: 24rpx; }
  &.on { color: #0f766e; background: #f0fdfa; border-color: #5eead4; font-weight: 600; }
  &.off { opacity: 0.4; }
}
.mc-send {
  height: 52rpx; padding: 0 22rpx; border-radius: 6rpx;
  display: flex; align-items: center; gap: 8rpx;
  background: linear-gradient(135deg, #0d9488, #14b8a6); color: #fff;
  font-size: 23rpx; font-weight: 600;
  .ico { width: 24rpx; height: 24rpx; }
  &.off { opacity: 0.4; }
  &.stop { background: #475569; }
}

/* ===== 已载入数据 ===== */
.cx { background: #fff; border: 1rpx solid #d9ece8; border-radius: 6rpx; padding: 26rpx 24rpx 22rpx; }
.cx-title { display: block; font-size: 30rpx; font-weight: 700; color: #0f172a; }
.cx-sub { display: block; font-size: 22rpx; color: #64748b; margin-top: 4rpx; }
.cx-list { margin-top: 16rpx; }
.cx-row { display: flex; gap: 16rpx; padding: 10rpx 0; border-top: 1rpx solid #f1f5f9; &.off { opacity: 0.45; } }
.cx-k { flex-shrink: 0; width: 140rpx; font-size: 23rpx; font-weight: 600; color: #0f766e; }
.cx-v { flex: 1; min-width: 0; font-size: 23rpx; color: #475569; line-height: 1.5; }
.cx-view { display: block; font-size: 22rpx; color: #0d9488; margin-top: 12rpx; }
.cx-raw { display: block; margin-top: 10rpx; padding: 14rpx 16rpx; background: #f8fafc; border-radius: 6rpx; font-size: 20rpx; color: #475569; line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
.cx-ex { display: flex; flex-wrap: wrap; gap: 12rpx; margin-top: 18rpx; }
.cx-q { font-size: 22rpx; color: #0f766e; background: #f0fdfa; border: 1rpx solid #99f6e4; border-radius: 6rpx; padding: 8rpx 16rpx; }
</style>
