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

        <view v-else-if="!messages.length && !streaming" class="mc-empty">
          <view class="mc-empty-head">
            <view class="mc-badge"><view class="ico ico-spark"></view></view>
            <view class="mc-empty-titles">
              <text class="mc-empty-title">本场 AI 分析</text>
              <text class="mc-empty-sub">数据为主,联网为辅,结论附依据与风险</text>
            </view>
          </view>
          <view class="mc-caps">
            <text class="mc-cap">盘口变动</text>
            <text class="mc-cap">历史同赔</text>
            <text class="mc-cap">七因子预测</text>
            <text class="mc-cap web">联网情报</text>
            <text class="mc-cap img">截图 / 文章</text>
          </view>
          <text class="mc-starter-label">从这里开始</text>
          <view class="mc-starters">
            <view v-for="st in starters" :key="st.t" class="mc-starter" @tap="send(st.t)">
              <view class="mc-st-main">
                <text class="mc-st-t">{{ st.t }}</text>
                <text class="mc-st-d">{{ st.d }}</text>
              </view>
              <text class="mc-st-go">›</text>
            </view>
          </view>
          <text class="mc-empty-note">仅供参考,不构成投注建议。联网信息未经校验,请以官方首发和赛前公告为准。</text>
        </view>

        <view v-for="m in messages" :key="m.id || m.tmp" class="mc-msg" :class="m.role">
          <view v-if="m.role === 'user'" class="mc-user">
            <text class="mc-user-text">{{ m.content }}</text>
            <text v-if="m.attachments" class="mc-user-att">含 {{ m.attachments }} 张图片</text>
          </view>
          <view v-else class="mc-ai">
            <view v-if="m.verdict" class="mc-verdict" :class="m.verdict.direction">
              <view class="mc-v-top">
                <text class="mc-v-dir">{{ dirLabel(m.verdict.direction) }}</text>
                <text class="mc-v-conf" :class="m.verdict.confidence">置信 {{ confLabel(m.verdict.confidence) }}</text>
              </view>
              <text v-if="m.verdict.headline" class="mc-v-head">{{ m.verdict.headline }}</text>

              <view v-if="(m.verdict.supports || []).length" class="mc-v-block">
                <text class="mc-v-title">依据</text>
                <view v-for="(sp, i) in m.verdict.supports" :key="'s' + i" class="mc-v-row">
                  <text v-if="tagOf(sp).tag" class="mc-v-tag" :class="tagOf(sp).cls">{{ tagOf(sp).tag }}</text>
                  <text class="mc-v-item">{{ tagOf(sp).text }}</text>
                </view>
              </view>

              <view v-if="(m.verdict.facts || []).length" class="mc-v-block">
                <text class="mc-v-title">联网基本面</text>
                <view v-for="(f, i) in m.verdict.facts" :key="'f' + i" class="mc-v-row">
                  <text class="mc-v-st" :class="f.status">{{ f.status === 'confirmed' ? '已核实' : '待核实' }}</text>
                  <view class="mc-v-fact">
                    <text class="mc-v-item">{{ f.text }}</text>
                    <text v-if="f.source || f.date" class="mc-v-src">{{ [f.source, f.date].filter(Boolean).join(' · ') }}</text>
                  </view>
                </view>
              </view>

              <view v-if="(m.verdict.risks || []).length" class="mc-v-block risk">
                <text class="mc-v-title">可能出错</text>
                <view v-for="(r, i) in m.verdict.risks" :key="'r' + i" class="mc-v-row">
                  <text class="mc-v-dot"></text>
                  <text class="mc-v-item">{{ r }}</text>
                </view>
              </view>
            </view>

            <view class="mc-body" :class="{ clamp: isLong(m) && !m._full }">
              <view class="mc-md" v-html="renderMd(m.content)"></view>
            </view>
            <view v-if="isLong(m)" class="mc-more" @tap="m._full = !m._full">{{ m._full ? '收起' : '展开全文' }}</view>
            <view v-if="(m.sources || []).length" class="mc-src">
              <view class="mc-src-head" @tap="toggleSrc(m)">
                <view class="ico ico-globe"></view>
                <text>联网来源 {{ m.sources.length }} 条(未经校验)</text>
                <text class="mc-src-arrow">{{ m._open ? '收起' : '展开' }}</text>
              </view>
              <view v-if="m._open" class="mc-src-list">
                <text
                  v-for="(s, i) in m.sources"
                  :key="i"
                  class="mc-src-item"
                  @tap="openLink(s.url)"
                >{{ i + 1 }}. {{ s.title }}</text>
              </view>
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
            <view v-else class="mc-wait">
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
      <scroll-view v-if="!streaming && messages.length" class="mc-quick" scroll-x>
        <view class="mc-quick-row">
          <text v-for="q in quicks" :key="q" class="mc-q" @tap="send(q)">{{ q }}</text>
        </view>
      </scroll-view>

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
          placeholder="问点什么,或粘贴文章内容"
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
import { fetchHistory, clearHistory, streamChat, compressImage } from '@/utils/matchChat'

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
const web = ref(true)
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

const starters = [
  { t: '综合分析这场', d: '盘口、同赔、多因子、基本面一起看,给出结论和风险点' },
  { t: '同赔样本可靠吗', d: '检查样本量与置信区间,判断是否只是小样本巧合' },
  { t: '联网查一下阵容伤停和轮换', d: '核实核心球员缺阵、赛程密度与战意' },
  { t: '七因子和实时数据有冲突吗', d: '对比已存预测与当前盘口、同赔是否一致' },
]

const quicks = [
  '综合分析这场',
  '同赔样本可靠吗',
  '联网查一下阵容伤停和轮换',
  '七因子和实时数据有冲突吗',
  '最可能出错的点是什么',
]

const DIR = { upper: '上盘(让球方)', lower: '下盘(受让方)', neutral: '无明确倾向' }
const CONF = { high: '高', medium: '中', low: '低' }
const dirLabel = (d) => DIR[d] || d
const confLabel = (c) => CONF[c] || c

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

const TAGS = { '盘口': 'ah', '同赔': 'f6', '多因子': 'mf', '基本面': 'fund' }
function tagOf(t) {
  const m = String(t || '').match(/^【(盘口|同赔|多因子|基本面)】\s*(.*)$/)
  return m ? { tag: m[1], cls: TAGS[m[1]], text: m[2] } : { tag: '', cls: '', text: String(t || '') }
}
function isLong(m) {
  const n = String(m.content || '').length
  return m.verdict ? n > 160 : n > 420
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

  let verdict = null
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
      } else if (ev.type === 'verdict') {
        verdict = ev.verdict
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
    messages.value.push(reactive({ tmp: ++tmpSeq, role: 'assistant', content: body, verdict, sources, _open: false }))
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

/* 结论卡 */
.mc-verdict {
  border-radius: 6rpx; padding: 18rpx 20rpx 16rpx; margin-bottom: 14rpx;
  background: #f8fafc; border-left: 6rpx solid #94a3b8;
  &.upper { background: #fef2f2; border-left-color: #dc2626; .mc-v-dir { color: #dc2626; } }
  &.lower { background: #ecfdf5; border-left-color: #059669; .mc-v-dir { color: #059669; } }
}
.mc-v-top { display: flex; align-items: center; gap: 14rpx; }
.mc-v-dir { font-size: 32rpx; font-weight: 800; color: #475569; letter-spacing: 1rpx; }
.mc-v-conf {
  font-size: 20rpx; padding: 2rpx 12rpx; border-radius: 6rpx;
  color: #64748b; background: rgba(255, 255, 255, 0.8); border: 1rpx solid #e2e8f0;
  &.high { color: #b91c1c; border-color: #fecaca; }
  &.medium { color: #b45309; border-color: #fde68a; }
  &.low { color: #64748b; }
}
.mc-v-head { display: block; font-size: 25rpx; font-weight: 600; color: #0f172a; line-height: 1.5; margin-top: 8rpx; }
.mc-v-block {
  display: flex; flex-direction: column; gap: 8rpx;
  margin-top: 14rpx; padding-top: 12rpx; border-top: 1rpx solid rgba(15, 23, 42, 0.08);
}
.mc-v-title { font-size: 20rpx; font-weight: 700; color: #64748b; letter-spacing: 2rpx; }
.mc-v-row { display: flex; align-items: flex-start; gap: 10rpx; }
.mc-v-item { font-size: 23rpx; color: #1e293b; line-height: 1.55; word-break: break-all; }
.mc-v-fact { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2rpx; }
.mc-v-src { font-size: 19rpx; color: #94a3b8; }
.mc-v-tag, .mc-v-st {
  flex-shrink: 0; font-size: 19rpx; font-weight: 600; line-height: 1;
  padding: 5rpx 10rpx; border-radius: 6rpx; margin-top: 4rpx;
}
.mc-v-tag {
  color: #475569; background: #e2e8f0;
  &.ah { color: #1d4ed8; background: #dbeafe; }
  &.f6 { color: #7c3aed; background: #ede9fe; }
  &.mf { color: #0f766e; background: #ccfbf1; }
  &.fund { color: #b45309; background: #fef3c7; }
}
.mc-v-st {
  &.confirmed { color: #047857; background: #d1fae5; }
  &.pending { color: #b45309; background: #fef3c7; }
}
.mc-v-dot { flex-shrink: 0; width: 8rpx; height: 8rpx; border-radius: 50%; background: #f59e0b; margin: 14rpx 4rpx 0; }
.mc-body.clamp {
  max-height: 210rpx; overflow: hidden; position: relative;
  &::after {
    content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 70rpx;
    background: linear-gradient(to bottom, rgba(255, 255, 255, 0), #fff);
  }
}
.mc-more { font-size: 22rpx; color: #0d9488; padding: 8rpx 0 2rpx; font-weight: 600; }

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

/* 联网来源 */
.mc-src { margin-top: 12rpx; border-top: 1rpx dashed #e2e8f0; padding-top: 10rpx; }
.mc-src-head {
  display: flex; align-items: center; gap: 8rpx; font-size: 21rpx; color: #64748b;
  .ico { width: 24rpx; height: 24rpx; }
}
.mc-src-arrow { margin-left: auto; color: #0d9488; }
.mc-src-list { display: flex; flex-direction: column; gap: 6rpx; margin-top: 8rpx; }
.mc-src-item { font-size: 21rpx; color: #0d9488; line-height: 1.5; word-break: break-all; }

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

/* ===== 空状态 ===== */
.mc-empty {
  display: flex; flex-direction: column; gap: 18rpx;
  background: #fff; border: 1rpx solid #d9ece8; border-radius: 6rpx;
  padding: 28rpx 26rpx 24rpx; margin-top: 6rpx;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.06);
}
.mc-empty-head { display: flex; align-items: center; gap: 18rpx; }
.mc-badge {
  width: 72rpx; height: 72rpx; border-radius: 6rpx; flex-shrink: 0;
  background: linear-gradient(135deg, #0d9488, #14b8a6); color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4rpx 12rpx rgba(13, 148, 136, 0.3);
  .ico { width: 40rpx; height: 40rpx; }
}
.mc-empty-titles { display: flex; flex-direction: column; gap: 4rpx; }
.mc-empty-title { font-size: 32rpx; font-weight: 700; color: #0f172a; }
.mc-empty-sub { font-size: 22rpx; color: #64748b; }
.mc-caps { display: flex; flex-wrap: wrap; gap: 10rpx; }
.mc-cap {
  font-size: 21rpx; color: #334155; background: #f1f5f9;
  padding: 4rpx 14rpx; border-radius: 6rpx;
  &.web { color: #0f766e; background: #f0fdfa; }
  &.img { color: #b45309; background: #fffbeb; }
}
.mc-starter-label { font-size: 22rpx; color: #94a3b8; margin-top: 6rpx; }
.mc-starters { display: flex; flex-direction: column; gap: 12rpx; }
.mc-starter {
  display: flex; align-items: center; gap: 12rpx;
  padding: 18rpx 20rpx; border-radius: 6rpx;
  background: #f8fafc; border: 1rpx solid #e2e8f0;
  &:active { background: #f0fdfa; border-color: #99f6e4; }
}
.mc-st-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.mc-st-t { font-size: 26rpx; font-weight: 600; color: #0f172a; }
.mc-st-d { font-size: 21rpx; color: #64748b; line-height: 1.5; }
.mc-st-go { font-size: 34rpx; color: #94a3b8; flex-shrink: 0; }
.mc-empty-note { font-size: 20rpx; color: #94a3b8; line-height: 1.6; margin-top: 4rpx; }

/* ===== 底部输入区 ===== */
.mc-quick { white-space: nowrap; padding: 14rpx 0 0; }
.mc-quick-row { display: inline-flex; gap: 10rpx; padding: 0 24rpx; }
.mc-q {
  font-size: 22rpx; color: #0f766e; background: #f0fdfa; border: 1rpx solid #99f6e4;
  border-radius: 6rpx; padding: 6rpx 16rpx; white-space: nowrap;
}
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
</style>
