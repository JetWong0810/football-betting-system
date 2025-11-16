<template>
  <view class="matches-page">
    <mescroll-body ref="mescrollRef" :down="downOption" :up="upOption" :bottombar="false" @init="mescrollInit" @down="downCallback" @up="upCallback">
      <view class="list-content">
        <view v-if="visibleMatches.length > 0">
          <view class="day-section" v-for="group in groupedMatches" :key="group.key">
            <view class="day-header" @tap="toggleGroup(group.key)">
              <view class="day-title">
                <text class="date">{{ formatDateLabel(group.displayDate) }}</text>
                <text class="count-wrap"
                  >共<text class="count">{{ group.matches.length }}</text
                  >场</text
                >
                <text class="tip">(红框选项可投单关)</text>
              </view>
              <text class="arrow" :class="{ collapsed: collapsedMap[group.key] }">▲</text>
            </view>

            <view class="match-wrap" v-show="!collapsedMap[group.key]">
              <view class="match-row" v-for="(match, index) in group.matches" :key="match.matchId">
                <view class="row-left">
                  <text class="code">{{ displayMatchCode(match, group.displayDate, index + 1) }}</text>
                  <text class="league" :style="{ backgroundColor: pickLeagueColor(match.league) }">{{ truncateText(match.league, 3) }}</text>
                  <text class="time">{{ formatTime(match) }}</text>
                  <text class="attitude" v-if="match.notice">态度</text>
                </view>

                <view class="row-right">
                  <view class="teams-info">
                    <view class="teams-container">
                      <text class="team-name team-home">{{ truncateText(match.homeTeam.name, 3) }}</text>
                      <text class="vs">VS</text>
                      <text class="team-name team-away">{{ truncateText(match.awayTeam.name, 3) }}</text>
                    </view>
                  </view>

                  <view class="main-content">
                    <view class="odds-section">
                      <!-- 胜平负 -->
                      <view class="odds-row">
                        <text class="handicap">0</text>
                        <template v-if="match.wdl?.had">
                          <view
                            class="odds-item"
                            :class="{
                              'single-ok': isSingleFor(match, 'had'),
                              selected: isOddsSelected(match.matchId, 'had', 'win'),
                            }"
                            @tap="() => handleSelectOdds(match, 'had', 'win', '胜', match.wdl.had.win_odds)"
                          >
                            <text class="label">胜</text>
                            <text class="value">{{ formatOdds(match.wdl.had.win_odds) }}</text>
                          </view>
                          <view
                            class="odds-item"
                            :class="{
                              'single-ok': isSingleFor(match, 'had'),
                              selected: isOddsSelected(match.matchId, 'had', 'draw'),
                            }"
                            @tap="() => handleSelectOdds(match, 'had', 'draw', '平', match.wdl.had.draw_odds)"
                          >
                            <text class="label">平</text>
                            <text class="value">{{ formatOdds(match.wdl.had.draw_odds) }}</text>
                          </view>
                          <view
                            class="odds-item"
                            :class="{
                              'single-ok': isSingleFor(match, 'had'),
                              selected: isOddsSelected(match.matchId, 'had', 'lose'),
                            }"
                            @tap="() => handleSelectOdds(match, 'had', 'lose', '负', match.wdl.had.lose_odds)"
                          >
                            <text class="label">负</text>
                            <text class="value">{{ formatOdds(match.wdl.had.lose_odds) }}</text>
                          </view>
                        </template>
                        <template v-else>
                          <view class="odds-item not-sale">
                            <text class="not-sale-text">未</text>
                          </view>
                          <view class="odds-item not-sale">
                            <text class="not-sale-text">开</text>
                          </view>
                          <view class="odds-item not-sale">
                            <text class="not-sale-text">售</text>
                          </view>
                        </template>
                      </view>

                      <!-- 让球胜平负 -->
                      <view class="odds-row" v-if="match.wdl?.hhad">
                        <text class="handicap" :class="getHandicapClass(match.wdl.hhad.handicap)">{{ formatHandicap(match.wdl.hhad.handicap) }}</text>
                        <view
                          class="odds-item"
                          :class="{
                            'single-ok': isSingleFor(match, 'hhad'),
                            selected: isOddsSelected(match.matchId, 'hhad', 'win'),
                          }"
                          @tap="() => handleSelectOdds(match, 'hhad', 'win', '胜', match.wdl.hhad.win_odds, match.wdl.hhad.handicap)"
                        >
                          <text class="label">胜</text>
                          <text class="value">{{ formatOdds(match.wdl.hhad.win_odds) }}</text>
                        </view>
                        <view
                          class="odds-item"
                          :class="{
                            'single-ok': isSingleFor(match, 'hhad'),
                            selected: isOddsSelected(match.matchId, 'hhad', 'draw'),
                          }"
                          @tap="() => handleSelectOdds(match, 'hhad', 'draw', '平', match.wdl.hhad.draw_odds, match.wdl.hhad.handicap)"
                        >
                          <text class="label">平</text>
                          <text class="value">{{ formatOdds(match.wdl.hhad.draw_odds) }}</text>
                        </view>
                        <view
                          class="odds-item"
                          :class="{
                            'single-ok': isSingleFor(match, 'hhad'),
                            selected: isOddsSelected(match.matchId, 'hhad', 'lose'),
                          }"
                          @tap="() => handleSelectOdds(match, 'hhad', 'lose', '负', match.wdl.hhad.lose_odds, match.wdl.hhad.handicap)"
                        >
                          <text class="label">负</text>
                          <text class="value">{{ formatOdds(match.wdl.hhad.lose_odds) }}</text>
                        </view>
                      </view>
                    </view>

                    <view class="side-links">
                      <text class="link-index">指数</text>
                      <text class="link-more" :class="{ active: hasMatchSelection(match.matchId) }" @tap="goPlays(match.matchId, match)"> 更多玩法 </text>
                    </view>
                  </view>
                </view>
              </view>
            </view>
          </view>
        </view>
      </view>
    </mescroll-body>

    <!-- 投注车组件 -->
    <BetCart />
  </view>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { onShow, onPageScroll, onReachBottom } from "@dcloudio/uni-app";
import dayjs from "dayjs";
import MescrollBody from "mescroll-uni/mescroll-body.vue";
import BetCart from "@/components/BetCart.vue";
import { useMatchStore } from "@/stores/matchStore";
import { useBetCartStore } from "@/stores/betCartStore";

const matchStore = useMatchStore();
const betCartStore = useBetCartStore();
const matches = computed(() => matchStore.matches);
const loading = computed(() => matchStore.loading);
const collapsedMap = reactive({});

// mescroll 配置
const mescrollRef = ref(null);
let mescroll = null;

// 初始化 mescroll
function mescrollInit(mescrollInstance) {
  mescroll = mescrollInstance;
  // 延迟触发上拉加载，确保 mescroll 完全初始化
  setTimeout(() => {
    if (mescroll && mescroll.triggerUpScroll) {
      mescroll.triggerUpScroll();
    }
  }, 100);
}

// 下拉刷新回调
function downCallback() {
  matchStore
    .refreshMatches()
    .then(() => {
      if (mescroll) {
        mescroll.endSuccess();
      }
    })
    .catch(() => {
      if (mescroll) {
        mescroll.endErr();
      }
    });
}

// 上拉加载回调（接口一次性返回所有数据，不需要分页）
function upCallback(page) {
  // 只处理第一页，因为接口一次性返回所有数据
  if (page.num === 1) {
    matchStore
      .refreshMatches()
      .then(() => {
        const dataLength = matches.value.length;
        if (mescroll) {
          // 第二个参数传 false，表示没有更多数据
          mescroll.endSuccess(dataLength, false);
        }
      })
      .catch(() => {
        if (mescroll) {
          mescroll.endErr();
        }
      });
  } else {
    if (mescroll) {
      mescroll.endSuccess(0, false);
    }
  }
}

// 下拉刷新配置
const downOption = {
  auto: false, // 不自动加载
};

// 上拉加载配置（接口一次性返回所有数据，不需要分页）
const upOption = {
  auto: false, // 手动触发上拉加载（在 mescrollInit 中触发）
  page: {
    num: 0, // 当前页码,默认0,回调之前会加1,即callback(page)会从1开始
    size: 1000, // 每页数据的数量（设置一个大值，因为接口返回所有数据）
  },
  noMoreSize: 0, // 不显示"无更多数据"提示
  empty: {
    use: true, // 使用 mescroll 的空布局
    tip: "暂无可售赛事", // 空布局提示文本
  },
};

const visibleMatches = computed(() => matches.value.filter((match) => !isFinishedMatch(match?.status)));

const groupedMatches = computed(() => {
  const bucket = visibleMatches.value.reduce((acc, match) => {
    const key = extractIssueKey(match);
    if (!acc[key]) acc[key] = [];
    acc[key].push(match);
    return acc;
  }, {});

  return Object.keys(bucket)
    .map((key) => {
      const matchesInGroup = bucket[key].slice().sort(sortMatchesWithinDay);
      const issueDate = deriveIssueDate(key) || guessGroupDate(matchesInGroup);
      const sortValue = issueDate ? dayjs(issueDate).valueOf() : Number.MAX_SAFE_INTEGER;
      return {
        key,
        matches: matchesInGroup,
        displayDate: issueDate || "待定",
        sortValue,
      };
    })
    .sort((a, b) => {
      if (a.sortValue !== b.sortValue) {
        return a.sortValue - b.sortValue;
      }
      if (a.key === "待定") return 1;
      if (b.key === "待定") return -1;
      return a.key.localeCompare(b.key);
    });
});

onShow(() => {
  uni.$emit("tab-active", "matches");
});

// mescroll-body 需要的页面生命周期
onPageScroll((e) => {
  if (mescroll && mescroll.onPageScroll) {
    mescroll.onPageScroll(e);
  }
});

onReachBottom(() => {
  if (mescroll && mescroll.onReachBottom) {
    mescroll.onReachBottom();
  }
});

function goPlays(matchId, match) {
  const title = `${match.homeTeam.name} VS ${match.awayTeam.name}`;
  uni.navigateTo({
    url: `/pages/matches/plays?matchId=${matchId}&title=${encodeURIComponent(title)}`,
  });
}

function toggleGroup(date) {
  collapsedMap[date] = !collapsedMap[date];
}

function extractIssueKey(match) {
  if (match?.matchNumber) {
    return String(match.matchNumber);
  }
  const digits = match?.matchCode?.replace(/\D/g, "");
  if (digits && digits.length === 6) {
    return digits;
  }
  return match?.matchDate || "待定";
}

function deriveIssueDate(issueKey) {
  const key = String(issueKey || "").trim();
  if (/^\d{6}$/.test(key)) {
    const year = 2000 + Number(key.slice(0, 2));
    const month = key.slice(2, 4);
    const day = key.slice(4, 6);
    const dateStr = `${year}-${month}-${day}`;
    return dayjs(dateStr).isValid() ? dateStr : null;
  }
  if (dayjs(key).isValid()) {
    return dayjs(key).format("YYYY-MM-DD");
  }
  return null;
}

function guessGroupDate(matches) {
  for (const match of matches) {
    if (match?.matchDate && dayjs(match.matchDate).isValid()) {
      return match.matchDate;
    }
  }
  return null;
}

function formatOdds(value) {
  if (value === null || value === undefined) return "--";
  return Number(value).toFixed(2);
}

function formatHandicap(value) {
  if (!value && value !== 0) return 0;
  return value > 0 ? `+${value}` : value;
}

function formatDateLabel(date) {
  if (!date || date === "待定") {
    return "待定时间";
  }
  const weekMap = ["日", "一", "二", "三", "四", "五", "六"];
  const d = dayjs(date);
  return `周${weekMap[d.day()]} ${d.format("YYYY-MM-DD")}`;
}

function displayMatchCode(match, date, index) {
  const fallbackDate = match?.matchDate || date;
  if (match?.matchCode) {
    return match.matchCode;
  }
  return formatMatchCode(fallbackDate, index);
}

function formatMatchCode(date, index) {
  if (!date || date === "待定") {
    return `待${String(index).padStart(3, "0")}`;
  }
  const weekMap = ["日", "一", "二", "三", "四", "五", "六"];
  const d = dayjs(date);
  const weekChar = weekMap[d.day()];
  return `${weekChar}${String(index).padStart(3, "0")}`;
}

function formatTime(match) {
  if (match.matchTime) {
    return match.matchTime.slice(0, 5);
  }
  return "待定";
}

function truncateText(text, maxLength) {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength);
}

function isSingleFor(match, oddsType) {
  const oddsSingle = match?.wdl?.[oddsType]?.is_single;
  if (oddsSingle !== undefined && oddsSingle !== null) {
    return Number(oddsSingle) === 1;
  }
  return Boolean(match?.isSingle);
}

function isFinishedMatch(status) {
  if (!status) return false;
  const normalized = String(status).toLowerCase();
  return normalized === "finished" || normalized === "cancelled";
}

function sortMatchesWithinDay(a, b) {
  const timeA = getMatchTimeValue(a);
  const timeB = getMatchTimeValue(b);
  if (timeA !== timeB) {
    return timeA - timeB;
  }
  const codeA = getMatchCodeNumber(a);
  const codeB = getMatchCodeNumber(b);
  if (codeA !== codeB) {
    return codeA - codeB;
  }
  return (a.matchId || "").localeCompare(b.matchId || "");
}

function getMatchTimeValue(match) {
  if (match?.matchDate) {
    const time = match.matchTime || "00:00:00";
    const dt = dayjs(`${match.matchDate} ${time}`);
    if (dt.isValid()) {
      return dt.valueOf();
    }
  }
  if (match?.kickoff) {
    const kickoff = dayjs(match.kickoff);
    if (kickoff.isValid()) {
      return kickoff.valueOf();
    }
  }
  return Number.MAX_SAFE_INTEGER;
}

function getMatchCodeNumber(match) {
  if (!match?.matchCode) return Number.MAX_SAFE_INTEGER;
  const digits = match.matchCode.replace(/\D/g, "");
  const value = parseInt(digits, 10);
  return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value;
}

function getLeagueSuffix(league) {
  // 提取联赛简称，如"英锦赛" -> "英甲"
  if (!league) return "";
  if (league.includes("英")) {
    if (league.includes("甲")) return "英甲";
    if (league.includes("乙")) return "英乙";
    return "英甲";
  }
  if (league.includes("西")) return "西甲";
  if (league.includes("意")) return "意甲";
  if (league.includes("德")) return "德甲";
  if (league.includes("法")) return "法甲";
  return "";
}

function getHandicapClass(handicap) {
  if (!handicap && handicap !== 0) return "gray";
  if (handicap > 0) return "green";
  if (handicap < 0) return "red";
  return "gray";
}

function pickLeagueColor(league) {
  const palette = ["#bb0060", "#1d7dde", "#f97316", "#10b981"];
  const seed = league ? league.charCodeAt(0) : 0;
  return palette[seed % palette.length];
}

// ========== 投注选择相关方法 ==========

/**
 * 处理赔率选择
 */
function handleSelectOdds(match, playType, selection, selectionLabel, odds, handicap = null) {
  if (!odds || odds === "--") {
    uni.showToast({ title: "该选项暂未开售", icon: "none" });
    return;
  }

  const playNameMap = {
    had: "胜平负",
    hhad: "让球胜平负",
  };

  betCartStore.toggleSelection({
    matchId: match.matchId,
    homeTeam: match.homeTeam?.name || "",
    awayTeam: match.awayTeam?.name || "",
    league: match.league || "",
    matchDate: match.matchDate || "",
    matchTime: match.matchTime || "00:00",
    playType,
    playName: playNameMap[playType] || playType,
    selection,
    selectionLabel,
    odds: Number(odds),
    handicap,
    isSingle: isSingleFor(match, playType),
  });
}

/**
 * 检查赔率是否已选中
 */
function isOddsSelected(matchId, playType, selection) {
  return betCartStore.isSelected(matchId, playType, selection);
}

/**
 * 检查某场比赛是否有选项被选中
 */
function hasMatchSelection(matchId) {
  return betCartStore.selections.some((s) => s.matchId === matchId);
}
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.matches-page {
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
  min-height: 100vh;
}

.list-content {
  padding-bottom: 0rpx;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16rpx 24rpx 12rpx;
  background: transparent;
  letter-spacing: 0.03em;
}

.day-title {
  font-size: 22rpx;
  color: #666;
  line-height: 1.6;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10rpx;

  .date {
    font-weight: 500;
  }

  .count-wrap {
    color: #666;
  }

  .count {
    color: #ff7875;
    font-weight: 500;
  }

  .tip {
    color: #999;
    font-size: 20rpx;
  }
}

.arrow {
  font-size: 24rpx;
  color: #999;
  transition: transform 0.2s ease;
}

.arrow.collapsed {
  transform: rotate(180deg);
}

.match-wrap {
  background: #fff;
  padding: 0 24rpx;
  border-radius: 20rpx;
  box-shadow: 0 4rpx 12rpx rgba(13, 148, 136, 0.08);
  overflow: hidden;
}

.match-row {
  display: flex;
  padding: 0;
  border-bottom: 1px solid #f0f0f0;
  background: #fff;
}

.match-row:last-child {
  border-bottom: none;
}

.row-left {
  width: 120rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12rpx 0;
  gap: 12rpx;
  flex-shrink: 0;
}

.row-left .code {
  font-size: 22rpx;
  color: #666;
  white-space: nowrap;
  line-height: 1.2;
}

.league {
  border-radius: 6rpx;
  padding: 4rpx 10rpx;
  color: #fff;
  font-size: 20rpx;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100rpx;
  line-height: 1.3;
}

.time {
  font-size: 22rpx;
  color: #666;
  white-space: nowrap;
  line-height: 1.2;
}

.attitude {
  font-size: 18rpx;
  color: #666;
  background: #f8f8f8;
  padding: 3rpx 8rpx;
  border-radius: 3rpx;
  line-height: 1.2;
}

.row-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16rpx 16rpx 16rpx 16rpx;
  min-width: 0;
}

.teams-info {
  margin-bottom: 10rpx;
  display: flex;
  align-items: center;
}

.teams-container {
  display: flex;
  align-items: center;
  gap: 4rpx;
  margin-left: 46rpx;
  flex: 1;
  max-width: 374rpx;
  min-width: 0;
}

.team-name {
  flex: 1;
  font-size: 26rpx;
  font-weight: 400;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;

  &.team-home {
    text-align: right;
  }

  &.team-away {
    text-align: left;
  }
}

.vs {
  flex: 1;
  font-size: 18rpx;
  color: #999;
  font-weight: 400;
  text-align: center;
  white-space: nowrap;
  min-width: 0;
}

.main-content {
  display: flex;
  align-items: flex-start;
  gap: 12rpx;
}

.odds-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  min-width: 0;
  max-width: 420rpx;
}

.odds-row {
  display: flex;
  align-items: stretch;
  gap: 4rpx;
}

.handicap {
  width: 42rpx;
  height: 42rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20rpx;
  font-weight: 500;
  flex-shrink: 0;
  border-radius: 50%;
  background-color: #f5f5f5;
  color: #666;
  position: relative;
  top: 4rpx;

  &.gray {
    color: #666;
    background-color: #f5f5f5;
  }

  &.green {
    color: #22c55e;
    background-color: #e8f8f0;
  }

  &.red {
    color: #ff7875;
    background-color: #fff1f0;
  }
}

.side-links {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 56rpx;
}

.odds-item {
  flex: 1;
  border: 1px solid #e5e5e5;
  border-radius: 6rpx;
  padding: 0 10rpx;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  box-sizing: border-box;
  min-width: 0;
  height: 60rpx;
  transition: all 0.2s;
  cursor: pointer;

  &.single-ok {
    border-color: #ffa39e;
    border-width: 1rpx;
  }

  &.selected {
    background: #ff7875;
    border-color: #ff7875;

    .label,
    .value {
      color: #fff !important;
      font-weight: 600;
    }
  }

  &.not-sale {
    border-color: #e5e5e5;
    background: #f9f9f9;
    justify-content: center;
    cursor: not-allowed;
  }

  .label {
    font-size: 24rpx;
    color: #333;
    white-space: nowrap;
    font-weight: 400;
  }

  .value {
    font-size: 22rpx;
    color: #666;
    white-space: nowrap;
  }

  .not-sale-text {
    font-size: 22rpx;
    color: #999;
    white-space: nowrap;
  }
}

.link-index {
  color: #0d9488;
  font-size: 22rpx;
  white-space: nowrap;
  line-height: 60rpx;
  text-align: center;
  font-weight: 500;
}

.link-more {
  color: #0d9488;
  font-size: 22rpx;
  line-height: 1.4;
  text-align: center;
  word-break: break-all;
  width: 56rpx;
  font-weight: 500;
  transition: all 0.2s;

  &.active {
    color: #ff7875;
    font-weight: 700;
  }
}

.state {
  text-align: center;
  color: #999;
  padding: 32rpx 0;
  font-size: 24rpx;
}

.state.empty {
  color: #666;
}
</style>
