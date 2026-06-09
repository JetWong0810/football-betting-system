<template>
  <view class="results-page">
    <!-- 日期选择条 -->
    <view class="date-bar">
      <scroll-view scroll-x class="date-scroll">
        <view class="date-list">
          <view
            v-for="d in dateList"
            :key="d.value"
            class="date-item"
            :class="{ active: d.value === selectedDate }"
            @tap="selectDate(d.value)"
          >
            <text class="date-week">{{ d.week }}</text>
            <text class="date-day">{{ d.day }}</text>
          </view>
          <!-- 日历按钮 -->
          <view class="date-item calendar-btn" @tap="openCalendar">
            <text class="calendar-text">选择</text>
            <text class="calendar-text">日期</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <!-- 统计概览 -->
    <view class="stats-bar">
      <text class="stats-text">{{ selectedDateLabel }} 共<text class="stats-num">{{ matches.length }}</text>场已完赛</text>
    </view>

    <!-- 比赛列表 -->
    <view class="match-list">
      <view
        v-for="match in matches"
        :key="match.id"
        class="match-card"
        @tap="toggleExpand(match.id)"
      >
        <view class="card-body" :class="'border-' + resultType(match)">
          <!-- 左侧: 联赛+时间 -->
          <view class="card-meta">
            <text class="league-tag" :style="{ backgroundColor: match.leagueColor }">{{ match.league }}</text>
            <text class="match-time">{{ match.time }}</text>
          </view>

          <!-- 中间: 球队+比分 -->
          <view class="card-match">
            <text class="team-name home">{{ match.homeTeam }}</text>
            <view class="score-wrap">
              <text class="score-num">{{ match.homeScore }}</text>
              <text class="score-divider">:</text>
              <text class="score-num">{{ match.awayScore }}</text>
            </view>
            <text class="team-name away">{{ match.awayTeam }}</text>
          </view>

          <!-- 右侧: 联赛结果 -->
          <view class="card-result">
            <text class="spf-tag" :class="'spf-' + resultType(match)">{{ match.resultText }}</text>
          </view>
        </view>

        <!-- 展开详情 -->
        <view class="card-detail" v-if="expandedId === match.id">
          <!-- 亚盘 -->
          <view class="detail-row">
            <text class="detail-label">亚盘</text>
            <view v-if="asianCache[match.id]" class="asian-info">
              <text class="asian-val">{{ asianCache[match.id].handicap }}</text>
              <text class="asian-water">{{ (Number(asianCache[match.id].homeOdds) + 1).toFixed(2) }}/{{ (Number(asianCache[match.id].awayOdds) + 1).toFixed(2) }}</text>
              <text class="asian-res" :class="'ah-' + asianCache[match.id].result" v-if="asianCache[match.id].result">{{ handicapLabel(asianCache[match.id].result) }}</text>
            </view>
            <text class="detail-val" v-else-if="asianLoading[match.id]">加载中...</text>
            <text class="detail-val" v-else>无数据</text>
          </view>
          <!-- 竞彩赔率 -->
          <view class="detail-row">
            <text class="detail-label">竞彩</text>
            <view class="odds-chips">
              <text class="odds-chip" :class="{ 'chip-active': match.spfResult === '胜' }">胜{{ match.spfOdds?.win }}</text>
              <text class="odds-chip" :class="{ 'chip-active': match.spfResult === '平' }">平{{ match.spfOdds?.draw }}</text>
              <text class="odds-chip" :class="{ 'chip-active': match.spfResult === '负' }">负{{ match.spfOdds?.lose }}</text>
            </view>
          </view>
          <!-- 预测记录 -->
          <view class="detail-row" v-if="match.prediction">
            <text class="detail-label">预测</text>
            <view class="pred-info">
              <text class="pred-detail" :class="match.prediction.hit === true ? 'pred-hit-text' : match.prediction.hit === false ? 'pred-miss-text' : ''">
                {{ match.prediction.hit === true ? '✓' : match.prediction.hit === false ? '✗' : '' }} {{ match.prediction.direction }} {{ match.prediction.confidence }}%
              </text>
              <text class="pred-time">{{ match.prediction.time }}</text>
            </view>
          </view>
          <view class="detail-footer">
            <view class="btn-review" @tap.stop="onReview(match)">
              <text class="btn-review-text">复盘</text>
            </view>
          </view>
        </view>
      </view>
    </view>

    <!-- 加载中 -->
    <view class="loading-state" v-if="loading">
      <text class="loading-text">加载中...</text>
    </view>

    <!-- 空状态 -->
    <view class="empty-state" v-if="!loading && matches.length === 0">
      <text class="empty-text">该日期暂无已完赛比赛</text>
    </view>

    <!-- 日期选择弹窗 -->
    <view class="picker-mask" v-if="showDatePicker" @tap="showDatePicker = false"></view>
    <view class="picker-panel" :class="{ visible: showDatePicker }">
      <view class="picker-header">
        <text class="picker-cancel" @tap="showDatePicker = false">取消</text>
        <text class="picker-title">选择日期</text>
        <text class="picker-confirm" @tap="confirmPicker">确定</text>
      </view>
      <view class="picker-body">
        <view class="picker-month-nav">
          <text class="month-arrow" @tap="prevMonth">&lt;</text>
          <text class="month-label">{{ pickerYear }}年{{ pickerMonth }}月</text>
          <text class="month-arrow" @tap="nextMonth">&gt;</text>
        </view>
        <view class="picker-weekdays">
          <text class="wd" v-for="w in ['日','一','二','三','四','五','六']" :key="w">{{ w }}</text>
        </view>
        <view class="picker-days">
          <text
            v-for="(d, i) in calendarDays"
            :key="i"
            class="day-cell"
            :class="{
              'other-month': d.other,
              'is-today': d.isToday,
              'is-selected': d.dateStr === pickerSelected,
            }"
            @tap="d.other ? null : (pickerSelected = d.dateStr)"
          >{{ d.day }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { request } from "@/utils/http";

const WEEK_MAP = ["日", "一", "二", "三", "四", "五", "六"];
const LEAGUE_COLORS = ["#c41e3a", "#0d9488", "#1a3a8b", "#7c3aed", "#b45309", "#0369a1", "#be123c"];
const leagueColorMap = {};
let colorIdx = 0;

function getLeagueColor(league) {
  if (!league) return "#999";
  if (!leagueColorMap[league]) {
    leagueColorMap[league] = LEAGUE_COLORS[colorIdx % LEAGUE_COLORS.length];
    colorIdx++;
  }
  return leagueColorMap[league];
}

function buildDateList() {
  const list = [];
  const today = new Date();
  for (let i = 1; i <= 7; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    list.push({
      value: `${y}-${m}-${day}`,
      week: `周${WEEK_MAP[d.getDay()]}`,
      day: `${m}-${day}`,
    });
  }
  return list;
}

const dateList = ref(buildDateList());
const selectedDate = ref(dateList.value[0]?.value || "");
const expandedId = ref(null);
const loading = ref(false);
const matches = ref([]);

const selectedDateLabel = computed(() => {
  const d = dateList.value.find((i) => i.value === selectedDate.value);
  if (d) return `${d.week} ${d.day}`;
  const parts = selectedDate.value.split("-");
  if (parts.length === 3) {
    const dt = new Date(selectedDate.value);
    return `周${WEEK_MAP[dt.getDay()]} ${parts[1]}-${parts[2]}`;
  }
  return selectedDate.value;
});

function selectDate(val) {
  selectedDate.value = val;
  expandedId.value = null;
}

watch(selectedDate, () => { fetchResults(); }, { immediate: false });

onLoad(() => { fetchResults(); });

async function fetchResults() {
  loading.value = true;
  try {
    const data = await request({ url: "/api/match-results", method: "GET", data: { date: selectedDate.value } });
    matches.value = (data.items || []).map(transformMatch);
  } catch (e) {
    matches.value = [];
  } finally {
    loading.value = false;
  }
}

function transformMatch(item) {
  const hs = item.homeScore ?? null;
  const as = item.awayScore ?? null;
  const handicap = item.handicap ?? item.wdl?.hhad?.handicap ?? null;

  let handicapResult = null;
  if (handicap !== null && hs !== null && as !== null) {
    const adjusted = (hs - as) + Number(handicap);
    if (Math.abs(adjusted) < 0.01) handicapResult = "push";
    else if (adjusted > 0) handicapResult = "upper";
    else handicapResult = "lower";
  }

  let resultText = "";
  if (hs !== null && as !== null) {
    if (hs > as) resultText = "主胜";
    else if (hs < as) resultText = "客胜";
    else resultText = "平局";
  }

  let spfResult = null;
  if (hs !== null && as !== null) {
    if (hs > as) spfResult = "胜";
    else if (hs === as) spfResult = "平";
    else spfResult = "负";
  }

  const spfOdds = item.wdl?.had ? {
    win: Number(item.wdl.had.win_odds).toFixed(2),
    draw: Number(item.wdl.had.draw_odds).toFixed(2),
    lose: Number(item.wdl.had.lose_odds).toFixed(2),
  } : null;

  let prediction = null;
  if (item.prediction) {
    const pred = item.prediction;
    let hit = null;
    if (handicapResult && pred.direction) {
      const predDir = pred.direction === "upper" ? "upper" : pred.direction === "lower" ? "lower" : null;
      if (predDir) hit = predDir === handicapResult;
    }
    prediction = {
      direction: pred.direction === "upper" ? "上盘" : pred.direction === "lower" ? "下盘" : "中性",
      confidence: pred.confidence,
      hit,
      time: (pred.predictedAt || "").slice(5, 16),
    };
  }

  return {
    id: item.matchId,
    league: item.league || "",
    leagueColor: getLeagueColor(item.league),
    time: (item.matchTime || "").slice(0, 5),
    homeTeam: item.homeTeam?.name || "",
    awayTeam: item.awayTeam?.name || "",
    homeScore: hs,
    awayScore: as,
    resultText,
    handicap: handicap !== null ? (Number(handicap) > 0 ? `+${handicap}` : String(handicap)) : null,
    handicapResult,
    spfResult,
    spfOdds,
    prediction,
  };
}

// 日历弹窗
const showDatePicker = ref(false);
const pickerYear = ref(2026);
const pickerMonth = ref(6);
const pickerSelected = ref("");

const calendarDays = computed(() => {
  const y = pickerYear.value;
  const m = pickerMonth.value;
  const firstDay = new Date(y, m - 1, 1).getDay();
  const daysInMonth = new Date(y, m, 0).getDate();
  const daysInPrev = new Date(y, m - 1, 0).getDate();
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const cells = [];

  for (let i = firstDay - 1; i >= 0; i--) {
    const day = daysInPrev - i;
    const pm = m - 1 < 1 ? 12 : m - 1;
    const py = m - 1 < 1 ? y - 1 : y;
    cells.push({ day, other: true, dateStr: `${py}-${String(pm).padStart(2, "0")}-${String(day).padStart(2, "0")}`, isToday: false });
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, other: false, dateStr, isToday: dateStr === todayStr });
  }

  const remaining = 42 - cells.length;
  for (let d = 1; d <= remaining; d++) {
    const nm = m + 1 > 12 ? 1 : m + 1;
    const ny = m + 1 > 12 ? y + 1 : y;
    cells.push({ day: d, other: true, dateStr: `${ny}-${String(nm).padStart(2, "0")}-${String(d).padStart(2, "0")}`, isToday: false });
  }

  return cells;
});

function openCalendar() {
  const parts = selectedDate.value.split("-");
  pickerYear.value = parseInt(parts[0]);
  pickerMonth.value = parseInt(parts[1]);
  pickerSelected.value = selectedDate.value;
  showDatePicker.value = true;
}

function prevMonth() {
  if (pickerMonth.value === 1) { pickerMonth.value = 12; pickerYear.value--; }
  else pickerMonth.value--;
}

function nextMonth() {
  if (pickerMonth.value === 12) { pickerMonth.value = 1; pickerYear.value++; }
  else pickerMonth.value++;
}

function confirmPicker() {
  selectedDate.value = pickerSelected.value;
  expandedId.value = null;
  showDatePicker.value = false;
}

const asianCache = ref({});
const asianLoading = ref({});

function toggleExpand(id) {
  if (expandedId.value === id) {
    expandedId.value = null;
    return;
  }
  expandedId.value = id;
  if (!asianCache.value[id] && !asianLoading.value[id]) {
    fetchAsian(id);
  }
}

async function fetchAsian(matchId) {
  asianLoading.value[matchId] = true;
  try {
    const data = await request({ url: `/api/matches/${matchId}/indices`, method: "GET" });
    const asianList = data?.indices?.asian || [];
    const preferred = asianList.find((a) => a.bookmaker === "澳门") || asianList[0];
    if (preferred && preferred.current) {
      const hc = preferred.current.handicap;
      const match = matches.value.find((m) => m.id === matchId);
      // 亚盘handicap是正数=主让，显示为负号；0不加符号
      const displayHc = hc === 0 ? "0" : `-${hc}`;
      // 用亚盘盘口计算上下盘结果: 主队净胜 - 让球数
      let result = null;
      if (match && match.homeScore !== null && match.awayScore !== null && hc !== null) {
        const adjusted = (match.homeScore - match.awayScore) - hc;
        if (Math.abs(adjusted) < 0.01) result = "push";
        else if (adjusted > 0) result = "upper";
        else result = "lower";
      }
      asianCache.value[matchId] = {
        handicap: displayHc,
        homeOdds: preferred.current.home,
        awayOdds: preferred.current.away,
        result,
      };
    }
  } catch (e) {
    // 无亚盘数据
  } finally {
    asianLoading.value[matchId] = false;
  }
}

function resultType(match) {
  if (match.homeScore > match.awayScore) return "win";
  if (match.homeScore < match.awayScore) return "lose";
  return "draw";
}

function handicapLabel(r) {
  const map = { upper: "上盘", lower: "下盘", push: "走水" };
  return map[r] || r;
}

function onReview(match) {
  uni.showToast({ title: "复盘功能开发中", icon: "none" });
}
</script>

<style lang="scss" scoped>
.results-page {
  min-height: 100vh;
  background: linear-gradient(180deg, #ecfdf5 0%, #f0fdf9 100%);
  padding-bottom: 40rpx;
}

/* ===== 日期条 ===== */
.date-bar {
  background: #fff;
  padding: 16rpx 0;
  box-shadow: 0 1rpx 6rpx rgba(0, 0, 0, 0.04);
}

.date-scroll {
  white-space: nowrap;
}

.date-list {
  display: flex;
  padding: 0 16rpx;
  gap: 12rpx;
}

.date-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 10rpx 20rpx;
  border-radius: 10rpx;
  background: #f7f7f7;
  flex-shrink: 0;
  min-width: 88rpx;
  transition: all 0.2s;

  .date-week {
    font-size: 20rpx;
    color: #888;
    line-height: 1.4;
  }

  .date-day {
    font-size: 22rpx;
    color: #333;
    font-weight: 600;
    line-height: 1.4;
  }

  &.active {
    background: #0d9488;
    box-shadow: 0 4rpx 12rpx rgba(13, 148, 136, 0.3);

    .date-week,
    .date-day {
      color: #fff;
    }
  }
}

.calendar-btn {
  background: transparent;
  border: 1px dashed #bbb;

  .calendar-text {
    font-size: 18rpx;
    color: #999;
    line-height: 1.4;
  }
}

/* ===== 统计条 ===== */
.stats-bar {
  padding: 14rpx 28rpx;
}

.stats-text {
  font-size: 22rpx;
  color: #888;
}

.stats-num {
  color: #0d9488;
  font-weight: 700;
  margin: 0 4rpx;
}

/* ===== 比赛卡片 ===== */
.match-list {
  padding: 0 20rpx;
}

.match-card {
  background: #fff;
  border-radius: 14rpx;
  margin-bottom: 16rpx;
  box-shadow: 0 2rpx 12rpx rgba(13, 148, 136, 0.05);
  overflow: hidden;
}

.card-body {
  display: flex;
  align-items: center;
  padding: 18rpx 20rpx;
  gap: 12rpx;
  border-left: 6rpx solid transparent;

  &.border-win {
    border-left-color: #ef4444;
  }

  &.border-lose {
    border-left-color: #3b82f6;
  }

  &.border-draw {
    border-left-color: #d1d5db;
  }
}

.card-meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6rpx;
  width: 80rpx;
  flex-shrink: 0;
}

.league-tag {
  font-size: 18rpx;
  color: #fff;
  padding: 2rpx 10rpx;
  border-radius: 6rpx;
  white-space: nowrap;
  line-height: 1.5;
}

.match-time {
  font-size: 20rpx;
  color: #aaa;
  line-height: 1.4;
}

.card-match {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
}

.team-name {
  font-size: 26rpx;
  color: #333;
  font-weight: 500;
  width: 120rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.home {
    text-align: right;
  }

  &.away {
    text-align: left;
  }
}

.score-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 100rpx;
  margin: 0 16rpx;
}

.score-num {
  font-size: 32rpx;
  font-weight: 700;
  color: #0d9488;
  min-width: 32rpx;
  text-align: center;
}

.score-divider {
  font-size: 24rpx;
  color: #ccc;
  margin: 0 6rpx;
}

.card-result {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6rpx;
  width: 80rpx;
  flex-shrink: 0;
}

.spf-tag {
  font-size: 20rpx;
  padding: 3rpx 12rpx;
  border-radius: 6rpx;
  font-weight: 500;

  &.spf-win {
    background: #fef2f2;
    color: #dc2626;
  }

  &.spf-lose {
    background: #eff6ff;
    color: #2563eb;
  }

  &.spf-draw {
    background: #f3f4f6;
    color: #6b7280;
  }
}


/* ===== 展开详情 ===== */
.card-detail {
  border-top: 1px solid #f3f4f6;
  padding: 14rpx 20rpx 16rpx;
  background: #fafffe;
}

.detail-row {
  display: flex;
  align-items: center;
  margin-bottom: 10rpx;

  &:last-of-type {
    margin-bottom: 0;
  }
}

.detail-label {
  font-size: 20rpx;
  color: #aaa;
  width: 70rpx;
  flex-shrink: 0;
}

.detail-val {
  font-size: 20rpx;
  color: #555;
}

.asian-info {
  display: flex;
  align-items: center;
  gap: 10rpx;
}

.asian-val {
  font-size: 22rpx;
  color: #333;
  font-weight: 600;
}

.asian-water {
  font-size: 20rpx;
  color: #888;
}

.asian-res {
  font-size: 20rpx;
  font-weight: 600;
  padding: 2rpx 8rpx;
  border-radius: 4rpx;

  &.ah-upper {
    color: #dc2626;
    background: #fef2f2;
  }

  &.ah-lower {
    color: #2563eb;
    background: #eff6ff;
  }

  &.ah-push {
    color: #6b7280;
    background: #f3f4f6;
  }
}

.odds-chips {
  display: flex;
  gap: 8rpx;
}

.odds-chip {
  font-size: 18rpx;
  color: #888;
  padding: 2rpx 10rpx;
  border-radius: 4rpx;
  background: #f5f5f5;

  &.chip-active {
    background: #0d9488;
    color: #fff;
    font-weight: 500;
  }
}

.pred-info {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.pred-detail {
  font-size: 20rpx;
  color: #333;
  font-weight: 500;

  &.pred-hit-text {
    color: #059669;
  }

  &.pred-miss-text {
    color: #ef4444;
  }
}

.pred-time {
  font-size: 18rpx;
  color: #bbb;
}

.detail-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 12rpx;
}

.btn-review {
  background: #f0fdfa;
  border: 1px solid #99f6e4;
  border-radius: 8rpx;
  padding: 6rpx 20rpx;
}

.btn-review-text {
  font-size: 20rpx;
  color: #0d9488;
  font-weight: 500;
}

/* ===== 加载/空状态 ===== */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 120rpx 0;
}

.loading-text {
  font-size: 24rpx;
  color: #aaa;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 180rpx 0;
}

.empty-text {
  font-size: 24rpx;
  color: #bbb;
}

/* ===== 日期选择弹窗 ===== */
.picker-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1000;
}

.picker-panel {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  z-index: 1001;
  transform: translateY(100%);
  transition: transform 0.3s ease;

  &.visible {
    transform: translateY(0);
  }
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1px solid #f3f4f6;
}

.picker-cancel {
  font-size: 26rpx;
  color: #999;
}

.picker-title {
  font-size: 28rpx;
  color: #333;
  font-weight: 600;
}

.picker-confirm {
  font-size: 26rpx;
  color: #0d9488;
  font-weight: 600;
}

.picker-body {
  padding: 20rpx 24rpx 48rpx;
}

.picker-month-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 40rpx;
  margin-bottom: 20rpx;
}

.month-arrow {
  font-size: 28rpx;
  color: #666;
  padding: 8rpx 16rpx;
}

.month-label {
  font-size: 26rpx;
  color: #333;
  font-weight: 500;
}

.picker-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 12rpx;
}

.wd {
  text-align: center;
  font-size: 22rpx;
  color: #aaa;
  line-height: 2;
}

.picker-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4rpx 0;
}

.day-cell {
  text-align: center;
  font-size: 26rpx;
  color: #333;
  line-height: 2.4;
  border-radius: 8rpx;

  &.other-month {
    color: #ddd;
  }

  &.is-today {
    color: #0d9488;
    font-weight: 600;
  }

  &.is-selected {
    background: #0d9488;
    color: #fff;
    font-weight: 600;
  }
}
</style>
