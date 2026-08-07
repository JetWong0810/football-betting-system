<template>
  <view class="batch-page" :class="{ 'sim-pad': simBet.hasLegs }">
    <view class="summary-bar">
      <view class="sum-row">
        <view class="date-nav">
          <text class="date-arr" :class="{ disabled: !prevSaleDate }" @tap.stop="goPrevDate">‹</text>
          <text class="sum-title date-tap" @tap="openCalendar">{{ dateLabel }} 同赔分析</text>
          <text class="date-arr" :class="{ disabled: !nextSaleDate }" @tap.stop="goNextDate">›</text>
        </view>
        <view class="sum-right">
          <text
            class="sim-toggle"
            :class="{ on: simBet.simMode }"
            @tap="simBet.toggleSimMode()"
          >模拟投注</text>
          <text class="sum-total">
            <template v-if="hasFilter">已筛 {{ filteredItems.length }}/{{ summary.total }}</template>
            <template v-else>{{ summary.total }} 场</template>
          </text>
        </view>
      </view>
      <view class="status-row">
        <text
          class="status-tab"
          :class="{ on: status === 'not_started' }"
          @tap="switchStatus('not_started')"
        >在售</text>
        <text
          class="status-tab"
          :class="{ on: status === 'finished' }"
          @tap="switchStatus('finished')"
        >已结束</text>
      </view>
      <view class="sum-stats">
        <text class="st upper">上盘 {{ summary.upper }}</text>
        <text class="st-sep">·</text>
        <text class="st lower">下盘 {{ summary.lower }}</text>
        <text class="st-sep">·</text>
        <text class="st neutral">中性 {{ summary.neutral }}</text>
        <template v-if="isFinished && summary.hitTotal">
          <text class="st-sep">·</text>
          <text class="st hit">命中 {{ summary.hitRate }}%</text>
        </template>
      </view>
      <view v-if="isFinished && summary.hitTotal" class="sum-stats single-split">
        <text class="st single-stat">单关 {{ summary.single?.hitRate ?? 0 }}%（{{ summary.single?.hits || 0 }}/{{ summary.single?.total || 0 }}）</text>
        <text class="st-sep">·</text>
        <text class="st">非单 {{ summary.nonSingle?.hitRate ?? 0 }}%（{{ summary.nonSingle?.hits || 0 }}/{{ summary.nonSingle?.total || 0 }}）</text>
        <text v-if="summary.singleCount" class="st-sep">·</text>
        <text v-if="summary.singleCount" class="st">单关场 {{ summary.singleCount }}</text>
      </view>
      <view v-if="simBet.simMode && dateConfirmed.length" class="sum-sim-hist">
        <text
          v-for="s in dateConfirmed.slice(0, 3)"
          :key="s.id"
          class="sim-hist-item"
          :class="[s.status, s.result]"
        >{{ s.parlayLabel }} {{ s.combinedSafety }} · {{ slipResultLabel(s) }}{{ slipStakeBrief(s) }}{{ slipLegSettleBrief(s) }}</text>
      </view>
    </view>

    <view class="ctrl-bar" v-if="!loading && items.length">
      <view class="ctrl-row">
        <text class="ctrl-lab">排序</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'default' }" @tap="sortMode = 'default'">默认</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'time' }" @tap="sortMode = 'time'">时间</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'hitPct' }" @tap="sortMode = 'hitPct'">命中率</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'refScore' }" @tap="sortMode = 'refScore'">分数</text>
      </view>
      <view class="ctrl-row">
        <text class="ctrl-lab">筛选</text>
        <text class="ctrl-btn" :class="{ active: !dirFilters.length }" @tap="dirFilters = []">全部</text>
        <text class="ctrl-btn upper" :class="{ active: dirFilters.includes('upper') }" @tap="toggleFilter('upper')">上盘</text>
        <text class="ctrl-btn lower" :class="{ active: dirFilters.includes('lower') }" @tap="toggleFilter('lower')">下盘</text>
        <text class="ctrl-btn" :class="{ active: dirFilters.includes('neutral') }" @tap="toggleFilter('neutral')">中性</text>
        <text
          v-if="isFinished && summary.hitTotal"
          class="ctrl-btn hit"
          :class="{ active: dirFilters.includes('hit') }"
          @tap="toggleFilter('hit')"
        >命中</text>
        <text
          class="ctrl-btn sample"
          :class="{ active: dirFilters.includes('sample8') }"
          @tap="toggleFilter('sample8')"
        >同赔≥8</text>
        <text
          class="ctrl-btn hitpct"
          :class="{ active: dirFilters.includes('hitPct65') }"
          @tap="toggleFilter('hitPct65')"
        >命中≥65%</text>
        <text
          class="ctrl-btn score"
          :class="{ active: dirFilters.includes('score60') }"
          @tap="toggleFilter('score60')"
        >分数≥60</text>
        <text
          class="ctrl-btn single"
          :class="{ active: dirFilters.includes('single') }"
          @tap="toggleFilter('single')"
        >单关</text>
      </view>
      <view class="ctrl-row">
        <text class="ctrl-lab">变动</text>
        <text class="ctrl-btn" :class="{ active: !moveFilters.length }" @tap="moveFilters = []">全部</text>
        <text class="ctrl-btn move-up" :class="{ active: moveFilters.includes('up') }" @tap="toggleMoveFilter('up')">上升</text>
        <text class="ctrl-btn move-down" :class="{ active: moveFilters.includes('down') }" @tap="toggleMoveFilter('down')">下降</text>
        <text class="ctrl-btn" :class="{ active: moveFilters.includes('flat') }" @tap="toggleMoveFilter('flat')">不变</text>
      </view>
      <view class="filter-count" v-if="hasFilter">
        <text class="fc-main">已筛 {{ filteredItems.length }} 场</text>
        <text class="fc-sub">共 {{ summary.total }} 场</text>
        <text v-if="isFinished" class="fc-hit">命中 {{ filteredHitCount }}/{{ filteredItems.length }}</text>
        <text class="fc-clear" @tap="clearFilter">清除</text>
      </view>
    </view>

    <view v-if="loading" class="state-hint"><text>分析中…</text></view>
    <view v-else-if="items.length === 0" class="state-hint">
      <text>该日无{{ isFinished ? '已结束' : '在售' }}竞彩比赛</text>
    </view>
    <view v-else-if="filteredItems.length === 0" class="state-hint">
      <text>当前筛选无场次</text>
      <text class="state-clear" @tap="clearFilter">清除筛选</text>
    </view>

    <scroll-view v-else class="card-list" scroll-y>
      <view class="card-list-inner">
        <view
          v-for="it in filteredItems"
          :key="it.matchId"
          class="match-card"
        >
          <view class="row-meta">
            <text class="league">{{ it.league || '-' }}</text>
            <text class="time">{{ (it.matchTime || '').slice(0, 5) }}</text>
            <text v-if="it.isSingle" class="single-tag">单关</text>
            <view class="dir-wrap">
              <text class="dir" :class="[it.f6?.direction || 'neutral', refTier(it.f6)]">{{ dirLabel(it.f6?.direction) }}</text>
              <text
                v-if="it.f6?.refScore != null"
                class="ref-score"
                :class="[it.f6?.direction || 'neutral', refTier(it.f6)]"
              >{{ it.f6.refScore }}</text>
            </view>
            <view class="predict-icon" @tap.stop="goPredict(it)">
              <text class="predict-icon-text">预</text>
            </view>
          </view>
          <view v-if="simBet.simMode" class="row-sim">
            <text
              class="sim-pick"
              :class="{ disabled: it.ahHandicap == null, active: !!simBet.findLeg(it.matchId) }"
              @tap.stop="openSimPick(it)"
            >{{ simPickLabel(it) }}</text>
          </view>

          <view class="row-teams">
            <text class="team home">{{ it.homeTeam?.name }}</text>
            <text class="vs">vs</text>
            <text class="team away">{{ it.awayTeam?.name }}</text>
          </view>

          <!-- 核心结论 -->
          <view class="row-hit" v-if="ahStats(it.f6).total > 0">
            <view class="hit-top">
              <text class="pct" :class="focusSide(it.f6)">{{ focusPct(it.f6) }}%</text>
              <text class="pct-lab" :class="focusSide(it.f6)">{{ focusHitLabel(it.f6) }}</text>
              <text class="sample">{{ ahStats(it.f6).upper }}/{{ ahStats(it.f6).lower }}/{{ ahStats(it.f6).push }} · {{ ahStats(it.f6).total }}场</text>
            </view>
            <view class="bar">
              <view class="bar-u" :style="{ width: ahStats(it.f6).upperPct + '%' }"></view>
              <view class="bar-l" :style="{ width: ahStats(it.f6).lowerPct + '%' }"></view>
            </view>
            <text class="reason" v-if="it.f6?.reason">{{ shortReason(it.f6.reason) }}</text>
          </view>
          <view class="row-hit empty" v-else>
            <text class="reason">{{ it.f6?.reason || '暂无同赔样本' }}</text>
          </view>

          <view
            v-if="isJapanLeague(it.league)"
            class="row-jp"
            @tap.stop="openJapanIntel(it)"
          >
            <text class="jp-lab">日本情报</text>
            <text class="jp-sum">{{ japanSummary(it) }}</text>
            <text class="jp-go">详情 ›</text>
          </view>

          <!-- 亚盘盘口: 初/终; 无数据时显示「无数据」 -->
          <view class="row-ah">
            <text class="ah-lab">亚盘</text>
            <template v-if="hasAh(it)">
              <text class="ah-muted">初</text>
              <text class="ah-num">{{ ahOpenOf(it) != null ? fmtAh(ahOpenOf(it)) : '-' }}</text>
              <text class="ah-muted">→</text>
              <text class="ah-muted">终</text>
              <text class="ah-num">{{ ahCloseOf(it) != null ? fmtAh(ahCloseOf(it)) : '-' }}</text>
              <text v-if="ahMoveLabel(it)" class="ah-move" :class="ahMoveClass(it)">{{ ahMoveLabel(it) }}</text>
            </template>
            <text v-else class="ah-miss">无数据</text>
            <template v-if="isFinished && it.actualScore">
              <text class="ac-sep">·</text>
              <text class="ac-score">{{ it.actualScore }}</text>
              <text class="ac-sep">·</text>
              <text :class="resultClass(it.actualResult)">{{ it.actualResult || '-' }}</text>
              <text class="ac-sep">·</text>
              <text :class="ahResultClass(it.actualAh)">{{ it.actualAh || '-' }}</text>
              <text v-if="it.hit === true" class="ac-hit">命中</text>
              <text v-else-if="it.hit === false" class="ac-miss">未中</text>
            </template>
          </view>

          <!-- 赔率一行 -->
          <view class="row-odds" v-if="it.spf">
            <text class="ol-lab">竞彩</text>
            <text class="ol-muted">初</text>
            <text :class="lowClass(it.spf.initial, 'win')">{{ fmt(it.spf.initial.win) }}</text>
            <text :class="lowClass(it.spf.initial, 'draw')">{{ fmt(it.spf.initial.draw) }}</text>
            <text :class="lowClass(it.spf.initial, 'loss')">{{ fmt(it.spf.initial.lose) }}</text>
            <text class="ol-muted">→</text>
            <text class="ol-muted">终</text>
            <text :class="lowClass(it.spf.current, 'win')">{{ fmt(it.spf.current.win) }}</text>
            <text :class="lowClass(it.spf.current, 'draw')">{{ fmt(it.spf.current.draw) }}</text>
            <text :class="lowClass(it.spf.current, 'loss')">{{ fmt(it.spf.current.lose) }}</text>
            <text class="ol-move" :class="moveClass(it.spf)">{{ moveLabel(it.spf) }}</text>
          </view>

          <view class="row-detail" @tap="openSimilar(it)">
            <text>同赔详情 {{ it.f6?.matches?.length || 0 }} 场 ›</text>
          </view>
        </view>
      </view>
    </scroll-view>

    <SimBetLineSheet
      :visible="showSimSheet"
      :home-team="simTarget?.homeTeam?.name || ''"
      :away-team="simTarget?.awayTeam?.name || ''"
      :main-hc="simTarget?.ahHandicap"
      :matches="simTarget?.f6?.matches || []"
      :f6-direction="simTarget?.f6?.direction || 'neutral'"
      :ref-score="simTarget?.f6?.refScore"
      :low-key="lowKeyFromSpf(simTarget?.spf)"
      :selected-side="simBet.findLeg(simTarget?.matchId)?.side"
      :selected-line="simBet.findLeg(simTarget?.matchId)?.line"
      @close="closeSimPick"
      @pick="onSimPick"
    />
    <SimBetSlip />

    <view class="similar-mask" v-if="showSimilar" @tap="closeSimilar"></view>
    <view class="similar-modal" :class="{ show: showSimilar }">
      <view class="similar-header">
        <view class="similar-title-wrap">
          <text class="similar-title">历史同赔详情</text>
          <text v-if="similarRefScore != null" class="similar-ref">参考分 {{ similarRefScore }}</text>
          <text
            v-if="similarIsJapan"
            class="jp-toggle"
            :class="{ on: similarJapanOnly, loading: similarJapanLoading }"
            @tap.stop="toggleJapanOnly"
          >仅日本</text>
        </view>
        <text class="similar-close" @tap="closeSimilar">关闭</text>
      </view>
      <view v-if="similarJapanOnly" class="jp-hint">
        <text>仅日职/日乙/杯赛 · 低赔±0.05 · 高赔±0.15</text>
      </view>
      <view v-if="similarStats.total > 0" class="similar-stats">
        <view class="stats-row">
          <text class="stats-label">胜平负</text>
          <text class="stats-item r-win">主胜 {{ similarStats.win }}({{ similarStats.winPct }}%)</text>
          <text class="stats-item r-draw">平 {{ similarStats.draw }}({{ similarStats.drawPct }}%)</text>
          <text class="stats-item r-loss">客胜 {{ similarStats.loss }}({{ similarStats.lossPct }}%)</text>
          <text class="stats-n">{{ similarStats.total }}场</text>
        </view>
        <view class="stats-row">
          <text class="stats-label">盘路</text>
          <template v-if="similarStats.ahTotal > 0">
            <text class="stats-item ah-upper">上盘 {{ similarStats.upper }}({{ similarStats.upperPct }}%){{ similarStats.halfUp ? ` 含半${similarStats.halfUp}` : '' }}</text>
            <text class="stats-item ah-push">走水 {{ similarStats.push }}({{ similarStats.pushPct }}%)</text>
            <text class="stats-item ah-lower">下盘 {{ similarStats.lower }}({{ similarStats.lowerPct }}%){{ similarStats.halfDown ? ` 含半${similarStats.halfDown}` : '' }}</text>
            <text class="stats-n">{{ similarStats.ahTotal }}场</text>
          </template>
          <text v-else class="stats-empty">无亚盘数据</text>
        </view>
      </view>
      <scroll-view class="similar-body" scroll-y scroll-x>
        <view class="similar-table">
          <view class="similar-row similar-thead">
            <text class="col-sim">相似度</text>
            <text class="col-team">主队</text>
            <text class="col-score">比分</text>
            <text class="col-team">客队</text>
            <text class="col-result">结果</text>
            <text class="col-ah-result">盘路</text>
            <text class="col-ah">亚初</text>
            <text class="col-ah">亚终</text>
            <text class="col-odds">初盘</text>
            <text class="col-odds">终盘</text>
            <text class="col-date">日期</text>
            <text class="col-league">联赛</text>
          </view>
          <view
            class="similar-row"
            :class="{ 'is-single': m.isSingle }"
            v-for="(m, mi) in similarMatches"
            :key="mi"
          >
            <view class="col-sim">
              <text class="sim-num">{{ m.similarity }}%</text>
              <text class="single-mark" :class="{ on: m.isSingle }">{{ m.isSingle ? '单' : '' }}</text>
            </view>
            <text class="col-team">{{ m.homeTeam }}</text>
            <text class="col-score">{{ m.score }}</text>
            <text class="col-team">{{ m.awayTeam }}</text>
            <text class="col-result" :class="resultClass(m.result)">{{ m.result }}</text>
            <text class="col-ah-result" :class="ahResultClass(m.ahResult)">{{ m.ahResult || '-' }}</text>
            <text class="col-ah">{{ m.handicapOpen || '-' }}</text>
            <text class="col-ah">{{ m.handicapClose || m.handicap || '-' }}</text>
            <text class="col-odds">{{ m.openOdds }}</text>
            <text class="col-odds">{{ m.closeOdds }}</text>
            <text class="col-date">{{ m.date }}</text>
            <text class="col-league" :class="{ 'league-same': m.sameLeague }">{{ m.league }}</text>
          </view>
          <view v-if="similarMatches.length === 0" class="similar-empty">
            <text>暂无历史同赔数据</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <!-- 日本情报弹层（辅助参考） -->
    <view class="similar-mask" v-if="showJapanIntel" @tap="closeJapanIntel"></view>
    <view class="japan-modal" :class="{ show: showJapanIntel }">
      <view class="similar-header">
        <view class="similar-title-wrap">
          <text class="similar-title">日本情报</text>
          <text class="similar-ref">辅助参考</text>
        </view>
        <text class="similar-close" @tap="closeJapanIntel">关闭</text>
      </view>
      <scroll-view class="japan-body" scroll-y>
        <view v-if="japanIntelLoading" class="japan-loading"><text>加载中…</text></view>
        <JapanIntelCard v-else-if="japanIntelData" :data="japanIntelData" />
        <view v-else class="japan-loading"><text>暂无数据</text></view>
      </scroll-view>
    </view>

    <!-- 日期选择 -->
    <view class="cal-mask" v-if="showCalendar" @tap="showCalendar = false"></view>
    <view class="cal-panel" :class="{ visible: showCalendar }">
      <view class="cal-header">
        <text class="cal-cancel" @tap="showCalendar = false">取消</text>
        <text class="cal-title">选择日期</text>
        <text class="cal-confirm" @tap="confirmCalendar">确定</text>
      </view>
      <view class="cal-body">
        <view class="cal-nav">
          <text class="cal-arrow" @tap="calPrevMonth">&lt;</text>
          <text class="cal-month">{{ calYear }}年{{ calMonth }}月</text>
          <text class="cal-arrow" @tap="calNextMonth">&gt;</text>
        </view>
        <view class="cal-weekdays">
          <text class="cal-wd" v-for="w in ['日','一','二','三','四','五','六']" :key="w">{{ w }}</text>
        </view>
        <view class="cal-days">
          <text
            v-for="(d, i) in calDays"
            :key="i"
            class="cal-day"
            :class="{
              'cal-other': d.other,
              'cal-today': d.isToday,
              'cal-selected': d.dateStr === calSelected,
              'cal-has': !d.other && saleDateSet.has(d.dateStr),
            }"
            @tap="!d.other && (calSelected = d.dateStr)"
          >{{ d.day }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { request } from '@/utils/http'
import { useSimBetStore } from '@/stores/simBetStore'
import { lowKeyFromSpf } from '@/utils/simBet'
import { calcSimilarStats } from '@/utils/similarStats'
import { isJapanLeague } from '@/utils/japanLeague'
import SimBetLineSheet from '@/components/SimBetLineSheet.vue'
import SimBetSlip from '@/components/SimBetSlip.vue'
import JapanIntelCard from '@/components/JapanIntelCard.vue'

const simBet = useSimBetStore()
const date = ref('')
const status = ref('not_started')
const loading = ref(true)
const items = ref([])
const summary = ref({ total: 0, upper: 0, lower: 0, neutral: 0 })
const saleDates = ref([])
/** 翻页用: 在售∪已结束售卖日, 避免「在售」稀疏日期导致跨大半个月 */
const navDates = ref([])
const showCalendar = ref(false)
const calYear = ref(2026)
const calMonth = ref(6)
const calSelected = ref('')
const showSimilar = ref(false)
const similarMatches = ref([])
const similarRefScore = ref(null)
const similarDefaultMatches = ref([])
const similarDefaultRef = ref(null)
const similarMatchId = ref('')
const similarIsJapan = ref(false)
const similarJapanOnly = ref(false)
const similarJapanLoading = ref(false)
const similarStats = computed(() => calcSimilarStats(similarMatches.value))
const showJapanIntel = ref(false)
const japanIntelData = ref(null)
const japanIntelLoading = ref(false)
const japanIntelCache = ref({})
const showSimSheet = ref(false)
const simTarget = ref(null)
/** 多选: upper/lower/neutral/hit */
const dirFilters = ref([])
/** 多选: up/down/flat — 低赔方(让球方)初→终 */
const moveFilters = ref([])
/** default | time | hitPct | refScore */
const sortMode = ref('default')

const isFinished = computed(() => status.value === 'finished')
const hasFilter = computed(() => dirFilters.value.length > 0 || moveFilters.value.length > 0)
const dateLabel = computed(() => (date.value || '').slice(5) || '--')
/** 日历打点用全量售卖日, 方便从在售点进已结束期 */
const saleDateSet = computed(() => new Set(navDates.value.length ? navDates.value : saleDates.value))

/** 按日历早晚翻期; 用 navDates(双状态并集) */
const sortedNavDates = computed(() => [...navDates.value].sort())
const dateIndex = computed(() => sortedNavDates.value.indexOf(date.value))
const prevSaleDate = computed(() => {
  const i = dateIndex.value
  return i > 0 ? sortedNavDates.value[i - 1] : null
})
const nextSaleDate = computed(() => {
  const i = dateIndex.value
  const list = sortedNavDates.value
  return i >= 0 && i < list.length - 1 ? list[i + 1] : null
})

const calDays = computed(() => {
  const y = calYear.value
  const m = calMonth.value
  const firstDay = new Date(y, m - 1, 1).getDay()
  const daysInMonth = new Date(y, m, 0).getDate()
  const daysInPrev = new Date(y, m - 1, 0).getDate()
  const today = new Date().toISOString().slice(0, 10)
  const cells = []
  for (let i = firstDay - 1; i >= 0; i--) {
    const day = daysInPrev - i
    const pm = m - 1 < 1 ? 12 : m - 1
    const py = m - 1 < 1 ? y - 1 : y
    cells.push({
      day,
      other: true,
      dateStr: `${py}-${String(pm).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
      isToday: false,
    })
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ day: d, other: false, dateStr, isToday: dateStr === today })
  }
  const remaining = 42 - cells.length
  for (let d = 1; d <= remaining; d++) {
    const nm = m + 1 > 12 ? 1 : m + 1
    const ny = m + 1 > 12 ? y + 1 : y
    cells.push({
      day: d,
      other: true,
      dateStr: `${ny}-${String(nm).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
      isToday: false,
    })
  }
  return cells
})

function calPrevMonth() {
  if (calMonth.value === 1) {
    calMonth.value = 12
    calYear.value--
  } else calMonth.value--
}
function calNextMonth() {
  if (calMonth.value === 12) {
    calMonth.value = 1
    calYear.value++
  } else calMonth.value++
}

function openCalendar() {
  const base = date.value || saleDates.value[0] || new Date().toISOString().slice(0, 10)
  const [y, m] = base.split('-').map(Number)
  calYear.value = y
  calMonth.value = m
  calSelected.value = base
  showCalendar.value = true
}

function confirmCalendar() {
  if (calSelected.value) switchDate(calSelected.value)
  showCalendar.value = false
}

function goPrevDate() {
  if (prevSaleDate.value) switchDate(prevSaleDate.value)
}
function goNextDate() {
  if (nextSaleDate.value) switchDate(nextSaleDate.value)
}

async function switchDate(next) {
  if (!next || next === date.value) return
  date.value = next
  if (!saleDates.value.includes(next)) {
    saleDates.value = [next, ...saleDates.value]
  }
  if (!navDates.value.includes(next)) {
    navDates.value = [...navDates.value, next].sort()
  }
  if (simBet.hasLegs) simBet.clearLegs()
  await loadBatch({ autoFlipStatus: true })
}

async function switchStatus(next) {
  if (!next || next === status.value) return
  status.value = next
  if (simBet.hasLegs) simBet.clearLegs()
  await loadSaleDates()
  // 当前日期若不在新状态的日期列表里, 落到最近一期
  if (saleDates.value.length && !saleDates.value.includes(date.value)) {
    date.value = status.value === 'finished'
      ? saleDates.value[0]
      : (saleDates.value[saleDates.value.length - 1] || saleDates.value[0])
  }
  await loadBatch()
}

async function loadSaleDates() {
  const otherStatus = status.value === 'not_started' ? 'finished' : 'not_started'
  try {
    const [cur, other] = await Promise.all([
      request({ url: '/api/predict/dates', data: { status: status.value } }),
      request({ url: '/api/predict/dates', data: { status: otherStatus } }),
    ])
    saleDates.value = cur?.dates || []
    if (date.value && !saleDates.value.includes(date.value)) {
      saleDates.value = [date.value, ...saleDates.value]
    }
    const merged = new Set([...(cur?.dates || []), ...(other?.dates || [])])
    if (date.value) merged.add(date.value)
    navDates.value = [...merged].sort()
  } catch {
    saleDates.value = date.value ? [date.value] : []
    navDates.value = [...saleDates.value]
  }
}

async function fetchBatch(forStatus) {
  return request({
    url: '/api/predict/batch-similar',
    data: { date: date.value, status: forStatus },
  })
}

function simPickLabel(it) {
  const leg = simBet.findLeg(it.matchId)
  if (leg) return `${leg.pickLabel} · ${leg.safetyScore}`
  if (it.ahHandicap == null) return '无亚盘'
  return '选盘'
}
function openSimPick(it) {
  if (it.ahHandicap == null) {
    uni.showToast({ title: '该场无亚盘数据', icon: 'none' })
    return
  }
  simTarget.value = it
  showSimSheet.value = true
}
function closeSimPick() {
  showSimSheet.value = false
  simTarget.value = null
}
function onSimPick(cell) {
  const it = simTarget.value
  if (!it) return
  simBet.setLeg({
    matchId: it.matchId,
    homeTeam: it.homeTeam?.name || '',
    awayTeam: it.awayTeam?.name || '',
    league: it.league || '',
    matchTime: it.matchTime || '',
    mainHc: it.ahHandicap,
    side: cell.side,
    line: cell.line,
    safetyScore: cell.safetyScore,
    scoreSource: cell.scoreSource,
    sample: cell.sample,
    notLoseRate: cell.notLoseRate,
    expUnit: cell.expUnit,
    f6Direction: it.f6?.direction || 'neutral',
    date: date.value,
  })
  closeSimPick()
}
function applySimSettlement() {
  const map = {}
  for (const it of items.value) {
    const score = it.actualScore
    if (!score || typeof score !== 'string' || !score.includes('-')) continue
    const [hs, aws] = score.split('-').map(Number)
    if (Number.isNaN(hs) || Number.isNaN(aws)) continue
    map[it.matchId] = { homeScore: hs, awayScore: aws }
  }
  if (Object.keys(map).length) simBet.settleWithScores(map)
}

const dateConfirmed = computed(() =>
  simBet.confirmed.filter((s) => !s.date || s.date === date.value)
)
function slipResultLabel(s) {
  if (s.status !== 'settled') return '待结算'
  return ({ win: '赢', lose: '输', half: '半', push: '走水' })[s.result] || s.result || '-'
}
function slipLegSettleBrief(s) {
  if (!s?.legs?.length) return ''
  const parts = s.legs
    .filter((l) => l.settle?.label)
    .map((l) => l.settle.label)
  if (!parts.length) return ''
  return ` (${parts.join('/')})`
}
function slipStakeBrief(s) {
  if (s?.suggestedStake == null) return ''
  return ` · 建议¥${s.suggestedStake}`
}

const DIR_ORDER = { upper: 0, lower: 1, neutral: 2 }
function itemHitPct(it) {
  return focusPct(it?.f6) || 0
}
function itemRefScore(it) {
  const s = it?.f6?.refScore
  return s == null ? -1 : Number(s)
}
function itemTimeValue(it) {
  const rawTime = String(it?.matchTime || '')
  const fullInTime = rawTime.match(/(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/)
  if (fullInTime) {
    const [, y, mo, d, h, mi, s = '0'] = fullInTime
    return new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s)).getTime()
  }

  const rawDate = String(it?.matchDate || '')
  const dateMatch = rawDate.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/)
  const timeMatch = rawTime.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/)
  if (!dateMatch || !timeMatch) return Number.MAX_SAFE_INTEGER

  const [, y, mo, d] = dateMatch
  const [, h, mi, s = '0'] = timeMatch
  const value = new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s)).getTime()
  return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value
}
const sortedItems = computed(() => {
  const list = [...items.value]
  const mode = sortMode.value
  if (mode === 'time') {
    return list.sort((a, b) => {
      const d = itemTimeValue(a) - itemTimeValue(b)
      if (d !== 0) return d
      return itemRefScore(b) - itemRefScore(a)
    })
  }
  if (mode === 'hitPct') {
    return list.sort((a, b) => {
      const d = itemHitPct(b) - itemHitPct(a)
      if (d !== 0) return d
      return itemRefScore(b) - itemRefScore(a)
    })
  }
  if (mode === 'refScore') {
    return list.sort((a, b) => {
      const d = itemRefScore(b) - itemRefScore(a)
      if (d !== 0) return d
      return itemHitPct(b) - itemHitPct(a)
    })
  }
  return list.sort((a, b) => {
    const da = DIR_ORDER[a.f6?.direction] ?? 2
    const db = DIR_ORDER[b.f6?.direction] ?? 2
    if (da !== db) return da - db
    return itemRefScore(b) - itemRefScore(a)
  })
})
const filteredItems = computed(() => {
  let list = sortedItems.value
  const dirs = dirFilters.value
  if (dirs.length) {
    const dirSet = dirs.filter(k => k !== 'hit' && k !== 'sample8' && k !== 'hitPct65' && k !== 'score60' && k !== 'single')
    const needHit = dirs.includes('hit')
    const needSample8 = dirs.includes('sample8')
    const needHitPct65 = dirs.includes('hitPct65')
    const needScore60 = dirs.includes('score60')
    const needSingle = dirs.includes('single')
    list = list.filter(it => {
      const okDir = !dirSet.length || dirSet.includes(it.f6?.direction || 'neutral')
      const okHit = !needHit || it.hit === true
      const okSample = !needSample8 || similarHistCount(it) >= 8
      const okHitPct = !needHitPct65 || itemHitPct(it) >= 65
      const okScore = !needScore60 || itemRefScore(it) >= 60
      const okSingle = !needSingle || !!it.isSingle
      return okDir && okHit && okSample && okHitPct && okScore && okSingle
    })
  }
  const moves = moveFilters.value
  if (moves.length) {
    list = list.filter(it => moves.includes(lowMoveDir(it.spf)))
  }
  return list
})
const filteredHitCount = computed(() =>
  filteredItems.value.reduce((n, it) => n + (it.hit === true ? 1 : 0), 0)
)

/** 同赔历史匹配场次(详情列表条数) */
function similarHistCount(it) {
  const n = it?.f6?.matches?.length
  return n == null ? 0 : Number(n)
}

function toggleInList(listRef, key) {
  const arr = listRef.value
  const i = arr.indexOf(key)
  if (i >= 0) listRef.value = arr.filter((_, idx) => idx !== i)
  else listRef.value = [...arr, key]
}
function toggleFilter(key) {
  toggleInList(dirFilters, key)
}
function toggleMoveFilter(key) {
  toggleInList(moveFilters, key)
}
function clearFilter() {
  dirFilters.value = []
  moveFilters.value = []
}

function dirLabel(dir) { return dir === 'upper' ? '上盘' : dir === 'lower' ? '下盘' : '中性' }
/** 参考分档: weak <40 / mid 40–64 / strong ≥65 */
function refTier(f6) {
  const s = f6?.refScore
  if (s == null) return ''
  if (s < 40) return 'ref-weak'
  if (s < 65) return 'ref-mid'
  return 'ref-strong'
}
function fmt(v) { return v == null ? '-' : Number(v).toFixed(2) }
/** 亚盘展示: 标准约定负=主让, 保留常见四分盘精度 */
function fmtAh(h) {
  if (h == null || h === '') return '-'
  const n = Number(h)
  if (Number.isNaN(n)) return '-'
  if (Object.is(n, -0) || n === 0) return '0'
  const s = Math.abs(n) % 1 === 0 ? String(Math.abs(n)) : Math.abs(n).toFixed(2).replace(/0$/, '')
  return (n > 0 ? '+' : '-') + s
}
function ahOpenOf(it) {
  // 缺初盘时不要用终盘顶替, 否则永远显示「初=终」
  if (it?.ahHandicapOpen != null) return it.ahHandicapOpen
  return null
}
function ahCloseOf(it) {
  if (it?.ahHandicapClose != null) return it.ahHandicapClose
  return it?.ahHandicap
}
function hasAh(it) {
  return ahCloseOf(it) != null || ahOpenOf(it) != null
}
/** 亚盘初→终: 升盘(绝对值变深)/降盘/不变 */
function ahMoveDir(it) {
  const o = it?.ahHandicapOpen
  const c = ahCloseOf(it)
  if (o == null || c == null) return null
  const a = Number(o), b = Number(c)
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  if (Math.abs(a - b) < 1e-9) return 'flat'
  if (Math.abs(b) > Math.abs(a) + 1e-9) return 'up'
  if (Math.abs(b) < Math.abs(a) - 1e-9) return 'down'
  return 'up'
}
function ahMoveLabel(it) {
  const d = ahMoveDir(it)
  if (d === 'up') return '升盘'
  if (d === 'down') return '降盘'
  if (d === 'flat') return '不变'
  return ''
}
function ahMoveClass(it) {
  const d = ahMoveDir(it)
  return d ? `ah-mv-${d}` : ''
}
function isLow(odds) {
  if (!odds) return ''
  const w = Number(odds.win), d = Number(odds.draw), l = Number(odds.lose)
  const m = Math.min(w, d, l)
  if (m === w) return 'win'
  if (m === l) return 'loss'
  return 'draw'
}
function lowClass(odds, key) {
  return isLow(odds) === key ? `low-${key}` : 'ol-n'
}
/** 低赔方(=让球方/强方)初→终: up上升 / down下降 / flat不变 */
function lowMoveDir(spf) {
  if (!spf?.initial || !spf?.current) return null
  const key = isLow(spf.initial)
  if (!key) return null
  const field = key === 'loss' ? 'lose' : key
  const o = Number(spf.initial[field])
  const c = Number(spf.current[field])
  if (Number.isNaN(o) || Number.isNaN(c)) return null
  // 与 scraper 变动阈值对齐: ≤0.005 视为不变
  if (c < o - 0.005) return 'down'
  if (c > o + 0.005) return 'up'
  return 'flat'
}
function moveLabel(spf) {
  const d = lowMoveDir(spf)
  if (d === 'up') return '上升'
  if (d === 'down') return '下降'
  if (d === 'flat') return '不变'
  return '-'
}
function moveClass(spf) {
  const d = lowMoveDir(spf)
  return d ? `mv-${d}` : ''
}
function parseHit(desc) {
  if (!desc) return null
  const m = String(desc).match(/(\d+(?:\.\d+)?)%\s*\((\d+)\/(\d+)\)/)
  if (!m) return null
  return { pct: Number(m[1]), n: Number(m[2]), total: Number(m[3]) }
}
function getDetail(f6, name) {
  const d = (f6?.details || []).find(x => x.name === name)
  return d ? d.desc : ''
}
function ahStats(f6) {
  const up = parseHit(getDetail(f6, '上盘命中'))
  const lo = parseHit(getDetail(f6, '下盘命中'))
  const pushDesc = getDetail(f6, '走水')
  const pushM = pushDesc ? String(pushDesc).match(/^(\d+)/) : null
  const total = up?.total || lo?.total || 0
  const upper = up?.n || 0
  const lower = lo?.n || 0
  const push = pushM ? Number(pushM[1]) : 0
  const upperPct = total ? Math.round((upper / total) * 100) : 0
  const lowerPct = total ? Math.round((lower / total) * 100) : 0
  return { total, upper, lower, push, upperPct, lowerPct }
}
function focusSide(f6) {
  const dir = f6?.direction
  if (dir === 'upper' || dir === 'lower') return dir
  const s = ahStats(f6)
  // 比场次更稳: 百分比四舍五入后也可能相等(如 10/10/4 → 42/42)
  if (s.lower > s.upper) return 'lower'
  if (s.upper > s.lower) return 'upper'
  if (s.lowerPct > s.upperPct) return 'lower'
  if (s.upperPct > s.lowerPct) return 'upper'
  return 'neutral' // 上=下, 无领先侧
}
function focusPct(f6) {
  const s = ahStats(f6)
  const side = focusSide(f6)
  if (side === 'upper') return s.upperPct
  if (side === 'lower') return s.lowerPct
  return Math.max(s.upperPct, s.lowerPct)
}
function focusHitLabel(f6) {
  const side = focusSide(f6)
  if (side === 'upper') return '上盘命中'
  if (side === 'lower') return '下盘命中'
  return '两侧持平'
}
function shortReason(reason) {
  if (!reason) return ''
  let s = reason.replace(/^历史同赔\d+场盘路/, '')
  s = s.replace(/^[上下]盘命中\d+(?:\.\d+)?%\(\d+\/\d+\)[,，]\s*/, '')
  return s.trim() || reason
}
function resultClass(r) {
  if (r === '主胜') return 'r-win'
  if (r === '平局') return 'r-draw'
  if (r === '客胜') return 'r-loss'
  return ''
}
function ahResultClass(ah) {
  if (ah === '上盘' || ah === '半上') return 'ah-upper'
  if (ah === '下盘' || ah === '半下') return 'ah-lower'
  if (ah === '走水') return 'ah-push'
  return ''
}
function openSimilar(it) {
  similarDefaultMatches.value = it?.f6?.matches || []
  similarDefaultRef.value = it?.f6?.refScore != null ? it.f6.refScore : null
  similarMatches.value = similarDefaultMatches.value
  similarRefScore.value = similarDefaultRef.value
  similarMatchId.value = it?.matchId || ''
  similarIsJapan.value = isJapanLeague(it?.league)
  similarJapanOnly.value = false
  similarJapanLoading.value = false
  showSimilar.value = true
}
function closeSimilar() {
  showSimilar.value = false
  similarRefScore.value = null
  similarJapanOnly.value = false
  similarJapanLoading.value = false
  similarMatchId.value = ''
  similarIsJapan.value = false
}
async function toggleJapanOnly() {
  if (!similarIsJapan.value || similarJapanLoading.value) return
  if (similarJapanOnly.value) {
    // 关: 恢复默认全联赛匹配
    similarJapanOnly.value = false
    similarMatches.value = similarDefaultMatches.value
    similarRefScore.value = similarDefaultRef.value
    return
  }
  if (!similarMatchId.value) {
    uni.showToast({ title: '比赛ID缺失', icon: 'none' })
    return
  }
  similarJapanLoading.value = true
  try {
    const data = await request({
      url: `/api/predict/${encodeURIComponent(similarMatchId.value)}/similar-odds`,
      method: 'GET',
      data: { japan_only: true },
    })
    similarJapanOnly.value = true
    similarMatches.value = data?.matches || []
    similarRefScore.value = data?.refScore != null ? data.refScore : null
  } catch (e) {
    uni.showToast({ title: e?.message || '仅日本匹配失败', icon: 'none' })
  } finally {
    similarJapanLoading.value = false
  }
}

function japanSummary(it) {
  const cached = japanIntelCache.value[it.matchId]
  if (!cached) return '阵容 / 天气 / 进攻点'
  if ((cached.lineups || []).length) {
    const n = cached.attackNotes?.length || 0
    return n ? `已出首发 · 进攻点${n}` : '已出首发'
  }
  if (cached.weather) return '天气已出 · 阵容待公布'
  return cached.note || '点击查看'
}

async function openJapanIntel(it) {
  const mid = it?.matchId
  if (!mid) return
  showJapanIntel.value = true
  if (japanIntelCache.value[mid]) {
    japanIntelData.value = japanIntelCache.value[mid]
    return
  }
  japanIntelLoading.value = true
  japanIntelData.value = null
  try {
    const data = await request({
      url: `/api/predict/${encodeURIComponent(mid)}/japan-context`,
      method: 'GET',
    })
    japanIntelCache.value = { ...japanIntelCache.value, [mid]: data }
    japanIntelData.value = data
  } catch (e) {
    japanIntelData.value = {
      isJapanLeague: true,
      note: e?.message || '加载失败',
      lineups: [],
      weather: null,
      attackNotes: [],
    }
  } finally {
    japanIntelLoading.value = false
  }
}

function closeJapanIntel() {
  showJapanIntel.value = false
}

function goPredict(it) {
  if (!it?.matchId) {
    uni.showToast({ title: '比赛ID缺失', icon: 'none' })
    return
  }
  const isWorldCup = it.league && it.league.includes('世界杯')
  const qs = [`matchId=${encodeURIComponent(it.matchId)}`, 'auto=1']
  if (date.value) qs.push(`date=${encodeURIComponent(date.value)}`)
  const url = isWorldCup
    ? `/pages/worldcup/predict?${qs.join('&')}`
    : `/pages/predict/predict?${qs.join('&')}`
  uni.navigateTo({ url })
}

async function loadBatch(opts = {}) {
  const autoFlipStatus = !!opts.autoFlipStatus
  loading.value = true
  dirFilters.value = []
  moveFilters.value = []
  sortMode.value = 'default'
  try {
    let data = await fetchBatch(status.value)
    let list = data?.items || []
    // 换日时空列表: 在售↔已结束自动对侧补救(常见:翻到已完赛日仍停在「在售」)
    if (autoFlipStatus && list.length === 0) {
      const other = status.value === 'not_started' ? 'finished' : 'not_started'
      const otherData = await fetchBatch(other)
      const otherList = otherData?.items || []
      if (otherList.length > 0) {
        status.value = other
        data = otherData
        list = otherList
        await loadSaleDates()
        uni.showToast({
          title: other === 'finished' ? '已切到已结束' : '已切到在售',
          icon: 'none',
        })
      }
    }
    items.value = list
    summary.value = data?.summary || { total: 0, upper: 0, lower: 0, neutral: 0 }
    if (status.value === 'finished') applySimSettlement()
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onLoad(async (options) => {
  const today = new Date().toISOString().slice(0, 10)
  date.value = options?.date || today
  status.value = options?.status || 'not_started'
  await loadSaleDates()
  loadBatch()
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.batch-page {
  min-height: 100vh;
  width: 100%;
  max-width: 100vw;
  overflow-x: hidden;
  background: #f7faf9;
  display: flex;
  flex-direction: column;

  &, view, text, scroll-view {
    box-sizing: border-box;
    max-width: 100%;
  }
}

/* 顶栏: 纯色 + 文字统计,无 chip 块 */
.summary-bar {
  background: $frbt-primary;
  padding: 22rpx 28rpx 20rpx;
  .sum-row {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 10rpx; gap: 12rpx;
  }
  .date-nav {
    display: flex; align-items: center; gap: 4rpx; min-width: 0;
  }
  .date-arr {
    font-size: 36rpx; color: rgba(255,255,255,0.9);
    padding: 4rpx 10rpx; line-height: 1;
    &.disabled { opacity: 0.28; pointer-events: none; }
  }
  .sum-title {
    font-size: 28rpx; font-weight: 600; color: #fff;
    &.date-tap {
      padding: 4rpx 8rpx;
      border-bottom: 1rpx dashed rgba(255,255,255,0.45);
    }
  }
  .sum-right { display: flex; align-items: center; gap: 16rpx; flex-shrink: 0; }
  .status-row {
    display: flex; gap: 12rpx; margin-bottom: 10rpx;
  }
  .status-tab {
    font-size: 22rpx; color: rgba(255,255,255,0.75);
    padding: 4rpx 16rpx; border-radius: 6rpx;
    border: 1rpx solid rgba(255,255,255,0.28);
    &.on {
      color: #0f172a; background: #fff; border-color: #fff; font-weight: 600;
    }
  }
  .sim-toggle {
    font-size: 22rpx; color: rgba(255,255,255,0.85);
    padding: 6rpx 14rpx; border-radius: 6rpx;
    border: 1rpx solid rgba(255,255,255,0.35);
    &.on {
      color: #0f172a; background: #fff; border-color: #fff; font-weight: 600;
    }
  }
  .sum-total { font-size: 22rpx; color: rgba(255,255,255,0.7); }
  .sum-stats {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8rpx;
    .st {
      font-size: 22rpx; color: rgba(255,255,255,0.85);
      &.upper { color: #fecaca; font-weight: 600; }
      &.lower { color: #a7f3d0; font-weight: 600; }
      &.neutral { color: rgba(255,255,255,0.85); font-weight: 500; }
      &.hit { color: #fde68a; font-weight: 600; }
      &.single-stat { color: #fdba74; font-weight: 600; }
    }
    .st-sep { font-size: 22rpx; color: rgba(255,255,255,0.35); }
    &.single-split { margin-top: 6rpx; opacity: 0.95; }
  }
  .sum-sim-hist {
    margin-top: 12rpx; display: flex; flex-wrap: wrap; gap: 8rpx;
    .sim-hist-item {
      font-size: 20rpx; color: rgba(255,255,255,0.8);
      padding: 4rpx 10rpx; border-radius: 6rpx;
      background: rgba(0,0,0,0.15);
      &.settled { color: #fde68a; }
    }
  }
}

.ctrl-bar {
  background: #fff;
  border-bottom: 1rpx solid #eef2f5;
  padding: 12rpx 28rpx 14rpx;
  .ctrl-row {
    display: flex; align-items: center; flex-wrap: wrap; gap: 12rpx;
    & + .ctrl-row { margin-top: 10rpx; }
  }
  .ctrl-lab { font-size: 22rpx; color: #94a3b8; margin-right: 4rpx; flex-shrink: 0; }
  .ctrl-btn {
    font-size: 22rpx; color: #64748b;
    padding: 6rpx 16rpx; border-radius: 6rpx;
    border: 1rpx solid #e2e8f0; background: #f8fafc;
    &.active {
      color: $frbt-primary; border-color: rgba($frbt-primary, 0.45);
      background: rgba($frbt-primary, 0.08); font-weight: 600;
    }
    &.upper.active { color: #dc2626; border-color: rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06); }
    &.lower.active { color: #059669; border-color: rgba(#059669, 0.4); background: rgba(#059669, 0.06); }
    &.hit.active { color: #d97706; border-color: rgba(#d97706, 0.4); background: rgba(#d97706, 0.08); }
    &.sample.active { color: #0369a1; border-color: rgba(#0369a1, 0.4); background: rgba(#0369a1, 0.06); }
    &.hitpct.active { color: #7c3aed; border-color: rgba(#7c3aed, 0.4); background: rgba(#7c3aed, 0.06); }
    &.score.active { color: #0f766e; border-color: rgba(#0f766e, 0.4); background: rgba(#0f766e, 0.06); }
    &.single.active { color: #dc2626; border-color: rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06); }
    &.move-up.active { color: #dc2626; border-color: rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06); }
    &.move-down.active { color: #059669; border-color: rgba(#059669, 0.4); background: rgba(#059669, 0.06); }
    &:active { opacity: 0.7; }
  }
  .filter-count {
    display: flex; align-items: baseline; gap: 12rpx;
    margin-top: 12rpx; padding-top: 10rpx;
    border-top: 1rpx solid #f1f5f9;
    .fc-main { font-size: 24rpx; font-weight: 600; color: #0f172a; }
    .fc-sub { font-size: 22rpx; color: #94a3b8; }
    .fc-hit { font-size: 22rpx; font-weight: 600; color: #d97706; }
    .fc-clear {
      margin-left: auto; font-size: 22rpx; color: $frbt-primary; padding: 4rpx 0;
      &:active { opacity: 0.6; }
    }
  }
}

.state-hint {
  padding: 120rpx 0; display: flex; flex-direction: column; align-items: center; gap: 16rpx;
  text { font-size: 26rpx; color: #94a3b8; }
  .state-clear { font-size: 24rpx; color: $frbt-primary; padding: 8rpx 16rpx; }
}

.card-list { flex: 1; width: 100%; height: 0; }
.card-list-inner { padding: 16rpx 24rpx 80rpx; width: 100%; }
.batch-page.sim-pad .card-list-inner { padding-bottom: 180rpx; }

/* 卡片: 白底 + 细分隔,无阴影/左边条/内嵌色盒 */
.match-card {
  background: #fff;
  border-radius: 10rpx;
  padding: 22rpx 24rpx 16rpx;
  margin-bottom: 14rpx;
  border: 1rpx solid #e8eef0;
  width: 100%;
}

.row-sim {
  margin: -6rpx 0 12rpx;
  .sim-pick {
    display: inline-block;
    font-size: 22rpx; color: #0d9488; font-weight: 600;
    padding: 6rpx 16rpx; border-radius: 6rpx;
    border: 1rpx solid rgba(#0d9488, 0.45); background: rgba(#0d9488, 0.06);
    &.active { background: #0d9488; color: #fff; border-color: #0d9488; }
    &.disabled { color: #94a3b8; border-color: #e2e8f0; background: #f8fafc; font-weight: 500; }
  }
}

.row-meta {
  display: flex; align-items: center; gap: 12rpx; margin-bottom: 14rpx;
  .league { font-size: 22rpx; color: #64748b; font-weight: 500; }
  .time { font-size: 22rpx; color: #94a3b8; }
  .single-tag {
    font-size: 20rpx; color: #dc2626; font-weight: 600;
    padding: 2rpx 8rpx; border-radius: 6rpx;
    border: 1rpx solid rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06);
    flex-shrink: 0;
  }
  .dir-wrap {
    margin-left: auto; display: flex; align-items: baseline; gap: 8rpx; flex-shrink: 0;
  }
  .predict-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48rpx;
    height: 48rpx;
    border-radius: 6rpx;
    background: linear-gradient(135deg, #0d9488, #14b8a6);
    flex-shrink: 0;
    box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);
    &:active { opacity: 0.75; }
  }
  .predict-icon-text {
    font-size: 22rpx;
    line-height: 1;
    color: #fff;
    font-weight: 600;
  }
  .dir {
    font-size: 24rpx; font-weight: 600;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #94a3b8; }
    &.ref-weak { color: #94a3b8; font-weight: 500; }
    &.ref-strong { font-weight: 700; }
  }
  .ref-score {
    font-size: 24rpx; font-weight: 600; font-variant-numeric: tabular-nums;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #94a3b8; }
    &.ref-weak { color: #94a3b8; font-weight: 500; }
    &.ref-strong { font-weight: 700; }
  }
}

.row-teams {
  display: flex; align-items: center; justify-content: center;
  gap: 16rpx; margin-bottom: 18rpx; width: 100%;
  .team {
    flex: 1; min-width: 0; font-size: 28rpx; font-weight: 600; color: #1e293b;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    &.home { text-align: right; }
    &.away { text-align: left; }
  }
  .vs { font-size: 20rpx; color: #cbd5e1; flex-shrink: 0; }
}

.row-hit {
  margin-bottom: 14rpx;
  &.empty { padding: 4rpx 0; }
  .hit-top {
    display: flex; align-items: baseline; gap: 10rpx; margin-bottom: 10rpx;
  }
  .pct {
    font-size: 40rpx; font-weight: 700; line-height: 1;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #64748b; }
  }
  .pct-lab {
    font-size: 24rpx; font-weight: 500;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #64748b; }
  }
  .sample { margin-left: auto; font-size: 22rpx; color: #94a3b8; }
  .bar {
    display: flex; height: 6rpx; border-radius: 6rpx; overflow: hidden;
    background: #eef2f5; margin-bottom: 10rpx;
    .bar-u { background: #f87171; height: 100%; }
    .bar-l { background: #34d399; height: 100%; }
  }
  .reason { font-size: 24rpx; color: #64748b; line-height: 1.45; word-break: break-word; }
}

.row-ah {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx;
  margin-bottom: 12rpx; padding: 10rpx 0;
  border-top: 1rpx solid #f1f5f9;
  font-size: 24rpx; color: #334155;
  .ah-lab { font-size: 22rpx; color: #94a3b8; }
  .ah-muted { font-size: 22rpx; color: #94a3b8; }
  .ah-num { font-size: 26rpx; font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums; }
  .ah-miss { font-size: 22rpx; color: #94a3b8; }
  .ah-move {
    margin-left: 4rpx; font-size: 20rpx; font-weight: 600;
    &.ah-mv-up { color: #dc2626; }
    &.ah-mv-down { color: #059669; }
    &.ah-mv-flat { color: #94a3b8; font-weight: 500; }
  }
  .ac-score { font-weight: 700; color: #1e293b; }
  .ac-sep { color: #cbd5e1; }
  .ac-hit { margin-left: auto; color: #059669; font-weight: 600; font-size: 22rpx; }
  .ac-miss { margin-left: auto; color: #dc2626; font-weight: 600; font-size: 22rpx; }
}

.row-odds {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx;
  font-size: 22rpx; color: #64748b; margin-bottom: 4rpx;
  .ol-lab { font-size: 22rpx; color: #64748b; font-weight: 500; }
  .ol-muted { color: #94a3b8; }
  .ol-n { color: #64748b; }
  .low-win { color: #dc2626; font-weight: 600; }
  .low-draw { color: #d97706; font-weight: 600; }
  .low-loss { color: #059669; font-weight: 600; }
  .ol-move {
    margin-left: auto; font-size: 20rpx; font-weight: 600;
    &.mv-up { color: #dc2626; }
    &.mv-down { color: #059669; }
    &.mv-flat { color: #94a3b8; font-weight: 500; }
  }
}

.row-detail {
  padding: 10rpx 0 2rpx; text-align: right;
  text { font-size: 22rpx; color: $frbt-primary; }
  &:active { opacity: 0.6; }
}

/* 弹窗 */
.similar-mask {
  position: fixed; inset: 0; background: rgba(15,23,42,0.4); z-index: 200;
}
.similar-modal {
  position: fixed; top: 50%; left: 3vw; right: 3vw; bottom: auto;
  max-height: 88vh; height: auto;
  background: #fff; border-radius: 12rpx; z-index: 201;
  display: flex; flex-direction: column;
  transform: translateY(-50%) scale(0.96); opacity: 0;
  transition: transform 0.2s ease, opacity 0.2s ease;
  pointer-events: none;
  &.show { transform: translateY(-50%) scale(1); opacity: 1; pointer-events: auto; }
}
.similar-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20rpx 24rpx; border-bottom: 1rpx solid #e2e8f0; flex-shrink: 0;
  .similar-title-wrap { display: flex; align-items: center; gap: 12rpx; min-width: 0; flex-wrap: wrap; }
  .similar-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
  .similar-ref { font-size: 22rpx; color: #64748b; font-variant-numeric: tabular-nums; }
  .jp-toggle {
    font-size: 22rpx; color: #64748b; background: #f1f5f9;
    border: 1rpx solid #cbd5e1; border-radius: 6rpx;
    padding: 4rpx 12rpx; line-height: 1.4;
    &.on { color: #fff; background: #0f766e; border-color: #0f766e; }
    &.loading { opacity: 0.55; }
  }
  .similar-close { font-size: 24rpx; color: $frbt-primary; padding: 8rpx 4rpx; }
}
.jp-hint {
  flex-shrink: 0;
  padding: 8rpx 24rpx;
  background: #f0fdfa;
  border-bottom: 1rpx solid #ccfbf1;
  font-size: 20rpx;
  color: #0f766e;
}
.row-jp {
  display: flex;
  align-items: center;
  gap: 10rpx;
  margin-top: 10rpx;
  padding: 10rpx 12rpx;
  background: #f0fdfa;
  border: 1rpx solid #99f6e4;
  border-radius: 6rpx;
}
.jp-lab {
  font-size: 20rpx;
  font-weight: 600;
  color: #0f766e;
  flex-shrink: 0;
}
.jp-sum {
  flex: 1;
  min-width: 0;
  font-size: 20rpx;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.jp-go {
  font-size: 20rpx;
  color: #0f766e;
  flex-shrink: 0;
}
.japan-modal {
  position: fixed; top: 50%; left: 4vw; right: 4vw; bottom: auto;
  max-height: 80vh;
  background: #fff; border-radius: 12rpx; z-index: 201;
  display: flex; flex-direction: column;
  transform: translateY(-50%) scale(0.96); opacity: 0;
  transition: transform 0.2s ease, opacity 0.2s ease;
  pointer-events: none;
  &.show { transform: translateY(-50%) scale(1); opacity: 1; pointer-events: auto; }
}
.japan-body {
  flex: 1;
  max-height: 70vh;
  padding-bottom: 16rpx;
}
.japan-loading {
  padding: 40rpx 24rpx;
  text-align: center;
  font-size: 24rpx;
  color: #64748b;
}
.similar-stats {
  flex-shrink: 0;
  padding: 12rpx 24rpx;
  background: #f8fafb;
  border-bottom: 1rpx solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}
.stats-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8rpx 16rpx;
  font-size: 22rpx;
  font-variant-numeric: tabular-nums;
}
.stats-label {
  width: 72rpx;
  flex-shrink: 0;
  color: #64748b;
  font-weight: 600;
  font-size: 20rpx;
}
.stats-item { font-weight: 500; }
.stats-n { color: #94a3b8; font-size: 20rpx; margin-left: 4rpx; }
.stats-empty { color: #94a3b8; font-size: 20rpx; }
.similar-body {
  flex: 0 1 auto; overflow: auto; min-height: 0;
  max-height: calc(88vh - 200rpx);
}
.similar-table { min-width: 1430rpx; padding: 0 16rpx 24rpx; }
.similar-row {
  display: flex; align-items: center; padding: 14rpx 0;
  border-bottom: 1rpx solid #f1f5f9; gap: 4rpx;
  &.is-single { background: #fff7f7; }
}
.similar-thead {
  position: sticky; top: 0; background: #f8fafb;
  font-weight: 600; color: #64748b; font-size: 20rpx; z-index: 1;
}
.similar-row:not(.similar-thead) { font-size: 20rpx; color: #334155; }
.similar-empty { text-align: center; padding: 60rpx; color: #94a3b8; font-size: 24rpx; }

.col-sim {
  width: 120rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; gap: 4rpx;
}
.sim-num {
  width: 72rpx; text-align: right; flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.single-mark {
  width: 28rpx; height: 28rpx; flex-shrink: 0;
  font-size: 16rpx; font-weight: 700;
  color: transparent; text-align: center;
  border: 1rpx solid transparent; border-radius: 6rpx;
  line-height: 26rpx;
  &.on { color: #dc2626; border-color: #dc2626; }
}
.col-date { width: 110rpx; text-align: center; }
.col-league { width: 90rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-league.league-same { color: #2979ff; font-weight: 600; }
.col-team { width: 130rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-score { width: 70rpx; text-align: center; font-weight: 600; }
.col-result { width: 70rpx; text-align: center; font-weight: 500; }
.col-odds { width: 170rpx; text-align: center; }
.col-ah { width: 72rpx; text-align: center; font-variant-numeric: tabular-nums; }
.col-handicap { width: 70rpx; text-align: center; }
.col-ah-result { width: 70rpx; text-align: center; font-weight: 500; }

.r-win { color: #dc2626; }
.r-draw { color: #d97706; }
.r-loss { color: #059669; }
.ah-upper { color: #dc2626; }
.ah-lower { color: #059669; }
.ah-push { color: #64748b; }

/* 日期日历 */
.cal-mask {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 400;
}
.cal-panel {
  position: fixed; left: 0; right: 0; bottom: 0;
  background: #fff;
  border-radius: 12rpx 12rpx 0 0;
  z-index: 401;
  transform: translateY(100%);
  transition: transform 0.25s ease;
  padding-bottom: env(safe-area-inset-bottom);
  &.visible { transform: translateY(0); }
}
.cal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1rpx solid #f1f5f9;
}
.cal-cancel { font-size: 26rpx; color: #94a3b8; }
.cal-title { font-size: 28rpx; color: #0f172a; font-weight: 600; }
.cal-confirm { font-size: 26rpx; color: #0d9488; font-weight: 600; }
.cal-body { padding: 20rpx 24rpx 40rpx; }
.cal-nav {
  display: flex; align-items: center; justify-content: center;
  gap: 40rpx; margin-bottom: 20rpx;
}
.cal-arrow { font-size: 28rpx; color: #64748b; padding: 8rpx 16rpx; }
.cal-month { font-size: 26rpx; color: #0f172a; font-weight: 500; }
.cal-weekdays {
  display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 12rpx;
}
.cal-wd { text-align: center; font-size: 22rpx; color: #94a3b8; line-height: 2; }
.cal-days {
  display: grid; grid-template-columns: repeat(7, 1fr); gap: 4rpx 0;
}
.cal-day {
  text-align: center; font-size: 26rpx; color: #334155;
  line-height: 2.4; border-radius: 6rpx;
  &.cal-other { color: #e2e8f0; }
  &.cal-today { color: #0d9488; font-weight: 600; }
  &.cal-has:not(.cal-selected) { color: #0f766e; font-weight: 600; }
  &.cal-selected { background: #0d9488; color: #fff; font-weight: 600; }
}
</style>
