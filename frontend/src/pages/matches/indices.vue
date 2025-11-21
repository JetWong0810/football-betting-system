<template>
  <view class="indices-page">
    <!-- 顶部比赛信息卡片 -->
    <view class="match-header">
      <view class="league-badge">{{ matchInfo.league }}</view>
      <view class="match-teams">
        <text class="team-name">{{ matchInfo.homeTeam }}</text>
        <text class="vs">VS</text>
        <text class="team-name">{{ matchInfo.awayTeam }}</text>
      </view>
      <view class="match-meta">
        <text class="date">{{ matchInfo.date }}</text>
        <text class="time">{{ matchInfo.time }}</text>
        <view class="status-badge" :class="matchInfo.statusClass">{{ matchInfo.status }}</view>
      </view>
      <view class="update-info">最后更新: {{ lastUpdateTime }}</view>
    </view>

    <!-- 一级 Tab 导航 -->
    <view class="primary-tabs">
      <view v-for="tab in primaryTabs" :key="tab.id" class="primary-tab" :class="{ active: activePrimaryTab === tab.id }" @tap="switchPrimaryTab(tab.id)">
        <text class="tab-text">{{ tab.name }}</text>
      </view>
    </view>

    <!-- 二级 Tab 导航 -->
    <view class="secondary-tabs">
      <scroll-view scroll-x class="tabs-scroll">
        <view v-for="tab in currentSecondaryTabs" :key="tab.id" class="secondary-tab" :class="{ active: activeSecondaryTab === tab.id }" @tap="switchSecondaryTab(tab.id)">
          <text class="tab-text">{{ tab.name }}</text>
        </view>
      </scroll-view>
    </view>

    <!-- 内容区域 -->
    <scroll-view scroll-y class="content-area">
      <!-- 指数 - 欧指 -->
      <view v-if="activePrimaryTab === 'indices' && activeSecondaryTab === 'european'" class="content-section">
        <view class="statistics-bar">
          <view class="stat-item stat-up">
            <text class="icon">📈</text>
            <text class="text">上升 {{ statistics.european.up }}家</text>
          </view>
          <view class="stat-item stat-neutral">
            <text class="icon">➖</text>
            <text class="text">不变 {{ statistics.european.neutral }}家</text>
          </view>
          <view class="stat-item stat-down">
            <text class="icon">📉</text>
            <text class="text">下降 {{ statistics.european.down }}家</text>
          </view>
        </view>

        <view class="compact-table">
          <view class="table-header">
            <view class="header-company">公司</view>
            <view class="header-data">
              <view class="col-label"></view>
              <view class="col-odds">主胜</view>
              <view class="col-odds">平局</view>
              <view class="col-odds">客胜</view>
              <view class="col-return">返还率</view>
            </view>
          </view>
          <template v-for="(item, index) in europeanOdds" :key="item.bookmaker">
            <!-- 每个公司的数据组 -->
            <view class="table-group" :class="{ 'row-even': index % 2 === 1 }">
              <view class="company-cell">
                <text class="company-name">{{ item.bookmaker }}</text>
              </view>
              <view class="data-rows">
                <!-- 初盘行 -->
                <view class="table-row">
                  <view class="col-label">
                    <text class="label-text initial">初</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value">{{ formatNumber(item.initial.win) }}</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value">{{ formatNumber(item.initial.draw) }}</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value">{{ formatNumber(item.initial.lose) }}</text>
                  </view>
                  <view class="col-return">
                    <text class="return-value">{{ formatNumber(item.returnRate) }}%</text>
                  </view>
                </view>
                <!-- 即时行 -->
                <view class="table-row">
                  <view class="col-label">
                    <text class="label-text current">即</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value" :class="getChangeClass(item.initial.win, item.current.win)">
                      {{ formatNumber(item.current.win) }}
                      <text class="arrow-tiny" v-if="item.initial.win !== item.current.win">
                        {{ item.current.win > item.initial.win ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value" :class="getChangeClass(item.initial.draw, item.current.draw)">
                      {{ formatNumber(item.current.draw) }}
                      <text class="arrow-tiny" v-if="item.initial.draw !== item.current.draw">
                        {{ item.current.draw > item.initial.draw ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value" :class="getChangeClass(item.initial.lose, item.current.lose)">
                      {{ formatNumber(item.current.lose) }}
                      <text class="arrow-tiny" v-if="item.initial.lose !== item.current.lose">
                        {{ item.current.lose > item.initial.lose ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                  <view class="col-return">
                    <text class="return-value">{{ formatNumber(item.returnRate) }}%</text>
                  </view>
                </view>
              </view>
            </view>
          </template>
        </view>
      </view>

      <!-- 指数 - 亚指 -->
      <view v-if="activePrimaryTab === 'indices' && activeSecondaryTab === 'asian'" class="content-section">
        <view class="statistics-bar">
          <view class="stat-item stat-up">
            <text class="icon">📈</text>
            <text class="text">盘口升 {{ statistics.asian.up }}家</text>
          </view>
          <view class="stat-item stat-neutral">
            <text class="icon">➖</text>
            <text class="text">不变 {{ statistics.asian.neutral }}家</text>
          </view>
          <view class="stat-item stat-down">
            <text class="icon">📉</text>
            <text class="text">盘口降 {{ statistics.asian.down }}家</text>
          </view>
        </view>

        <view class="odds-card" v-for="item in asianOdds" :key="item.bookmaker">
          <view class="bookmaker-name">
            <text class="name">{{ item.bookmaker }}</text>
          </view>
          <view class="odds-row asian-handicap">
            <view class="odds-col">
              <text class="label">初盘</text>
              <view class="handicap-values">
                <text class="value">{{ formatNumber(item.initial.home) }}</text>
                <text class="handicap">{{ formatNumber(item.initial.handicap) }}</text>
                <text class="value">{{ formatNumber(item.initial.away) }}</text>
              </view>
            </view>
            <view class="odds-col">
              <text class="label">即时</text>
              <view class="handicap-values">
                <text class="value" :class="getChangeClass(item.initial.home, item.current.home)">
                  {{ formatNumber(item.current.home) }}
                  <text class="arrow-small" v-if="item.initial.home !== item.current.home">
                    {{ item.current.home > item.initial.home ? "↑" : "↓" }}
                  </text>
                </text>
                <text class="handicap" :class="getHandicapChangeClass(item.initial.handicap, item.current.handicap)">
                  {{ formatNumber(item.current.handicap) }}
                </text>
                <text class="value" :class="getChangeClass(item.initial.away, item.current.away)">
                  {{ formatNumber(item.current.away) }}
                  <text class="arrow-small" v-if="item.initial.away !== item.current.away">
                    {{ item.current.away > item.initial.away ? "↑" : "↓" }}
                  </text>
                </text>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 指数 - 大小 -->
      <view v-if="activePrimaryTab === 'indices' && activeSecondaryTab === 'overunder'" class="content-section">
        <view class="statistics-bar">
          <view class="stat-item stat-up">
            <text class="icon">📈</text>
            <text class="text">大球上升 {{ statistics.overunder.up }}家</text>
          </view>
          <view class="stat-item stat-neutral">
            <text class="icon">➖</text>
            <text class="text">不变 {{ statistics.overunder.neutral }}家</text>
          </view>
          <view class="stat-item stat-down">
            <text class="icon">📉</text>
            <text class="text">大球下降 {{ statistics.overunder.down }}家</text>
          </view>
        </view>

        <view class="odds-card" v-for="item in overUnderOdds" :key="item.bookmaker">
          <view class="bookmaker-name">
            <text class="name">{{ item.bookmaker }}</text>
          </view>
          <view class="odds-row">
            <view class="odds-col">
              <text class="label">初盘</text>
              <view class="ou-values">
                <text class="value">大 {{ formatNumber(item.initial.over) }}</text>
                <text class="line">{{ formatNumber(item.initial.line) }}</text>
                <text class="value">小 {{ formatNumber(item.initial.under) }}</text>
              </view>
            </view>
            <view class="odds-col">
              <text class="label">即时</text>
              <view class="ou-values">
                <text class="value" :class="getChangeClass(item.initial.over, item.current.over)">
                  大 {{ formatNumber(item.current.over) }}
                  <text class="arrow-small" v-if="item.initial.over !== item.current.over">
                    {{ item.current.over > item.initial.over ? "↑" : "↓" }}
                  </text>
                </text>
                <text class="line" :class="getChangeClass(item.initial.line, item.current.line)">
                  {{ formatNumber(item.current.line) }}
                </text>
                <text class="value" :class="getChangeClass(item.initial.under, item.current.under)">
                  小 {{ formatNumber(item.current.under) }}
                  <text class="arrow-small" v-if="item.initial.under !== item.current.under">
                    {{ item.current.under > item.initial.under ? "↑" : "↓" }}
                  </text>
                </text>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 数据 - 基本面 -->
      <view v-if="activePrimaryTab === 'data' && activeSecondaryTab === 'fundamentals'" class="content-section">
        <!-- 1. 主队历史比赛数据 -->
        <view class="section-block">
          <view class="section-header" @tap="toggleSection('homeHistory')">
            <text class="section-title">{{ matchInfo.homeTeam }} 近期战绩</text>
            <text class="toggle-icon">{{ expandedSections.homeHistory ? "▼" : "▶" }}</text>
          </view>
          <view v-if="expandedSections.homeHistory" class="section-content">
            <view class="team-form-wrapper">
              <view class="form-indicator">
                <view v-for="(result, idx) in recentForm.home" :key="idx" class="form-dot" :class="result"></view>
              </view>
              <text class="stat-summary">近6场: {{ recentForm.homeSummary }}</text>
            </view>
            <view class="match-list">
              <view v-for="match in recentMatches.home" :key="match.id" class="match-item-compact">
                <text class="match-date">{{ match.date }}</text>
                <text class="opponent">{{ match.opponent }}</text>
                <text class="score">{{ match.score }}</text>
                <view class="result-badge" :class="match.result">{{ match.resultText }}</view>
              </view>
            </view>
          </view>
        </view>

        <!-- 2. 客队历史比赛数据 -->
        <view class="section-block">
          <view class="section-header" @tap="toggleSection('awayHistory')">
            <text class="section-title">{{ matchInfo.awayTeam }} 近期战绩</text>
            <text class="toggle-icon">{{ expandedSections.awayHistory ? "▼" : "▶" }}</text>
          </view>
          <view v-if="expandedSections.awayHistory" class="section-content">
            <view class="team-form-wrapper">
              <view class="form-indicator">
                <view v-for="(result, idx) in recentForm.away" :key="idx" class="form-dot" :class="result"></view>
              </view>
              <text class="stat-summary">近6场: {{ recentForm.awaySummary }}</text>
            </view>
            <view class="match-list">
              <view v-for="match in recentMatches.away" :key="match.id" class="match-item-compact">
                <text class="match-date">{{ match.date }}</text>
                <text class="opponent">{{ match.opponent }}</text>
                <text class="score">{{ match.score }}</text>
                <view class="result-badge" :class="match.result">{{ match.resultText }}</view>
              </view>
            </view>
          </view>
        </view>

        <!-- 3. 两队交锋数据 -->
        <view class="section-block">
          <view class="section-header" @tap="toggleSection('h2h')">
            <text class="section-title">两队交锋记录</text>
            <text class="toggle-icon">{{ expandedSections.h2h ? "▼" : "▶" }}</text>
          </view>
          <view v-if="expandedSections.h2h" class="section-content">
            <view class="h2h-summary">
              <view class="summary-item">
                <text class="count win">{{ h2hStats.homeWins }}</text>
                <text class="label">{{ matchInfo.homeTeam }}胜</text>
              </view>
              <view class="summary-item">
                <text class="count draw">{{ h2hStats.draws }}</text>
                <text class="label">平局</text>
              </view>
              <view class="summary-item">
                <text class="count lose">{{ h2hStats.awayWins }}</text>
                <text class="label">{{ matchInfo.awayTeam }}胜</text>
              </view>
            </view>
            <view class="match-list">
              <view v-for="match in h2hMatches" :key="match.id" class="h2h-match-item">
                <view class="h2h-header">
                  <text class="match-date">{{ match.date }}</text>
                  <text class="competition">{{ match.competition }}</text>
                </view>
                <view class="match-result">
                  <text class="team">{{ match.homeTeam }}</text>
                  <text class="score" :class="match.resultClass">{{ match.score }}</text>
                  <text class="team">{{ match.awayTeam }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 4. 未来赛程数据 -->
        <view class="section-block">
          <view class="section-header" @tap="toggleSection('schedule')">
            <text class="section-title">未来赛程</text>
            <text class="toggle-icon">{{ expandedSections.schedule ? "▼" : "▶" }}</text>
          </view>
          <view v-if="expandedSections.schedule" class="section-content">
            <view class="future-schedule-wrapper">
              <view class="team-schedule-section">
                <text class="team-schedule-title">{{ matchInfo.homeTeam }}</text>
                <view class="schedule-list">
                  <view v-for="match in futureSchedule.home" :key="match.id" class="schedule-item-inline">
                    <text class="match-date">{{ match.date }}</text>
                    <text class="opponent">vs {{ match.opponent }}</text>
                    <text class="competition">{{ match.competition }}</text>
                  </view>
                </view>
              </view>
              <view class="team-schedule-section">
                <text class="team-schedule-title">{{ matchInfo.awayTeam }}</text>
                <view class="schedule-list">
                  <view v-for="match in futureSchedule.away" :key="match.id" class="schedule-item-inline">
                    <text class="match-date">{{ match.date }}</text>
                    <text class="opponent">vs {{ match.opponent }}</text>
                    <text class="competition">{{ match.competition }}</text>
                  </view>
                </view>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 数据 - 技术面 -->
      <view v-if="activePrimaryTab === 'data' && activeSecondaryTab === 'technical'" class="content-section">
        <view class="placeholder">
          <text class="placeholder-icon">📈</text>
          <text class="placeholder-text">技术面分析功能</text>
          <text class="placeholder-desc">即将上线...</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref, computed, reactive } from "vue";
import dayjs from "dayjs";

// 比赛信息
const matchInfo = ref({
  homeTeam: "曼联",
  awayTeam: "利物浦",
  league: "英超",
  date: "2024-03-17",
  time: "20:00",
  status: "未开赛",
  statusClass: "pending",
});

const lastUpdateTime = computed(() => {
  return dayjs().format("YYYY-MM-DD HH:mm:ss");
});

// 一级 Tab
const primaryTabs = [
  { id: "indices", name: "指数" },
  { id: "data", name: "数据" },
];
const activePrimaryTab = ref("indices");

// 二级 Tab 配置
const secondaryTabsMap = {
  indices: [
    { id: "european", name: "欧指" },
    { id: "asian", name: "亚指" },
    { id: "overunder", name: "大小" },
  ],
  data: [
    { id: "fundamentals", name: "基本面" },
    { id: "technical", name: "技术面" },
  ],
};
const activeSecondaryTab = ref("european");

// 当前二级 Tab 列表
const currentSecondaryTabs = computed(() => {
  return secondaryTabsMap[activePrimaryTab.value] || [];
});

// 统计数据
const statistics = ref({
  european: { up: 8, neutral: 4, down: 3 },
  asian: { up: 5, neutral: 6, down: 4 },
  overunder: { up: 7, neutral: 3, down: 5 },
});

// 欧洲指数数据（模拟）
const europeanOdds = ref([
  {
    bookmaker: "最大值",
    initial: { win: 2.14, draw: 3.75, lose: 3.25 },
    current: { win: 2.26, draw: 3.5, lose: 3.55 },
    returnRate: 94.78,
  },
  {
    bookmaker: "最小值",
    initial: { win: 1.96, draw: 3.25, lose: 2.82 },
    current: { win: 1.99, draw: 3.1, lose: 2.82 },
    returnRate: 86.92,
  },
  {
    bookmaker: "平均值",
    initial: { win: 2.07, draw: 3.49, lose: 3.05 },
    current: { win: 2.17, draw: 3.29, lose: 3.12 },
    returnRate: 91.96,
  },
  {
    bookmaker: "365*",
    initial: { win: 2.05, draw: 3.6, lose: 3.05 },
    current: { win: 2.1, draw: 3.25, lose: 3.4 },
    returnRate: 92.76,
  },
  {
    bookmaker: "威廉**",
    initial: { win: 2.1, draw: 3.25, lose: 3.0 },
    current: { win: 2.15, draw: 3.1, lose: 2.9 },
    returnRate: 88.3,
  },
  {
    bookmaker: "立*",
    initial: { win: 2.05, draw: 3.4, lose: 2.9 },
    current: { win: 2.15, draw: 3.2, lose: 3.0 },
    returnRate: 90.01,
  },
  {
    bookmaker: "皇*",
    initial: { win: 2.13, draw: 3.55, lose: 3.05 },
    current: { win: 2.19, draw: 3.35, lose: 3.05 },
    returnRate: 92.34,
  },
  {
    bookmaker: "香*",
    initial: { win: 1.99, draw: 3.35, lose: 3.0 },
    current: { win: 1.99, draw: 3.3, lose: 3.05 },
    returnRate: 88.23,
  },
  {
    bookmaker: "韦*",
    initial: { win: 2.1, draw: 3.5, lose: 3.1 },
    current: { win: 2.15, draw: 3.4, lose: 3.2 },
    returnRate: 93.31,
  },
  {
    bookmaker: "澳*",
    initial: { win: 2.0, draw: 3.38, lose: 2.82 },
    current: { win: 2.0, draw: 3.38, lose: 2.82 },
    returnRate: 86.92,
  },
]);

// 亚洲盘口数据（模拟）
const asianOdds = ref([
  {
    bookmaker: "365*",
    initial: { home: 0.95, handicap: -0.5, away: 0.9 },
    current: { home: 0.98, handicap: -0.5, away: 0.87 },
  },
  {
    bookmaker: "皇冠*",
    initial: { home: 0.93, handicap: -0.5, away: 0.92 },
    current: { home: 0.93, handicap: -0.25, away: 0.92 },
  },
  {
    bookmaker: "明陞*",
    initial: { home: 0.91, handicap: -0.5, away: 0.94 },
    current: { home: 0.89, handicap: -0.5, away: 0.96 },
  },
  {
    bookmaker: "12bet*",
    initial: { home: 0.92, handicap: -0.5, away: 0.93 },
    current: { home: 0.95, handicap: -0.5, away: 0.9 },
  },
  {
    bookmaker: "立博*",
    initial: { home: 0.9, handicap: -0.5, away: 0.95 },
    current: { home: 0.93, handicap: -0.5, away: 0.92 },
  },
]);

// 大小球数据（模拟）
const overUnderOdds = ref([
  {
    bookmaker: "365*",
    initial: { over: 1.83, line: 2.5, under: 2.03 },
    current: { over: 1.9, line: 2.5, under: 1.95 },
  },
  {
    bookmaker: "威廉*",
    initial: { over: 1.78, line: 2.5, under: 2.07 },
    current: { over: 1.85, line: 2.5, under: 2.0 },
  },
  {
    bookmaker: "立博*",
    initial: { over: 1.8, line: 2.5, under: 2.05 },
    current: { over: 1.88, line: 2.5, under: 1.97 },
  },
  {
    bookmaker: "皇冠*",
    initial: { over: 1.85, line: 2.5, under: 2.0 },
    current: { over: 1.92, line: 2.5, under: 1.93 },
  },
  {
    bookmaker: "明陞*",
    initial: { over: 1.81, line: 2.5, under: 2.04 },
    current: { over: 1.89, line: 2.5, under: 1.96 },
  },
]);

// 展开/收起状态
const expandedSections = reactive({
  homeHistory: true,
  awayHistory: true,
  h2h: true,
  schedule: true,
});

// 近期状态
const recentForm = ref({
  home: ["win", "draw", "win", "lose", "draw", "win"],
  away: ["win", "win", "draw", "win", "lose", "win"],
  homeSummary: "3胜2平1负",
  awaySummary: "4胜1平1负",
});

// 近期比赛
const recentMatches = ref({
  home: [
    { id: 1, date: "2024-03-10", opponent: "vs 切尔西", score: "2-1", result: "win", resultText: "胜" },
    { id: 2, date: "2024-03-03", opponent: "vs 阿森纳", score: "1-1", result: "draw", resultText: "平" },
    { id: 3, date: "2024-02-25", opponent: "vs 埃弗顿", score: "3-0", result: "win", resultText: "胜" },
    { id: 4, date: "2024-02-18", opponent: "vs 热刺", score: "0-2", result: "lose", resultText: "负" },
    { id: 5, date: "2024-02-11", opponent: "vs 纽卡斯尔", score: "2-2", result: "draw", resultText: "平" },
    { id: 6, date: "2024-02-04", opponent: "vs 布莱顿", score: "1-0", result: "win", resultText: "胜" },
  ],
  away: [
    { id: 1, date: "2024-03-10", opponent: "vs 曼城", score: "3-1", result: "win", resultText: "胜" },
    { id: 2, date: "2024-03-03", opponent: "vs 维拉", score: "2-1", result: "win", resultText: "胜" },
    { id: 3, date: "2024-02-25", opponent: "vs 西汉姆", score: "1-1", result: "draw", resultText: "平" },
    { id: 4, date: "2024-02-18", opponent: "vs 伯恩利", score: "3-0", result: "win", resultText: "胜" },
    { id: 5, date: "2024-02-11", opponent: "vs 布伦特福德", score: "2-3", result: "lose", resultText: "负" },
    { id: 6, date: "2024-02-04", opponent: "vs 谢菲尔德", score: "2-0", result: "win", resultText: "胜" },
  ],
});

// 交战历史
const h2hStats = ref({
  homeWins: 45,
  draws: 20,
  awayWins: 35,
});

const h2hMatches = ref([
  {
    id: 1,
    date: "2023-12-17",
    competition: "英超",
    homeTeam: "利物浦",
    awayTeam: "曼联",
    score: "2-0",
    resultClass: "away-win",
  },
  {
    id: 2,
    date: "2023-09-03",
    competition: "英超",
    homeTeam: "曼联",
    awayTeam: "利物浦",
    score: "1-1",
    resultClass: "draw",
  },
  {
    id: 3,
    date: "2023-03-05",
    competition: "英超",
    homeTeam: "利物浦",
    awayTeam: "曼联",
    score: "7-0",
    resultClass: "away-win",
  },
  {
    id: 4,
    date: "2022-08-22",
    competition: "英超",
    homeTeam: "曼联",
    awayTeam: "利物浦",
    score: "1-2",
    resultClass: "away-win",
  },
]);

// 未来赛程
const futureSchedule = ref({
  home: [
    { id: 1, date: "2024-03-24", opponent: "切尔西", competition: "英超" },
    { id: 2, date: "2024-03-31", opponent: "阿森纳", competition: "英超" },
    { id: 3, date: "2024-04-07", opponent: "布莱顿", competition: "英超" },
  ],
  away: [
    { id: 1, date: "2024-03-24", opponent: "热刺", competition: "英超" },
    { id: 2, date: "2024-04-02", opponent: "纽卡斯尔", competition: "英超" },
    { id: 3, date: "2024-04-09", opponent: "埃弗顿", competition: "英超" },
  ],
});

// 切换一级 Tab
function switchPrimaryTab(tabId) {
  activePrimaryTab.value = tabId;
  // 切换到第一个二级 Tab
  const tabs = secondaryTabsMap[tabId];
  if (tabs && tabs.length > 0) {
    activeSecondaryTab.value = tabs[0].id;
  }
}

// 切换二级 Tab
function switchSecondaryTab(tabId) {
  activeSecondaryTab.value = tabId;
}

// 切换区块展开/收起
function toggleSection(section) {
  expandedSections[section] = !expandedSections[section];
}

// 格式化数字为2位小数
function formatNumber(value) {
  return Number(value).toFixed(2);
}

// 获取变化样式类
function getChangeClass(oldVal, newVal) {
  if (oldVal === newVal) return "";
  return newVal > oldVal ? "value-up" : "value-down";
}

// 获取盘口变化样式类
function getHandicapChangeClass(oldVal, newVal) {
  if (oldVal === newVal) return "";
  return newVal > oldVal ? "handicap-up" : "handicap-down";
}
</script>

<style lang="scss" scoped>
.indices-page {
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
  min-height: 100vh;
  padding-bottom: 20rpx;
}

// 比赛头部信息
.match-header {
  background: #ffffff;
  margin: 20rpx 24rpx;
  padding: 16rpx;
  border-radius: 8rpx;
  border: 1px solid #e5e7eb;
}

.league-badge {
  display: inline-block;
  background: #0d9488;
  color: #ffffff;
  font-size: 22rpx;
  padding: 4rpx 12rpx;
  border-radius: 4rpx;
}

.match-teams {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16rpx;
  margin: 16rpx 0;

  .team-name {
    font-size: 32rpx;
    font-weight: 500;
    color: #111827;
  }

  .vs {
    font-size: 24rpx;
    color: #6b7280;
    font-weight: normal;
  }
}

.match-meta {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12rpx;
  margin-top: 12rpx;

  .date,
  .time {
    font-size: 24rpx;
    color: #6b7280;
  }

  .status-badge {
    padding: 4rpx 12rpx;
    border-radius: 4rpx;
    font-size: 20rpx;

    &.pending {
      background: #10b981;
      color: #ffffff;
    }
  }
}

.update-info {
  text-align: center;
  font-size: 20rpx;
  color: #9ca3af;
  margin-top: 12rpx;
}

// 一级 Tab
.primary-tabs {
  display: flex;
  background: #ffffff;
  margin: 0 24rpx;
  border-radius: 6rpx;
  box-shadow: none;
  border: 1px solid #e5e7eb;
}

.primary-tab {
  flex: 1;
  padding: 10rpx;
  text-align: center;
  border-radius: 4rpx;
  transition: all 0.3s;

  .tab-text {
    font-size: 26rpx;
    color: #6b7280;
    font-weight: normal;
  }

  &.active {
    background: #0d9488;

    .tab-text {
      color: #ffffff;
      font-weight: normal;
    }
  }
}

// 二级 Tab
.secondary-tabs {
  margin: 16rpx 24rpx 0;
  overflow: hidden;
}

.tabs-scroll {
  white-space: nowrap;
}

.secondary-tab {
  display: inline-block;
  padding: 6rpx 16rpx;
  margin-right: 12rpx;
  border-radius: 6rpx;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  transition: all 0.3s;

  .tab-text {
    font-size: 24rpx;
    color: #6b7280;
    font-weight: normal;
  }

  &.active {
    background: #0d9488;
    border-color: #0d9488;

    .tab-text {
      color: #ffffff;
      font-weight: normal;
    }
  }
}

// 内容区域
.content-area {
  height: calc(100vh - 400rpx);
  margin-top: 20rpx;
}

.content-section {
  padding: 0 24rpx 20rpx;
}

// 统计条
.statistics-bar {
  display: flex;
  justify-content: space-around;
  background: #ffffff;
  padding: 12rpx;
  border-radius: 6rpx;
  margin-bottom: 16rpx;
  border: 1px solid #e5e7eb;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;

  .icon {
    font-size: 32rpx;
  }

  .text {
    font-size: 22rpx;
    color: #6b7280;
  }

  &.stat-up .text {
    color: #ef4444;
  }

  &.stat-down .text {
    color: #10b981;
  }
}

// 紧凑表格布局
.compact-table {
  background: #ffffff;
  border-radius: 6rpx;
  overflow: hidden;
  border: 1px solid #e5e7eb;
}

.table-header {
  display: flex;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-size: 22rpx;
  color: #6b7280;
  font-weight: normal;
}

.header-company {
  width: 100rpx;
  flex-shrink: 0;
  padding: 10rpx 16rpx;
  display: flex;
  align-items: center;
}

.header-data {
  flex: 1;
  display: flex;
  padding: 10rpx 16rpx 10rpx 0;
  align-items: center;
}

// 每个公司的数据组（包含初盘和即时两行）
.table-group {
  display: flex;

  &.row-even {
    background: #f9fafb;
  }

  &:last-child {
    border-bottom: none;
  }
}

// 公司名称单元格（垂直居中两行）
.company-cell {
  width: 100rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 16rpx;
}

.company-name {
  font-size: 22rpx;
  color: #111827;
  font-weight: normal;
}

// 数据行容器
.data-rows {
  flex: 1;
  display: flex;
  flex-direction: column;
}

// 单行数据（初盘或即时）
.table-row {
  display: flex;
  padding: 6rpx 16rpx 6rpx 0;
  align-items: center;
  min-height: 36rpx;
}

.col-label {
  width: 36rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.label-text {
  font-size: 22rpx;
  font-weight: 500;

  &.initial {
    color: #9ca3af;
  }

  &.current {
    color: #2563eb;
  }
}

.col-odds {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
}

.col-return {
  width: 90rpx;
  text-align: center;
  flex-shrink: 0;
}

.odds-value {
  font-size: 22rpx;
  color: #111827;
  font-weight: normal;
  position: relative;
  text-align: center;
  display: inline-block;
  min-width: 70rpx;

  &.value-up {
    color: #ef4444;
  }

  &.value-down {
    color: #10b981;
  }
}

.arrow-tiny {
  font-size: 20rpx;
  position: absolute;
  right: -4rpx;
  top: 9rpx;
  transform: translateY(-42%);
}

.return-value {
  font-size: 22rpx;
  color: #6b7280;
  font-weight: normal;
  text-align: center;
  display: block;
}

.odds-row {
  display: flex;
  justify-content: space-between;
  gap: 16rpx;

  &.asian-handicap {
    flex-direction: column;
  }
}

.odds-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8rpx;

  .label {
    font-size: 22rpx;
    color: #6b7280;
    text-align: center;
  }
}

.odds-values,
.handicap-values,
.ou-values {
  display: flex;
  justify-content: space-around;
  gap: 8rpx;

  .value {
    flex: 1;
    text-align: right;
    font-size: 22rpx;
    font-weight: normal;
    color: #111827;
    padding: 8rpx 18rpx 8rpx 8rpx;
    background: #f9fafb;
    border-radius: 4rpx;
    position: relative;
    display: block;
    min-width: 70rpx;

    &.value-up {
      color: #ef4444;
    }

    &.value-down {
      color: #10b981;
    }

    .arrow,
    .arrow-small {
      font-size: 14rpx;
      position: absolute;
      right: 2rpx;
      top: 50%;
      transform: translateY(-50%);
    }
  }

  .handicap,
  .line {
    flex: 0.8;
    text-align: center;
    font-size: 22rpx;
    font-weight: normal;
    color: #0d9488;
    padding: 8rpx;
    background: #f0fdfa;
    border-radius: 4rpx;
    min-width: 60rpx;

    &.handicap-up {
      color: #ef4444;
    }

    &.handicap-down {
      color: #10b981;
    }
  }
}

.return-rate {
  text-align: center;
  font-size: 20rpx;
  color: #9ca3af;
  margin-top: 12rpx;
}

// 数据区块
.section-block {
  background: #ffffff;
  border-radius: 6rpx;
  margin-bottom: 16rpx;
  overflow: hidden;
  border: 1px solid #e5e7eb;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14rpx 16rpx;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.section-title {
  font-size: 28rpx;
  font-weight: 500;
  color: #111827;
}

.toggle-icon {
  font-size: 24rpx;
  color: #6b7280;
}

.section-content {
  padding: 20rpx;
}

// 球队表单状态
.team-form-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 16rpx;
}

.form-indicator {
  display: flex;
  justify-content: center;
  gap: 8rpx;
}

.form-dot {
  width: 24rpx;
  height: 24rpx;
  border-radius: 50%;

  &.win {
    background: #10b981;
  }

  &.draw {
    background: #f59e0b;
  }

  &.lose {
    background: #ef4444;
  }
}

.stat-summary {
  font-size: 22rpx;
  color: #6b7280;
  text-align: center;
}

// 比赛列表
.match-list {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.match-item-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10rpx 12rpx;
  background: #f9fafb;
  border-radius: 0;
  border-bottom: 1px solid #e5e7eb;
  gap: 8rpx;

  &:last-child {
    border-bottom: none;
  }

  .match-date {
    font-size: 20rpx;
    color: #6b7280;
    flex-shrink: 0;
    width: 90rpx;
  }

  .opponent {
    flex: 1;
    font-size: 22rpx;
    color: #111827;
  }

  .score {
    font-size: 22rpx;
    color: #111827;
    font-weight: 500;
    width: 50rpx;
    text-align: center;
  }

  .result-badge {
    padding: 4rpx 10rpx;
    border-radius: 4rpx;
    font-size: 20rpx;
    flex-shrink: 0;
    width: 40rpx;
    text-align: center;

    &.win {
      background: #d1fae5;
      color: #10b981;
    }

    &.draw {
      background: #fef3c7;
      color: #f59e0b;
    }

    &.lose {
      background: #fee2e2;
      color: #ef4444;
    }
  }
}

// 交战历史
.h2h-summary {
  display: flex;
  justify-content: space-around;
  margin-bottom: 20rpx;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;

  .count {
    font-size: 36rpx;
    font-weight: 600;

    &.win {
      color: #10b981;
    }

    &.draw {
      color: #f59e0b;
    }

    &.lose {
      color: #ef4444;
    }
  }

  .label {
    font-size: 22rpx;
    color: #6b7280;
  }
}

.h2h-match-item {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
  padding: 12rpx;
  background: #f9fafb;
  border-radius: 0;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 0;

  &:last-child {
    border-bottom: none;
  }

  .h2h-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4rpx;
  }

  .match-date {
    font-size: 20rpx;
    color: #6b7280;
  }

  .competition {
    font-size: 20rpx;
    color: #0d9488;
  }

  .match-result {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .team {
      flex: 1;
      font-size: 22rpx;
      color: #111827;

      &:last-child {
        text-align: right;
      }
    }

    .score {
      font-size: 24rpx;
      font-weight: 600;
      padding: 0 16rpx;

      &.away-win {
        color: #ef4444;
      }

      &.draw {
        color: #f59e0b;
      }
    }
  }
}

// 未来赛程
.future-schedule-wrapper {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.team-schedule-section {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.team-schedule-title {
  font-size: 24rpx;
  font-weight: 500;
  color: #0d9488;
  padding-bottom: 8rpx;
  border-bottom: 2px solid #e5e7eb;
}

.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.schedule-item-inline {
  padding: 10rpx 12rpx;
  background: #f9fafb;
  border-radius: 0;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8rpx;

  &:last-child {
    border-bottom: none;
  }

  .match-date {
    font-size: 20rpx;
    color: #6b7280;
    flex-shrink: 0;
    width: 90rpx;
  }

  .opponent {
    flex: 1;
    font-size: 22rpx;
    color: #111827;
    font-weight: normal;
  }

  .competition {
    font-size: 20rpx;
    color: #0d9488;
    flex-shrink: 0;
  }
}

// 占位符
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120rpx 40rpx;
  background: #ffffff;
  border-radius: 8rpx;
  border: 1px solid #e5e7eb;

  .placeholder-icon {
    font-size: 80rpx;
    margin-bottom: 20rpx;
  }

  .placeholder-text {
    font-size: 28rpx;
    font-weight: 500;
    color: #111827;
    margin-bottom: 12rpx;
  }

  .placeholder-desc {
    font-size: 24rpx;
    color: #9ca3af;
  }
}
</style>
