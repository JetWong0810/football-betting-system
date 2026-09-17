<template>
  <view>
    <view class="intel-mask" v-if="visible" @tap="emit('close')"></view>
    <view class="intel-modal" :class="{ show: visible }">
      <view class="intel-header">
        <view class="intel-title-wrap">
          <text class="intel-title">基本面</text>
          <text class="intel-tag">参考</text>
          <text v-if="statusLabel" class="intel-status" :class="statusClass">{{ statusLabel }}</text>
        </view>
        <text class="intel-close" @tap="emit('close')">关闭</text>
      </view>

      <view class="intel-body">
        <view v-if="loading" class="intel-state">
          <text>加载中</text>
        </view>
        <view v-else-if="!data || !data.available" class="intel-state">
          <text>{{ emptyText }}</text>
        </view>
        <view v-else class="intel-content">
          <view class="hero">
            <view class="hero-side">
              <text class="hero-name">{{ data.homeTeam }}</text>
              <view class="hero-meta">
                <text v-if="pred.home.formation" class="form">{{ pred.home.formation }}</text>
                <text v-if="pred.home.confidence != null" class="conf">{{ pct(pred.home.confidence) }}</text>
              </view>
              <text v-if="stand.home" class="rank">{{ standLine(stand.home) }}</text>
            </view>
            <text class="hero-vs">vs</text>
            <view class="hero-side away">
              <text class="hero-name">{{ data.awayTeam }}</text>
              <view class="hero-meta">
                <text v-if="pred.away.formation" class="form">{{ pred.away.formation }}</text>
                <text v-if="pred.away.confidence != null" class="conf">{{ pct(pred.away.confidence) }}</text>
              </view>
              <text v-if="stand.away" class="rank">{{ standLine(stand.away) }}</text>
            </view>
          </view>

          <view v-if="metaChips.length" class="chip-row">
            <text v-for="(c, i) in metaChips" :key="'m'+i" class="chip mute">{{ c }}</text>
          </view>

          <view v-if="insights.length" class="sec">
            <text class="sec-h">推断</text>
            <view class="insight">
              <text v-for="(x, i) in insights" :key="'i'+i" class="insight-item" :class="x.tone">{{ x.text }}</text>
            </view>
            <text class="hint dim">仅作辅助，不改变七因子方向</text>
          </view>

          <view class="sec" v-if="unav.home.length || unav.away.length">
            <text class="sec-h">伤停</text>
            <view class="duo">
              <view class="card">
                <text class="card-h">{{ data.homeTeam }}</text>
                <view v-if="!unav.home.length" class="empty">无记录</view>
                <view v-for="p in unav.home" :key="'h'+p.id" class="unav-row">
                  <text class="unav-st" :class="p.status">{{ statusZh(p.status) }}</text>
                  <text class="unav-n">{{ p.name }}</text>
                  <text class="unav-r">{{ reasonZh(p.reason) }}</text>
                </view>
              </view>
              <view class="card">
                <text class="card-h">{{ data.awayTeam }}</text>
                <view v-if="!unav.away.length" class="empty">无记录</view>
                <view v-for="p in unav.away" :key="'a'+p.id" class="unav-row">
                  <text class="unav-st" :class="p.status">{{ statusZh(p.status) }}</text>
                  <text class="unav-n">{{ p.name }}</text>
                  <text class="unav-r">{{ reasonZh(p.reason) }}</text>
                </view>
              </view>
            </view>
          </view>

          <view class="sec">
            <view class="sec-h-row">
              <text class="sec-h">阵容近况</text>
              <view class="side-tabs">
                <text class="tab" :class="{ on: viewSide === 'home' }" @tap="viewSide = 'home'">{{ data.homeTeam }}</text>
                <text class="tab" :class="{ on: viewSide === 'away' }" @tap="viewSide = 'away'">{{ data.awayTeam }}</text>
              </view>
            </view>

            <view class="card xi-card">
              <view class="card-h-row">
                <text class="card-h">本场 XI</text>
                <text v-if="curPred.formation" class="form">{{ curPred.formation }}</text>
                <text v-if="curPred.confidence != null" class="conf">{{ pct(curPred.confidence) }}</text>
              </view>
              <view v-if="!xiGroups.length" class="empty">未公布</view>
              <view v-for="g in xiGroups" :key="g.key" class="xi-group">
                <text class="xi-lab">{{ g.label }}</text>
                <view class="xi-names">
                  <view v-for="p in g.players" :key="p.id" class="xi-chip">
                    <text v-if="p.num" class="xi-num">{{ p.num }}</text>
                    <text>{{ p.name }}</text>
                    <text v-if="p.captain" class="xi-c">C</text>
                  </view>
                </view>
              </view>
            </view>

            <scroll-view v-if="hasMatrix" class="mx-scroll" scroll-x :show-scrollbar="false">
              <view class="mx">
                <view class="mx-row mx-head">
                  <text class="mx-name hd">近 5 场首发</text>
                  <text class="mx-role hd">角色</text>
                  <text v-for="c in matrix.cols" :key="c.id" class="mx-cell hd">{{ c.label }}</text>
                  <text class="mx-cell hd tonight">本场</text>
                </view>
                <view
                  v-for="r in matrix.rows"
                  :key="r.id"
                  class="mx-row"
                  :class="{ out: !r.inTonight }"
                >
                  <text class="mx-name">{{ r.name }}</text>
                  <text class="mx-role" :class="r.role">{{ r.role }}</text>
                  <text
                    v-for="(cell, i) in r.cells"
                    :key="i"
                    class="mx-cell"
                    :class="cell === '首' ? 'on' : 'off'"
                  >{{ cell }}</text>
                  <text class="mx-cell tonight" :class="r.inTonight ? 'on now' : 'off'">{{ r.inTonight ? '首' : '-' }}</text>
                </view>
              </view>
            </scroll-view>
            <text v-if="matrix.note" class="hint">{{ matrix.note }}</text>
          </view>

          <view class="sec">
            <text class="sec-h">教练</text>
            <view class="duo">
              <view class="card">
                <text class="card-h">{{ data.homeTeam }}</text>
                <text class="coach-n">{{ mgrName('home') }}</text>
                <text class="coach-d">{{ mgrDesc('home') }}</text>
              </view>
              <view class="card">
                <text class="card-h">{{ data.awayTeam }}</text>
                <text class="coach-n">{{ mgrName('away') }}</text>
                <text class="coach-d">{{ mgrDesc('away') }}</text>
              </view>
            </view>
            <text v-if="coachFormHint" class="hint">{{ coachFormHint }}</text>
          </view>

          <view class="sec" v-if="stand.home || stand.away">
            <text class="sec-h">积分</text>
            <view class="tbl">
              <view class="tbl-row hd">
                <text class="c-pos">名</text>
                <text class="c-team">球队</text>
                <text class="c-n">赛</text>
                <text class="c-n">胜</text>
                <text class="c-n">平</text>
                <text class="c-n">负</text>
                <text class="c-n">分</text>
                <text class="c-form">近况</text>
              </view>
              <view v-if="stand.home" class="tbl-row">
                <text class="c-pos">{{ stand.home.position }}</text>
                <text class="c-team">{{ data.homeTeam }}</text>
                <text class="c-n">{{ stand.home.played }}</text>
                <text class="c-n">{{ stand.home.won }}</text>
                <text class="c-n">{{ stand.home.drawn }}</text>
                <text class="c-n">{{ stand.home.lost }}</text>
                <text class="c-n pts">{{ stand.home.pts }}</text>
                <text class="c-form">{{ stand.home.form || '—' }}</text>
              </view>
              <view v-if="stand.away" class="tbl-row">
                <text class="c-pos">{{ stand.away.position }}</text>
                <text class="c-team">{{ data.awayTeam }}</text>
                <text class="c-n">{{ stand.away.played }}</text>
                <text class="c-n">{{ stand.away.won }}</text>
                <text class="c-n">{{ stand.away.drawn }}</text>
                <text class="c-n">{{ stand.away.lost }}</text>
                <text class="c-n pts">{{ stand.away.pts }}</text>
                <text class="c-form">{{ stand.away.form || '—' }}</text>
              </view>
            </view>
          </view>

          <view class="sec" v-if="h2hLine">
            <text class="sec-h">交锋</text>
            <text class="h2h">{{ h2hLine }}</text>
            <view class="h2h-list" v-if="h2hRecent.length">
              <text v-for="(x, i) in h2hRecent" :key="i" class="h2h-item">{{ x }}</text>
            </view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { request } from '@/utils/http'

const props = defineProps({
  visible: { type: Boolean, default: false },
  matchId: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const data = ref(null)
const errText = ref('')
const viewSide = ref('home')

watch(
  () => [props.visible, props.matchId],
  ([vis, id]) => {
    if (!vis || !id) return
    viewSide.value = 'home'
    load(id)
  },
)

async function load(id) {
  loading.value = true
  errText.value = ''
  data.value = null
  try {
    const res = await request({
      url: `/api/predict/${encodeURIComponent(id)}/intel`,
      method: 'GET',
      timeout: 60000,
    })
    if (props.matchId === id) data.value = res
  } catch (e) {
    if (props.matchId === id) {
      errText.value = e?.message || '加载失败'
      data.value = { available: false }
    }
  } finally {
    if (props.matchId === id) loading.value = false
  }
}

const emptyText = computed(() => {
  if (data.value?.reason === 'unmatched') return '该场暂无覆盖（亚运等）'
  return errText.value || '暂无数据'
})

const statusLabel = computed(() => {
  const s = data.value?.lineupStatus
  if (s === 'predicted') return '预计阵容'
  if (s === 'confirmed') return '确认首发'
  return ''
})
const statusClass = computed(() => (data.value?.lineupStatus === 'confirmed' ? 'ok' : 'pred'))

const pred = computed(() => ({
  home: data.value?.predicted?.home || { players: [] },
  away: data.value?.predicted?.away || { players: [] },
}))
const unav = computed(() => ({
  home: data.value?.unavailable?.home || [],
  away: data.value?.unavailable?.away || [],
}))
const curPred = computed(() => pred.value[viewSide.value] || { players: [] })

const POS_ORDER = ['G', 'D', 'M', 'F']
const POS_LABEL = { G: '门', D: '卫', M: '中', F: '前' }

const xiGroups = computed(() => {
  const players = [...(curPred.value.players || [])]
  const buckets = {}
  for (const p of players) {
    const k = POS_ORDER.includes(p.pos) ? p.pos : 'M'
    if (!buckets[k]) buckets[k] = []
    buckets[k].push(p)
  }
  for (const k of Object.keys(buckets)) {
    buckets[k].sort((a, b) => (Number(a.num) || 99) - (Number(b.num) || 99))
  }
  return POS_ORDER.filter((k) => buckets[k]?.length).map((k) => ({
    key: k,
    label: POS_LABEL[k],
    players: buckets[k],
  }))
})

function tableRows() {
  const s = data.value?.standings
  if (!s) return []
  if (Array.isArray(s.standings)) return s.standings
  if (Array.isArray(s.results)) return s.results
  return []
}
function pickStand(side) {
  const rows = tableRows()
  if (!rows.length) return null
  const id = side === 'home' ? data.value?.homeTeamId : data.value?.awayTeamId
  let hit = null
  if (id != null) hit = rows.find((r) => r.team_id === id) || null
  if (!hit) {
    const en = side === 'home' ? data.value?.bsdHome : data.value?.bsdAway
    hit = rows.find((r) => r.team_name === en) || null
  }
  if (!hit) return null
  if (!hit.played) return null
  return hit
}
const stand = computed(() => ({
  home: pickStand('home'),
  away: pickStand('away'),
}))
function standLine(r) {
  if (!r) return ''
  const bits = [`第${r.position}`]
  if (r.pts != null) bits.push(`${r.pts}分`)
  if (r.played != null) bits.push(`${r.played}轮`)
  return bits.join(' · ')
}

const metaChips = computed(() => {
  const d = data.value
  if (!d) return []
  const chips = []
  const v = d.venue
  if (v?.name) chips.push([v.city, v.name].filter(Boolean).join(' · '))
  const w = d.weather || {}
  const wbits = []
  if (w.temperature_c != null) wbits.push(`${Math.round(w.temperature_c)}°C`)
  if (w.wind_speed != null) wbits.push(`风${Number(w.wind_speed).toFixed(0)}`)
  if (w.description && w.description !== 'unknown') wbits.unshift(w.description)
  if (wbits.length) chips.push(wbits.join(' · '))
  if (d.travelKm != null) chips.push(`客队 ${Math.round(d.travelKm)} km`)
  if (d.isDerby) chips.push('德比')
  if (d.isNeutral) chips.push('中立')
  return chips
})

function statusZh(s) {
  if (s === 'injured') return '伤'
  if (s === 'doubtful') return '疑'
  if (s === 'suspended') return '停'
  return s || '缺'
}
function reasonZh(r) {
  if (!r) return ''
  const map = {
    'Muscle Injury': '肌肉',
    'Meniscus Injury': '半月板',
    'Shoulder Injury': '肩',
    'Virus': '病毒',
    'Physical Discomfort': '身体不适',
    'Knee Injury': '膝',
    'Ankle Injury': '踝',
    'Hamstring': '腘绳',
    'Hamstring Injury': '腘绳',
    'Cruciate Ligament Injury': '十字韧带',
    'Thigh Injury': '大腿',
    'Calf Injury': '小腿',
    'Groin Injury': '腹股沟',
    'Back Injury': '腰背',
    'Foot Injury': '脚',
    'Illness': '生病',
    'Knock': '撞伤',
    'red_card_suspension': '红牌停',
    'Red Card': '红牌停',
    'Suspension': '停赛',
    'Yellow Cards': '黄牌停',
  }
  if (map[r]) return map[r]
  if (/red[_ ]?card/i.test(r)) return '红牌停'
  if (/yellow/i.test(r)) return '黄牌停'
  return r.replace(/_/g, ' ')
}
function pct(n) {
  if (n == null) return ''
  return `${Math.round(Number(n) * 100)}%`
}
function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${m}-${day}`
}

function mgr(side) {
  return data.value?.managers?.[side] || null
}
function mgrName(side) {
  return mgr(side)?.short_name || mgr(side)?.name || '—'
}
function mgrDesc(side) {
  const m = mgr(side)
  if (!m) return ''
  const bits = []
  const style = {
    attacking: '进攻',
    defensive: '防守',
    possession: '控球',
    balanced: '均衡',
  }[m.tactical_profile] || m.tactical_profile
  if (style) bits.push(style)
  if (m.preferred_formation) bits.push(m.preferred_formation)
  if (m.win_pct != null) bits.push(`胜率${Math.round(Number(m.win_pct))}%`)
  if (m.avg_goals_scored != null && m.avg_goals_conceded != null) {
    bits.push(`场均${Number(m.avg_goals_scored).toFixed(1)}/${Number(m.avg_goals_conceded).toFixed(1)}`)
  }
  return bits.join(' · ')
}

const coachFormHint = computed(() => {
  const d = data.value
  if (!d) return ''
  const bits = []
  for (const side of ['home', 'away']) {
    const form = pred.value[side]?.formation
    const pref = mgr(side)?.preferred_formation
    const team = side === 'home' ? d.homeTeam : d.awayTeam
    if (form && pref && form !== pref) bits.push(`${team} 本场 ${form}，惯用 ${pref}`)
  }
  return bits.join('；')
})

function buildMatrix(side) {
  const tonight = pred.value[side]?.players || []
  const recent = [...(data.value?.recentLineups?.[side] || [])]
    .filter((g) => g?.lineups)
    .sort((a, b) => String(a.event_date || '').localeCompare(String(b.event_date || '')))
    .slice(-5)
  const cols = recent.map((g) => {
    const block = g.lineups?.[g.side] || {}
    const players = block.players || []
    return {
      id: g.event_id,
      label: fmtDate(g.event_date),
      ids: new Set(players.map((p) => p.id)),
    }
  })
  const tonightIds = new Set(tonight.map((p) => p.id))
  const byId = {}
  for (const p of tonight) byId[p.id] = p
  for (const g of recent) {
    const players = g.lineups?.[g.side]?.players || []
    for (const p of players) {
      if (!byId[p.id]) byId[p.id] = p
    }
  }
  const rest = Object.values(byId).filter((p) => !tonightIds.has(p.id))
  const last = cols[cols.length - 1]
  const rows = [...tonight, ...rest].map((p) => {
    const starts = cols.filter((c) => c.ids.has(p.id)).length
    const n = cols.length
    let role = '—'
    if (n >= 3) {
      const r = starts / n
      role = r >= 0.7 ? '主力' : r >= 0.3 ? '轮换' : '边缘'
    }
    const inTonight = tonightIds.has(p.id)
    const inLast = last ? last.ids.has(p.id) : false
    return {
      id: p.id,
      name: p.short_name || p.name,
      inTonight,
      role,
      starts,
      n,
      inLast,
      cells: cols.map((c) => (c.ids.has(p.id) ? '首' : '-')),
    }
  }).filter((r) => r.inTonight || r.starts >= 2 || (r.role === '主力' && !r.inTonight))

  const dropped = rows.filter((r) => !r.inTonight && r.role === '主力')
  const added = rows.filter((r) => r.inTonight && last && !r.inLast && r.role !== '主力')
  const notes = []
  if (dropped.length) notes.push(`相对近况未上主力 ${dropped.map((x) => x.name).join('、')}`)
  if (added.length) notes.push(`轮换顶上 ${added.map((x) => x.name).join('、')}`)
  return { cols, rows, note: notes.join('；'), dropped, added }
}

const matrix = computed(() => buildMatrix(viewSide.value))
const hasMatrix = computed(() => (matrix.value.cols || []).length > 0)

const insights = computed(() => {
  const d = data.value
  if (!d) return []
  const out = []
  const names = (list) => list.slice(0, 2).map((p) => p.name).join('、')
  if (unav.value.home.length) {
    const extra = unav.value.home.length > 2 ? ' 等' : ''
    out.push({ text: `${d.homeTeam}伤停 ${unav.value.home.length}人：${names(unav.value.home)}${extra}`, tone: unav.value.home.length >= 4 ? 'warn' : '' })
  }
  if (unav.value.away.length) {
    const extra = unav.value.away.length > 2 ? ' 等' : ''
    out.push({ text: `${d.awayTeam}伤停 ${unav.value.away.length}人：${names(unav.value.away)}${extra}`, tone: unav.value.away.length >= 4 ? 'warn' : '' })
  }
  const hm = buildMatrix('home')
  const am = buildMatrix('away')
  if (hm.dropped.length) out.push({ text: `${d.homeTeam}主力未上 ${hm.dropped.map((x) => x.name).join('、')}`, tone: 'warn' })
  if (am.dropped.length) out.push({ text: `${d.awayTeam}主力未上 ${am.dropped.map((x) => x.name).join('、')}`, tone: 'warn' })
  if (coachFormHint.value) out.push({ text: coachFormHint.value, tone: '' })
  if (d.travelKm != null && d.travelKm >= 300) {
    out.push({ text: `客队行程 ${Math.round(d.travelKm)} km`, tone: d.travelKm >= 800 ? 'warn' : '' })
  }
  const t = d.weather?.temperature_c
  if (t != null && (t >= 30 || t <= 5)) {
    out.push({ text: t >= 30 ? `场地偏热 ${Math.round(t)}°C` : `场地偏冷 ${Math.round(t)}°C`, tone: '' })
  }
  const sh = stand.value.home
  const sa = stand.value.away
  if (sh && sa && sh.played && sa.played && Math.abs(sh.position - sa.position) >= 6) {
    const lead = sh.position < sa.position ? d.homeTeam : d.awayTeam
    out.push({ text: `积分榜 ${lead}高 ${Math.abs(sh.position - sa.position)} 位（${sh.position} vs ${sa.position}）`, tone: '' })
  }
  if (d.lineupStatus === 'predicted') out.push({ text: '首发尚未确认，阵容为模型预计', tone: 'mute' })
  return out
})

function zhTeam(en) {
  if (!en || !data.value) return en || ''
  if (en === data.value.bsdHome) return data.value.homeTeam
  if (en === data.value.bsdAway) return data.value.awayTeam
  return en
}

const h2hLine = computed(() => {
  const h = data.value?.h2h
  if (!h || !h.total_matches) return ''
  return `近${h.total_matches}次  主${h.home_wins} 平${h.draws} 客${h.away_wins}`
})
const h2hRecent = computed(() => {
  const list = data.value?.h2h?.recent_matches || []
  return list.slice(0, 5).map((x) => {
    const score = x.score || `${x.home_score}-${x.away_score}`
    return `${fmtDate(x.date)}  ${zhTeam(x.home)} ${score} ${zhTeam(x.away)}`
  })
})
</script>

<style lang="scss" scoped>
.intel-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.4); z-index: 220;
}
.intel-modal {
  position: fixed; top: 50%; left: 3vw; right: 3vw; bottom: auto;
  max-height: 88vh; height: auto;
  background: #fff; border-radius: 12rpx; z-index: 221;
  display: flex; flex-direction: column;
  overflow: hidden;
  transform: translateY(-50%) scale(0.96); opacity: 0;
  transition: transform 0.2s ease, opacity 0.2s ease;
  pointer-events: none;
  &.show { transform: translateY(-50%) scale(1); opacity: 1; pointer-events: auto; }
}
.intel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20rpx 24rpx; border-bottom: 1rpx solid #e2e8f0; flex-shrink: 0;
  position: relative; z-index: 2; background: #fff;
}
.intel-title-wrap { display: flex; align-items: center; gap: 10rpx; min-width: 0; flex-wrap: wrap; }
.intel-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
.intel-tag {
  font-size: 18rpx; color: #0f766e; background: #ccfbf1;
  border-radius: 6rpx; padding: 2rpx 8rpx;
}
.intel-status {
  font-size: 18rpx; border-radius: 6rpx; padding: 2rpx 8rpx;
  &.pred { color: #b45309; background: #fffbeb; }
  &.ok { color: #047857; background: #ecfdf5; }
}
.intel-close { font-size: 24rpx; color: $frbt-primary; padding: 8rpx 4rpx; }
.intel-body {
  max-height: calc(88vh - 88rpx);
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  min-height: 0;
}
.intel-state {
  padding: 80rpx 32rpx; text-align: center; font-size: 24rpx; color: #64748b;
}
.intel-content { padding: 20rpx 20rpx 36rpx; }

.hero {
  display: flex; align-items: flex-start; gap: 12rpx; margin-bottom: 14rpx;
}
.hero-side {
  flex: 1; min-width: 0;
  &.away { text-align: right; }
  &.away .hero-meta { justify-content: flex-end; }
}
.hero-name {
  display: block; font-size: 30rpx; font-weight: 650; color: #0f172a;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.hero-vs {
  flex-shrink: 0; font-size: 20rpx; color: #94a3b8;
  padding-top: 8rpx;
}
.hero-meta {
  display: flex; align-items: center; gap: 6rpx; margin-top: 6rpx; flex-wrap: wrap;
}
.rank { display: block; margin-top: 4rpx; font-size: 20rpx; color: #64748b; }

.chip-row { display: flex; flex-wrap: wrap; gap: 8rpx; margin-bottom: 16rpx; }
.chip {
  font-size: 20rpx; border-radius: 6rpx; padding: 4rpx 10rpx;
  &.mute { color: #475569; background: #f1f5f9; }
}

.sec { margin-bottom: 24rpx; }
.sec-h {
  display: block; font-size: 22rpx; font-weight: 650; color: #0f766e;
  letter-spacing: 0.04em; margin-bottom: 10rpx;
  padding-left: 10rpx; border-left: 6rpx solid #0d9488;
}
.sec-h-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8rpx; margin-bottom: 10rpx;
  .sec-h { margin-bottom: 0; }
}
.side-tabs { display: flex; gap: 6rpx; }
.tab {
  font-size: 20rpx; color: #64748b; background: #f8fafc;
  border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 4rpx 10rpx;
  max-width: 180rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  &.on { color: #fff; background: #0f766e; border-color: #0f766e; }
}

.insight {
  background: #f8fafb; border: 1rpx solid #e2e8f0; border-radius: 6rpx;
  padding: 10rpx 14rpx;
}
.insight-item {
  display: block; font-size: 22rpx; color: #334155; line-height: 1.55;
  &.warn { color: #b45309; }
  &.mute { color: #64748b; }
}

.duo { display: flex; gap: 10rpx; }
.card {
  flex: 1; min-width: 0; background: #f8fafb; border: 1rpx solid #e2e8f0;
  border-radius: 6rpx; padding: 12rpx;
}
.xi-card { margin-bottom: 12rpx; }
.card-h-row { display: flex; align-items: center; gap: 6rpx; margin-bottom: 8rpx; flex-wrap: wrap; }
.card-h { font-size: 20rpx; font-weight: 650; color: #334155; margin-bottom: 6rpx; }
.card-h-row .card-h { margin-bottom: 0; }
.form {
  font-size: 18rpx; font-weight: 650; color: #0f766e; background: #ccfbf1;
  border-radius: 6rpx; padding: 0 8rpx; line-height: 1.5;
  font-variant-numeric: tabular-nums;
}
.conf { font-size: 18rpx; color: #94a3b8; }
.empty { font-size: 20rpx; color: #94a3b8; padding: 8rpx 0; }

.unav-row {
  display: flex; align-items: baseline; gap: 6rpx;
  font-size: 20rpx; line-height: 1.55; font-variant-numeric: tabular-nums;
}
.unav-st {
  width: 32rpx; flex-shrink: 0; font-size: 18rpx; font-weight: 650;
  &.injured { color: #b45309; }
  &.doubtful { color: #a16207; }
  &.suspended { color: #7c3aed; }
}
.unav-n { color: #1e293b; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.unav-r { color: #94a3b8; flex-shrink: 0; font-size: 18rpx; max-width: 120rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.xi-group { display: flex; gap: 8rpx; margin-bottom: 8rpx; }
.xi-lab {
  width: 32rpx; flex-shrink: 0; font-size: 20rpx; color: #94a3b8; padding-top: 4rpx;
}
.xi-names { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 6rpx; }
.xi-chip {
  display: flex; align-items: baseline; gap: 4rpx;
  font-size: 20rpx; color: #1e293b; background: #fff;
  border: 1rpx solid #e2e8f0; border-radius: 6rpx; padding: 2rpx 8rpx;
  line-height: 1.5;
}
.xi-num { color: #94a3b8; margin-right: 4rpx; font-variant-numeric: tabular-nums; }
.xi-c { color: #0f766e; font-weight: 650; margin-left: 4rpx; font-size: 16rpx; }

.hint { display: block; margin-top: 8rpx; font-size: 20rpx; color: #64748b; line-height: 1.5; }
.hint.dim { color: #94a3b8; font-size: 18rpx; }
.coach-n { display: block; font-size: 24rpx; font-weight: 650; color: #0f172a; }
.coach-d { display: block; font-size: 20rpx; color: #64748b; margin-top: 4rpx; line-height: 1.45; }
.h2h { display: block; font-size: 22rpx; color: #334155; margin-bottom: 8rpx; }
.h2h-list { display: flex; flex-direction: column; gap: 4rpx; }
.h2h-item { font-size: 20rpx; color: #64748b; }

.tbl { border: 1rpx solid #e2e8f0; border-radius: 6rpx; overflow: hidden; }
.tbl-row {
  display: flex; align-items: center; padding: 8rpx 10rpx;
  border-bottom: 1rpx solid #f1f5f9; font-size: 20rpx; color: #334155;
  font-variant-numeric: tabular-nums;
  &:last-child { border-bottom: 0; }
  &.hd { background: #f8fafb; color: #94a3b8; font-size: 18rpx; }
}
.c-pos { width: 44rpx; flex-shrink: 0; }
.c-team { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-n { width: 44rpx; flex-shrink: 0; text-align: right; }
.c-n.pts { font-weight: 650; color: #0f172a; }
.c-form { width: 88rpx; flex-shrink: 0; text-align: right; font-size: 18rpx; color: #64748b; letter-spacing: 1rpx; }

.mx-scroll { width: 100%; }
.mx { display: inline-block; min-width: 100%; }
.mx-row {
  display: flex; align-items: center; border-bottom: 1rpx solid #f1f5f9;
  &.out .mx-name { color: #94a3b8; }
}
.mx-head { border-bottom: 1rpx solid #e2e8f0; position: sticky; top: 0; z-index: 1; background: #fff; }
.mx-name {
  width: 140rpx; flex-shrink: 0; font-size: 20rpx; color: #1e293b;
  padding: 8rpx 6rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  &.hd { color: #94a3b8; font-size: 18rpx; }
}
.mx-role {
  width: 56rpx; flex-shrink: 0; font-size: 18rpx; color: #64748b;
  &.主力 { color: #0f766e; font-weight: 650; }
  &.轮换 { color: #b45309; }
  &.hd { color: #94a3b8; }
}
.mx-cell {
  width: 72rpx; flex-shrink: 0; text-align: center; font-size: 20rpx;
  font-variant-numeric: tabular-nums; color: #cbd5e1;
  &.hd { font-size: 18rpx; color: #94a3b8; }
  &.on { color: #0f172a; font-weight: 650; }
  &.now { color: #0f766e; }
  &.tonight { width: 72rpx; }
}
</style>
