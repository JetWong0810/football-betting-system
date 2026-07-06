<template>
  <view class="review-detail">
    <!-- 加载中 -->
    <view class="loading-state" v-if="loading">
      <text class="loading-text">加载复盘中...</text>
    </view>

    <!-- 无预测记录 -->
    <view class="empty-state" v-else-if="!data.hasPrediction">
      <text class="empty-text">该比赛暂无预测记录，无法复盘</text>
      <text class="empty-sub">预测后会自动保存记录，赛后可在此复盘</text>
    </view>

    <block v-else>
      <!-- 比赛信息头 -->
      <view class="match-header">
        <view class="header-meta">
          <text class="league-badge" :style="{ backgroundColor: leagueColor }">{{ matchInfo.league }}</text>
          <text class="match-time">{{ matchInfo.time }}</text>
          <view v-if="prediction.overallReverse" class="reverse-tag">
            <text>整体逆向</text>
          </view>
        </view>
        <view class="header-teams">
          <text class="team home">{{ matchInfo.home }}</text>
          <view class="center-info">
            <text class="score">{{ matchInfo.homeScore }} - {{ matchInfo.awayScore }}</text>
            <text class="handicap-tag" v-if="prediction.handicap !== null">
              盘口 {{ formatHandicap(prediction.handicap) }}
            </text>
          </view>
          <text class="team away">{{ matchInfo.away }}</text>
        </view>
      </view>

      <!-- 预测结果卡 -->
      <view class="result-card" :class="verdictClass">
        <view class="result-main">
          <text class="result-label">预测方向</text>
          <text class="result-text">{{ dirLabel(prediction.direction) }}</text>
        </view>
        <view class="result-confidence">
          <text class="conf-value">{{ prediction.confidence }}%</text>
          <text class="conf-label">置信度</text>
        </view>
        <view class="result-verdict">
          <text class="verdict-text" v-if="actual && actual.hit === true">命中</text>
          <text class="verdict-text" v-else-if="actual && actual.hit === false">未中</text>
          <text class="verdict-text" v-else-if="actual && actual.direction === 'push'">走水</text>
          <text class="verdict-text" v-else>未完赛</text>
        </view>
      </view>

      <!-- 实际盘路 -->
      <view class="actual-section" v-if="actual">
        <view class="section-header">
          <text class="section-title">实际盘路</text>
        </view>
        <view class="actual-row">
          <view class="actual-cell">
            <text class="actual-label">终盘方向</text>
            <text class="actual-val" :class="'dir-' + actual.direction">{{ dirLabel(actual.direction) }}</text>
          </view>
          <view class="actual-cell">
            <text class="actual-label">调整值</text>
            <text class="actual-val">{{ adjustedText }}</text>
          </view>
        </view>
      </view>

      <!-- 因子复盘 -->
      <view class="factors-section">
        <view class="section-header">
          <text class="section-title">因子复盘</text>
          <text class="section-sub">事后看各因子方向是否正确</text>
        </view>
        <view class="factor-list">
          <view class="factor-card" v-for="(f, idx) in factorVerdict" :key="idx" :class="factorClass(f)">
            <view class="factor-header">
              <view class="factor-num">
                <text>{{ idx + 1 }}</text>
              </view>
              <text class="factor-name">{{ f.name }}</text>
              <view class="factor-result">
                <text class="factor-direction" :class="'dir-' + f.direction">{{ dirLabel(f.direction) }}</text>
                <text class="factor-correct" v-if="f.correct === true">对</text>
                <text class="factor-correct" v-else-if="f.correct === false">错</text>
                <text class="factor-correct neutral" v-else>—</text>
              </view>
            </view>
            <view class="factor-meta">
              <view class="score-bar">
                <view class="score-fill" :style="{ width: (f.score || 0) * 10 + '%' }"></view>
              </view>
              <text class="score-text">{{ f.score }}/10</text>
            </view>
            <text class="factor-reason" v-if="f.reason">{{ f.reason }}</text>
          </view>
        </view>
      </view>

      <!-- AI 分析 -->
      <view class="ai-section" v-if="prediction.analysis">
        <view class="section-header">
          <text class="section-title">AI 综合分析</text>
          <text class="analysis-time">{{ predictedAtText }}</text>
        </view>
        <view class="ai-content">
          <text>{{ prediction.analysis }}</text>
        </view>
      </view>
    </block>
  </view>
</template>

<script setup>
import { ref, computed } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { request } from "@/utils/http";

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

const loading = ref(true);
const data = ref({ hasPrediction: false });

const matchInfo = computed(() => {
  const m = data.value.match || {};
  return {
    league: m.league || "",
    home: m.homeTeam?.name || "",
    away: m.awayTeam?.name || "",
    time: (m.matchDate || "") + " " + (m.matchTime || "").slice(0, 5),
    homeScore: m.homeScore ?? "-",
    awayScore: m.awayScore ?? "-",
  };
});

const prediction = computed(() => data.value.prediction || {});
const actual = computed(() => data.value.actual || null);
const factorVerdict = computed(() => data.value.factorVerdict || []);

const leagueColor = computed(() => getLeagueColor(matchInfo.value.league));

const verdictClass = computed(() => {
  if (!actual.value) return "";
  if (actual.value.hit === true) return "verdict-hit";
  if (actual.value.hit === false) return "verdict-miss";
  return "verdict-push";
});

const adjustedText = computed(() => {
  if (!actual.value || prediction.value.handicap === null || actual.value.homeScore === null) return "-";
  const adj = (actual.value.homeScore - actual.value.awayScore) + Number(prediction.value.handicap);
  return (adj > 0 ? "+" : "") + adj.toFixed(2);
});

const predictedAtText = computed(() => {
  const t = prediction.value.predictedAt || "";
  return t ? "预测于 " + t.slice(0, 16) : "";
});

function dirLabel(d) {
  if (d === "upper") return "上盘";
  if (d === "lower") return "下盘";
  if (d === "push") return "走水";
  return "中性";
}

function formatHandicap(h) {
  if (h === null || h === undefined) return "-";
  const n = Number(h);
  if (n === 0) return "0";
  return n > 0 ? `+${n}` : String(n);
}

function factorClass(f) {
  if (f.correct === true) return "factor-correct";
  if (f.correct === false) return "factor-wrong";
  return "";
}

onLoad(async (opts) => {
  const matchId = opts.matchId;
  if (!matchId) {
    loading.value = false;
    return;
  }
  try {
    const res = await request({ url: `/api/review/${matchId}`, method: "GET" });
    data.value = res || { hasPrediction: false };
  } catch (e) {
    uni.showToast({ title: "加载复盘失败", icon: "none" });
    data.value = { hasPrediction: false };
  } finally {
    loading.value = false;
  }
});
</script>

<style lang="scss" scoped>
.review-detail {
  min-height: 100vh;
  background: linear-gradient(180deg, #ecfdf5 0%, #f0fdf9 100%);
  padding: 24rpx 24rpx 60rpx;
  box-sizing: border-box;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 200rpx 0;
  gap: 12rpx;
}

.loading-text {
  font-size: 26rpx;
  color: #aaa;
}

.empty-text {
  font-size: 28rpx;
  color: #888;
}

.empty-sub {
  font-size: 22rpx;
  color: #bbb;
}

/* ===== 比赛信息头 ===== */
.match-header {
  background: #fff;
  border-radius: 14rpx;
  padding: 24rpx;
  margin-bottom: 24rpx;
  box-shadow: 0 2rpx 12rpx rgba(13, 148, 136, 0.06);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 20rpx;
}

.league-badge {
  font-size: 20rpx;
  color: #fff;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;
  line-height: 1.5;
}

.match-time {
  font-size: 22rpx;
  color: #aaa;
}

.reverse-tag {
  background: #fef3c7;
  color: #b45309;
  font-size: 20rpx;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;
}

.header-teams {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.team {
  font-size: 28rpx;
  color: #333;
  font-weight: 600;
  width: 160rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.home { text-align: left; }
  &.away { text-align: right; }
}

.center-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;
}

.score {
  font-size: 36rpx;
  font-weight: 700;
  color: #0d9488;
}

.handicap-tag {
  font-size: 20rpx;
  color: #888;
  background: #f5f5f5;
  padding: 2rpx 12rpx;
  border-radius: 6rpx;
}

/* ===== 预测结果卡 ===== */
.result-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-radius: 14rpx;
  padding: 28rpx 24rpx;
  margin-bottom: 24rpx;
  border-left: 8rpx solid #d1d5db;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.04);

  &.verdict-hit { border-left-color: #059669; }
  &.verdict-miss { border-left-color: #ef4444; }
  &.verdict-push { border-left-color: #d1d5db; }
}

.result-main {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.result-label {
  font-size: 20rpx;
  color: #aaa;
}

.result-text {
  font-size: 36rpx;
  font-weight: 700;
  color: #0d9488;
}

.result-confidence {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.conf-value {
  font-size: 32rpx;
  font-weight: 700;
  color: #333;
}

.conf-label {
  font-size: 18rpx;
  color: #aaa;
}

.result-verdict {
  .verdict-text {
    font-size: 26rpx;
    font-weight: 600;
    padding: 8rpx 20rpx;
    border-radius: 6rpx;
    background: #f3f4f6;
    color: #6b7280;
  }
}

.verdict-hit .result-verdict .verdict-text { background: #d1fae5; color: #059669; }
.verdict-miss .result-verdict .verdict-text { background: #fee2e2; color: #ef4444; }

/* ===== 实际盘路 ===== */
.actual-section {
  background: #fff;
  border-radius: 14rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 24rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.04);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16rpx;
}

.section-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
}

.section-sub {
  font-size: 20rpx;
  color: #aaa;
}

.actual-row {
  display: flex;
  gap: 24rpx;
}

.actual-cell {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.actual-label {
  font-size: 20rpx;
  color: #aaa;
}

.actual-val {
  font-size: 28rpx;
  font-weight: 600;
  color: #333;

  &.dir-upper { color: #dc2626; }
  &.dir-lower { color: #2563eb; }
  &.dir-push { color: #6b7280; }
}

/* ===== 因子复盘 ===== */
.factors-section {
  margin-bottom: 24rpx;
}

.factor-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.factor-card {
  background: #fff;
  border-radius: 12rpx;
  padding: 20rpx;
  border-left: 6rpx solid #e5e7eb;
  box-shadow: 0 2rpx 10rpx rgba(0, 0, 0, 0.03);

  &.factor-correct { border-left-color: #059669; }
  &.factor-wrong { border-left-color: #ef4444; }
}

.factor-header {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 12rpx;
}

.factor-num {
  width: 36rpx;
  height: 36rpx;
  border-radius: 6rpx;
  background: #0d9488;
  color: #fff;
  font-size: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.factor-name {
  flex: 1;
  font-size: 26rpx;
  color: #333;
  font-weight: 500;
}

.factor-result {
  display: flex;
  align-items: center;
  gap: 10rpx;
}

.factor-direction {
  font-size: 22rpx;
  font-weight: 500;
  padding: 2rpx 12rpx;
  border-radius: 6rpx;
  background: #f5f5f5;
  color: #6b7280;

  &.dir-upper { color: #dc2626; background: #fef2f2; }
  &.dir-lower { color: #2563eb; background: #eff6ff; }
}

.factor-correct {
  font-size: 20rpx;
  font-weight: 600;
  color: #059669;
  background: #d1fae5;
  padding: 2rpx 12rpx;
  border-radius: 6rpx;

  &.neutral {
    color: #9ca3af;
    background: #f3f4f6;
  }
}

.factor-wrong .factor-correct:not(.neutral) {
  color: #ef4444;
  background: #fee2e2;
}

.factor-meta {
  display: flex;
  align-items: center;
  gap: 10rpx;
  margin-bottom: 10rpx;
}

.score-bar {
  flex: 1;
  height: 8rpx;
  background: #f3f4f6;
  border-radius: 4rpx;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #14b8a6, #0d9488);
}

.score-text {
  font-size: 20rpx;
  color: #aaa;
}

.factor-reason {
  font-size: 22rpx;
  color: #666;
  line-height: 1.5;
}

/* ===== AI 分析 ===== */
.ai-section {
  background: #fff;
  border-radius: 14rpx;
  padding: 20rpx 24rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.04);
}

.analysis-time {
  font-size: 20rpx;
  color: #bbb;
}

.ai-content {
  font-size: 24rpx;
  color: #555;
  line-height: 1.7;
}
</style>
