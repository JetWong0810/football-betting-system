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
      <!-- 加载/错误状态 -->
      <view v-if="loading" class="loading-state">
        <text class="loading-text">加载中...</text>
      </view>
      <view v-else-if="errorMsg" class="error-state">
        <text class="error-text">{{ errorMsg }}</text>
        <view class="retry-btn" @tap="loadIndices">
          <text>重试</text>
        </view>
      </view>

      <!-- 指数 - 欧指 -->
      <view v-if="!loading && activePrimaryTab === 'indices' && activeSecondaryTab === 'european'" class="content-section">
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
              <view class="company-cell" @tap="item.cid && toggleHistory('european', item.cid, index)">
                <text class="company-name">{{ item.bookmaker }}</text>
                <text v-if="item.cid" class="expand-arrow" :class="{ expanded: expandedHistory[`euro_${index}`] }">▶</text>
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
      <view v-if="!loading && activePrimaryTab === 'indices' && activeSecondaryTab === 'asian'" class="content-section">
        <view class="compact-table">
          <view class="table-header">
            <view class="header-company">公司</view>
            <view class="header-data asian-header">
              <view class="col-label"></view>
              <view class="col-odds">主胜</view>
              <view class="col-handicap">盘</view>
              <view class="col-odds">客胜</view>
            </view>
          </view>
          <template v-for="(item, index) in asianOdds" :key="item.bookmaker">
            <!-- 每个公司的数据组 -->
            <view class="table-group" :class="{ 'row-even': index % 2 === 1 }">
              <view class="company-cell" @tap="item.cid && toggleHistory('asian', item.cid, index)">
                <text class="company-name">{{ item.bookmaker }}</text>
                <text v-if="item.cid" class="expand-arrow" :class="{ expanded: expandedHistory[`asian_${index}`] }">▶</text>
              </view>
              <view class="data-rows">
                <!-- 初盘行 -->
                <view class="table-row">
                  <view class="col-label">
                    <text class="label-text initial">初</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value">{{ formatNumber(item.initial.home) }}</text>
                  </view>
                  <view class="col-handicap">
                    <text class="handicap-value">{{ formatNumber(item.initial.handicap) }}</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value">{{ formatNumber(item.initial.away) }}</text>
                  </view>
                </view>
                <!-- 即时行 -->
                <view class="table-row">
                  <view class="col-label">
                    <text class="label-text current">即</text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value" :class="getChangeClass(item.initial.home, item.current.home)">
                      {{ formatNumber(item.current.home) }}
                      <text class="arrow-tiny" v-if="item.initial.home !== item.current.home">
                        {{ item.current.home > item.initial.home ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                  <view class="col-handicap">
                    <text class="handicap-value" :class="getHandicapChangeClass(item.initial.handicap, item.current.handicap)">
                      {{ formatNumber(item.current.handicap) }}
                    </text>
                  </view>
                  <view class="col-odds">
                    <text class="odds-value" :class="getChangeClass(item.initial.away, item.current.away)">
                      {{ formatNumber(item.current.away) }}
                      <text class="arrow-tiny" v-if="item.initial.away !== item.current.away">
                        {{ item.current.away > item.initial.away ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                </view>
              </view>
            </view>
          </template>
        </view>
      </view>

      <!-- 指数 - 大小 -->
      <view v-if="!loading && activePrimaryTab === 'indices' && activeSecondaryTab === 'overunder'" class="content-section">
        <view class="compact-table-ou">
          <!-- 表头 -->
          <view class="table-header-ou">
            <view class="col-company">公司</view>
            <view class="col-label"></view>
            <view class="col-over">大球</view>
            <view class="col-line">盘口</view>
            <view class="col-under">小球</view>
          </view>

          <!-- 数据行 -->
          <template v-for="(item, index) in overUnderOdds" :key="item.bookmaker">
            <view class="table-group-ou" :class="{ 'row-even': index % 2 === 0 }">
              <!-- 公司名称 -->
              <view class="company-cell-ou" @tap="item.cid && toggleHistory('overunder', item.cid, index)">
                <text class="company-name">{{ item.bookmaker }}</text>
                <text v-if="item.cid" class="expand-arrow" :class="{ expanded: expandedHistory[`ou_${index}`] }">▶</text>
              </view>

              <!-- 数据行 -->
              <view class="data-rows-ou">
                <!-- 初盘 -->
                <view class="table-row-ou">
                  <view class="col-label">
                    <text class="label-text initial">初</text>
                  </view>
                  <view class="col-over">
                    <text class="odds-value">{{ formatNumber(item.initial.over) }}</text>
                  </view>
                  <view class="col-line">
                    <text class="line-value">{{ formatNumber(item.initial.line) }}</text>
                  </view>
                  <view class="col-under">
                    <text class="odds-value">{{ formatNumber(item.initial.under) }}</text>
                  </view>
                </view>

                <!-- 即时 -->
                <view class="table-row-ou">
                  <view class="col-label">
                    <text class="label-text instant">即</text>
                  </view>
                  <view class="col-over">
                    <text class="odds-value" :class="getChangeClass(item.initial.over, item.current.over)">
                      {{ formatNumber(item.current.over) }}
                      <text class="arrow-icon" v-if="item.initial.over !== item.current.over">
                        {{ item.current.over > item.initial.over ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                  <view class="col-line">
                    <text class="line-value" :class="getLineChangeClass(item.initial.line, item.current.line)">
                      {{ formatNumber(item.current.line) }}
                    </text>
                  </view>
                  <view class="col-under">
                    <text class="odds-value" :class="getChangeClass(item.initial.under, item.current.under)">
                      {{ formatNumber(item.current.under) }}
                      <text class="arrow-icon" v-if="item.initial.under !== item.current.under">
                        {{ item.current.under > item.initial.under ? "↑" : "↓" }}
                      </text>
                    </text>
                  </view>
                </view>
              </view>
            </view>
          </template>
        </view>
      </view>

      <!-- 数据 - 基本面 -->
      <view v-if="activePrimaryTab === 'data' && activeSecondaryTab === 'fundamentals'" class="content-section">
        <!-- 1. 历史交锋 -->
        <view v-if="h2hMatches.length" class="section-block">
          <view class="section-header h2h-section-header" @tap="toggleSection('h2h')">
            <text class="section-title">历史交锋</text>
          </view>
          <view v-if="expandedSections.h2h" class="section-content h2h-content">
            <view class="h2h-table">
              <view class="h2h-table-header">
                <view class="col-event">赛事</view>
                <view class="col-teams">主队　比分　客队</view>
                <view class="col-asian">盘口</view>
                <view class="col-ou">大小</view>
              </view>
              <view v-for="(match, index) in h2hMatches" :key="match.id" class="h2h-table-row" :class="{ 'row-alt': index % 2 === 0 }">
                <view class="col-event">
                  <text class="event-date">{{ match.dateShort }}</text>
                  <text class="event-name">{{ match.competition }}</text>
                </view>
                <view class="col-teams">
                  <view class="team-left">
                    <text class="team-name" :class="getTeamColorClass(match, 'home')">{{ match.homeTeam }}</text>
                  </view>
                  <view class="score-wrapper">
                    <text class="match-score">{{ match.score }}</text>
                    <text class="halftime-score">{{ match.halftimeScore }}</text>
                  </view>
                  <view class="team-right">
                    <text class="team-name" :class="getTeamColorClass(match, 'away')">{{ match.awayTeam }}</text>
                  </view>
                </view>
                <view class="col-asian">
                  <text class="data-value" :class="match.asianClass">{{ match.asian }}</text>
                  <text class="data-label" :class="match.asianClass">{{ match.asianLabel }}</text>
                </view>
                <view class="col-ou">
                  <text class="data-label" :class="match.ouClass">{{ match.ouLabel }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 2. 主队近期战绩 -->
        <view class="section-block">
          <view class="section-header h2h-section-header" @tap="toggleSection('homeHistory')">
            <text class="section-title">{{ matchInfo.homeTeam }} 近期战绩</text>
            <view class="h2h-header-right">
              <view class="h2h-filters">
                <view class="filter-item" :class="{ active: homeFilters.homeOnly }" @tap.stop="toggleHomeFilter('homeOnly')">
                  <text>同主客</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.sameCompetition }" @tap.stop="toggleHomeFilter('sameCompetition')">
                  <text>同赛事</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.matchCount === 10 }" @tap.stop="setHomeMatchCount(10)">
                  <text>10场</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.matchCount === 15 }" @tap.stop="setHomeMatchCount(15)">
                  <text>15场</text>
                </view>
              </view>
            </view>
          </view>
          <view v-if="expandedSections.homeHistory" class="section-content h2h-content">
            <view class="h2h-table">
              <!-- 表头 -->
              <view class="h2h-table-header">
                <view class="col-event">赛事</view>
                <view class="col-teams">主队　比分　客队</view>
                <view class="col-asian">亚指</view>
                <view class="col-ou">大小</view>
              </view>

              <!-- 数据行 -->
              <view v-for="(match, index) in filteredHomeRecent" :key="match.id" class="h2h-table-row" :class="{ 'row-alt': index % 2 === 0 }">
                <view class="col-event">
                  <text class="event-date">{{ match.dateShort }}</text>
                  <text class="event-name">{{ match.competition }}</text>
                </view>
                <view class="col-teams">
                  <view class="team-left">
                    <text class="team-name" :class="getTeamColorClass(match, 'home')">{{ match.homeTeam }}</text>
                  </view>
                  <view class="score-wrapper">
                    <text class="match-score">{{ match.score }}</text>
                    <text class="halftime-score">{{ match.halftimeScore }}</text>
                  </view>
                  <view class="team-right">
                    <text class="team-name" :class="getTeamColorClass(match, 'away')">{{ match.awayTeam }}</text>
                  </view>
                </view>
                <view class="col-asian">
                  <text class="data-value" :class="match.asianClass">{{ match.asian }}</text>
                  <text class="data-label" :class="match.asianClass">{{ match.asianLabel }}</text>
                </view>
                <view class="col-ou">
                  <text class="data-label" :class="match.ouClass">{{ match.ouLabel }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 3. 客队近期战绩 -->
        <view class="section-block">
          <view class="section-header h2h-section-header" @tap="toggleSection('awayHistory')">
            <text class="section-title">{{ matchInfo.awayTeam }} 近期战绩</text>
            <view class="h2h-header-right">
              <view class="h2h-filters">
                <view class="filter-item" :class="{ active: awayFilters.awayOnly }" @tap.stop="toggleAwayFilter('awayOnly')">
                  <text>同主客</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.sameCompetition }" @tap.stop="toggleAwayFilter('sameCompetition')">
                  <text>同赛事</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.matchCount === 10 }" @tap.stop="setAwayMatchCount(10)">
                  <text>10场</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.matchCount === 15 }" @tap.stop="setAwayMatchCount(15)">
                  <text>15场</text>
                </view>
              </view>
            </view>
          </view>
          <view v-if="expandedSections.awayHistory" class="section-content h2h-content">
            <view class="h2h-table">
              <!-- 表头 -->
              <view class="h2h-table-header">
                <view class="col-event">赛事</view>
                <view class="col-teams">主队　比分　客队</view>
                <view class="col-asian">亚指</view>
                <view class="col-ou">大小</view>
              </view>

              <!-- 数据行 -->
              <view v-for="(match, index) in filteredAwayRecent" :key="match.id" class="h2h-table-row" :class="{ 'row-alt': index % 2 === 0 }">
                <view class="col-event">
                  <text class="event-date">{{ match.dateShort }}</text>
                  <text class="event-name">{{ match.competition }}</text>
                </view>
                <view class="col-teams">
                  <view class="team-left">
                    <text class="team-name" :class="getTeamColorClass(match, 'home')">{{ match.homeTeam }}</text>
                  </view>
                  <view class="score-wrapper">
                    <text class="match-score">{{ match.score }}</text>
                    <text class="halftime-score">{{ match.halftimeScore }}</text>
                  </view>
                  <view class="team-right">
                    <text class="team-name" :class="getTeamColorClass(match, 'away')">{{ match.awayTeam }}</text>
                  </view>
                </view>
                <view class="col-asian">
                  <text class="data-value" :class="match.asianClass">{{ match.asian }}</text>
                  <text class="data-label" :class="match.asianClass">{{ match.asianLabel }}</text>
                </view>
                <view class="col-ou">
                  <text class="data-label" :class="match.ouClass">{{ match.ouLabel }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 4. 未来赛程数据 -->
        <view class="section-block">
          <view class="section-header h2h-section-header">
            <text class="section-title">未来赛程</text>
          </view>
          <view class="section-content">
            <view class="future-schedule-wrapper">
              <!-- 主队赛程 -->
              <view class="team-schedule-section">
                <text class="team-schedule-title">{{ matchInfo.homeTeam }}</text>
                <view class="schedule-table">
                  <view class="schedule-header">
                    <view class="schedule-col-time">时间</view>
                    <view class="schedule-col-event">赛事</view>
                    <view class="schedule-col-match">对阵</view>
                    <view class="schedule-col-interval">间隔</view>
                  </view>
                  <view v-for="match in futureSchedule.home.slice(0, 3)" :key="match.id" class="schedule-row">
                    <view class="schedule-col-time">
                      <text>{{ match.dateShort }}</text>
                    </view>
                    <view class="schedule-col-event">
                      <text>{{ match.competition }}</text>
                    </view>
                    <view class="schedule-col-match">
                      <text>{{ match.matchup }}</text>
                    </view>
                    <view class="schedule-col-interval">
                      <text>{{ match.interval }}</text>
                    </view>
                  </view>
                </view>
              </view>

              <!-- 客队赛程 -->
              <view class="team-schedule-section">
                <text class="team-schedule-title">{{ matchInfo.awayTeam }}</text>
                <view class="schedule-table">
                  <view class="schedule-header">
                    <view class="schedule-col-time">时间</view>
                    <view class="schedule-col-event">赛事</view>
                    <view class="schedule-col-match">对阵</view>
                    <view class="schedule-col-interval">间隔</view>
                  </view>
                  <view v-for="match in futureSchedule.away.slice(0, 3)" :key="match.id" class="schedule-row">
                    <view class="schedule-col-time">
                      <text>{{ match.dateShort }}</text>
                    </view>
                    <view class="schedule-col-event">
                      <text>{{ match.competition }}</text>
                    </view>
                    <view class="schedule-col-match">
                      <text>{{ match.matchup }}</text>
                    </view>
                    <view class="schedule-col-interval">
                      <text>{{ match.interval }}</text>
                    </view>
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

    <!-- 赔率变动弹窗 -->
    <view v-if="historyModal.show" class="modal-mask" @tap="closeHistoryModal">
      <view class="modal-content" @tap.stop>
        <view class="modal-header">
          <text class="modal-title">{{ historyModal.companyName }} 赔率变动</text>
          <text class="modal-close" @tap="closeHistoryModal">✕</text>
        </view>
        <view v-if="historyModal.loading" class="modal-loading">
          <text>加载中...</text>
        </view>
        <scroll-view v-else-if="historyModal.data?.length" scroll-y class="modal-body">
          <view class="history-header">
            <text class="h-col-time">时间</text>
            <text class="h-col" v-for="col in historyModal.columns" :key="col">{{ col }}</text>
          </view>
          <view v-for="(h, hi) in historyModal.data" :key="hi" class="history-row" :class="{ 'h-row-alt': hi % 2 === 0 }">
            <text class="h-col-time">{{ formatTime(h.time) }}</text>
            <text class="h-col" v-for="(col, ci) in historyModal.fields" :key="ci">{{ formatHistoryValue(h, col) }}</text>
          </view>
        </scroll-view>
        <view v-else class="modal-empty">
          <text>暂无变动记录</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, reactive } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import dayjs from "dayjs";
import { request } from "@/utils/http";

// 比赛信息
const matchInfo = ref({
  homeTeam: "",
  awayTeam: "",
  league: "",
  date: "",
  time: "",
  status: "",
  statusClass: "pending",
});

const loading = ref(false);
const errorMsg = ref("");
const matchId = ref("");
const fid = ref("");

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

// 指数数据 (从API加载)
const europeanOdds = ref([]);
const asianOdds = ref([]);
const overUnderOdds = ref([]);

// 加载指数数据
async function loadIndices() {
  if (!matchId.value) return;
  loading.value = true;
  errorMsg.value = "";
  try {
    const res = await request({ url: `/api/matches/${matchId.value}/indices` });
    const indices = res.indices || {};

    fid.value = res.fid || "";
    europeanOdds.value = indices.european || [];
    asianOdds.value = indices.asian || [];
    overUnderOdds.value = indices.overUnder || [];

    // 更新比赛信息
    if (res.match) {
      matchInfo.value = {
        homeTeam: res.match.homeTeam?.name || "",
        awayTeam: res.match.awayTeam?.name || "",
        league: res.match.league || "",
        date: res.match.matchDate || "",
        time: res.match.matchTime || "",
        status: { not_started: "未开赛", finished: "已结束", cancelled: "取消" }[res.match.status] || "未开赛",
        statusClass: res.match.status === "finished" ? "finished" : "pending",
      };
    }
  } catch (e) {
    errorMsg.value = e.message || "加载失败";
    console.error("加载指数数据失败:", e);
  } finally {
    loading.value = false;
  }
}

onLoad((query) => {
  matchId.value = query.matchId || "";
  loadIndices();
});

// 赔率变动弹窗
const expandedHistory = reactive({});
const historyModal = reactive({
  show: false,
  loading: false,
  companyName: "",
  type: "",
  columns: [],
  fields: [],
  data: [],
});

const HISTORY_CONFIG = {
  european: { columns: ["主胜", "平局", "客胜", "返还"], fields: ["win", "draw", "lose", "returnRate"] },
  asian: { columns: ["主队", "盘口", "客队"], fields: ["home", "handicapText", "away"] },
  overunder: { columns: ["大球", "盘口", "小球"], fields: ["over", "line", "under"] },
};

async function toggleHistory(type, cid, index) {
  const keyMap = { european: "euro", asian: "asian", overunder: "ou" };
  const key = `${keyMap[type]}_${index}`;
  expandedHistory[key] = !expandedHistory[key];

  // Find company name
  const lists = { european: europeanOdds, asian: asianOdds, overunder: overUnderOdds };
  const item = lists[type]?.value?.[index];
  const config = HISTORY_CONFIG[type];

  historyModal.show = true;
  historyModal.loading = true;
  historyModal.companyName = item?.bookmaker || "";
  historyModal.type = type;
  historyModal.columns = config.columns;
  historyModal.fields = config.fields;
  historyModal.data = [];

  try {
    const res = await request({
      url: `/api/odds/history?fid=${fid.value}&cid=${cid}&type=${type}&matchId=${matchId.value}`,
    });
    historyModal.data = res.history || [];
  } catch (e) {
    historyModal.data = [];
    console.error("加载变动历史失败:", e);
  } finally {
    historyModal.loading = false;
  }
}

function closeHistoryModal() {
  historyModal.show = false;
}

function formatHistoryValue(h, field) {
  const val = h[field];
  if (val === null || val === undefined) return "-";
  if (field === "returnRate") return val + "%";
  if (field === "handicapText") return val || formatNumber(h.handicap);
  if (typeof val === "number") return formatNumber(val);
  return val;
}

function formatTime(time) {
  if (!time) return "";
  if (time.length > 16) return time.slice(5, 16);
  return time;
}

// 展开/收起状态
const expandedSections = reactive({
  homeHistory: true,
  awayHistory: true,
  h2h: true,
  schedule: true,
});

// 历史交锋筛选器
const h2hFilters = reactive({
  sameVenue: false, // 同主客
  sameCompetition: false, // 同赛事
  matchCount: 10, // 显示场次
});

// 主队近期战绩筛选器
const homeFilters = reactive({
  homeOnly: false, // 仅主场
  sameCompetition: false, // 同赛事
  matchCount: 10, // 显示场次
});

// 客队近期战绩筛选器
const awayFilters = reactive({
  awayOnly: false, // 仅客场
  sameCompetition: false, // 同赛事
  matchCount: 10, // 显示场次
});

// 近期状态
const recentForm = ref({
  home: [],
  away: [],
  homeSummary: "",
  awaySummary: "",
});

// 近期比赛 (从API加载)
const recentMatches = ref({ home: [], away: [] });

function _findMostCommonComp(list) {
  const counts = {};
  list.forEach((m) => { if (m.competition) counts[m.competition] = (counts[m.competition] || 0) + 1; });
  let max = "", maxCount = 0;
  for (const [k, v] of Object.entries(counts)) {
    if (v > maxCount) { max = k; maxCount = v; }
  }
  return max;
}

const filteredHomeRecent = computed(() => {
  let list = recentMatches.value.home;
  if (homeFilters.homeOnly) {
    const team = matchInfo.value.homeTeam;
    list = list.filter((m) => m.homeTeam && m.homeTeam.includes(team));
  }
  if (homeFilters.sameCompetition) {
    const comp = _findMostCommonComp(list);
    if (comp) list = list.filter((m) => m.competition === comp);
  }
  return list.slice(0, homeFilters.matchCount);
});

const filteredAwayRecent = computed(() => {
  let list = recentMatches.value.away;
  if (awayFilters.awayOnly) {
    const team = matchInfo.value.awayTeam;
    list = list.filter((m) => m.awayTeam && m.awayTeam.includes(team));
  }
  if (awayFilters.sameCompetition) {
    const comp = _findMostCommonComp(list);
    if (comp) list = list.filter((m) => m.competition === comp);
  }
  return list.slice(0, awayFilters.matchCount);
});
const h2hStats = ref({ homeWins: 0, draws: 0, awayWins: 0 });
const h2hMatches = ref([]);
const futureSchedule = ref({ home: [], away: [] });
const dataLoading = ref(false);

async function loadMatchData() {
  if (!matchId.value) return;
  dataLoading.value = true;
  try {
    const res = await request({ url: `/api/matches/${matchId.value}/data` });
    const d = res.data || {};

    // 近期战绩
    recentMatches.value = {
      home: (d.homeRecent || []).map((m, i) => _formatRecent(m, i)),
      away: (d.awayRecent || []).map((m, i) => _formatRecent(m, i)),
    };

    // 交锋历史
    h2hMatches.value = (d.h2h || [])
      .filter((m) => m.halfScore !== "VS")
      .map((m, i) => _formatH2h(m, i));

    // 未来赛程
    futureSchedule.value = {
      home: (d.homeFuture || []).map((m, i) => ({ id: i, competition: m.competition, dateShort: m.date, matchup: m.match, interval: m.interval })),
      away: (d.awayFuture || []).map((m, i) => ({ id: i, competition: m.competition, dateShort: m.date, matchup: m.match, interval: m.interval })),
    };
  } catch (e) {
    console.error("加载基本面数据失败:", e);
  } finally {
    dataLoading.value = false;
  }
}

function _formatRecent(m, i) {
  const matchText = m.match || "";
  const scoreMatch = matchText.match(/(\d+):(\d+)/);
  const homeScore = scoreMatch ? parseInt(scoreMatch[1]) : 0;
  const awayScore = scoreMatch ? parseInt(scoreMatch[2]) : 0;
  const teams = matchText.replace(/\d+:\d+/, "|").split("|");
  return {
    id: i,
    dateShort: m.date,
    competition: m.competition,
    homeTeam: teams[0] || "",
    awayTeam: teams[1] || "",
    score: scoreMatch ? `${homeScore}:${awayScore}` : "-",
    halftimeScore: m.halfScore ? `(${m.halfScore})` : "",
    homeScore,
    awayScore,
    asian: m.handicap || "",
    asianClass: m.asianResult === "赢" ? "win" : m.asianResult === "输" ? "lose" : "draw",
    asianLabel: m.asianResult || "",
    ou: "",
    ouClass: m.ouResult === "大" ? "big" : m.ouResult === "小" ? "small" : "",
    ouLabel: m.ouResult || "",
  };
}

function _formatH2h(m, i) {
  const matchText = m.match || "";
  const scoreMatch = matchText.match(/(\d+):(\d+)/);
  const homeScore = scoreMatch ? parseInt(scoreMatch[1]) : 0;
  const awayScore = scoreMatch ? parseInt(scoreMatch[2]) : 0;
  const teams = matchText.replace(/\[.*?\]/g, "").replace(/\d+:\d+/, "|").split("|");

  return {
    id: i,
    dateShort: m.date,
    competition: m.competition,
    homeTeam: teams[0] || "",
    awayTeam: teams[1] || "",
    score: scoreMatch ? `${homeScore}:${awayScore}` : "-",
    halftimeScore: m.halfScore ? `(${m.halfScore})` : "",
    homeScore,
    awayScore,
    asian: m.handicap || "",
    asianClass: m.asianResult === "赢" ? "win" : m.asianResult === "输" ? "lose" : "draw",
    asianLabel: m.asianResult || "",
    ou: "",
    ouClass: m.ouResult === "大" ? "big" : m.ouResult === "小" ? "small" : "",
    ouLabel: m.ouResult || "",
  };
}

// 获取队伍颜色样式
function getTeamColorClass(match, side) {
  if (match.homeScore === match.awayScore) {
    return "team-draw";
  }
  if (side === "home") {
    return match.homeScore > match.awayScore ? "team-win" : "team-lose";
  } else {
    return match.awayScore > match.homeScore ? "team-win" : "team-lose";
  }
}

// 切换一级 Tab
function switchPrimaryTab(tabId) {
  activePrimaryTab.value = tabId;
  const tabs = secondaryTabsMap[tabId];
  if (tabs && tabs.length > 0) {
    activeSecondaryTab.value = tabs[0].id;
  }
  if (tabId === "data" && recentMatches.value.home.length === 0) {
    loadMatchData();
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

// 获取大小球盘口线变化样式类
function getLineChangeClass(oldVal, newVal) {
  if (oldVal === newVal) return "";
  return newVal > oldVal ? "line-up" : "line-down";
}

// 切换历史交锋筛选器
function toggleH2hFilter(filterType) {
  if (filterType === "sameVenue") {
    h2hFilters.sameVenue = !h2hFilters.sameVenue;
  } else if (filterType === "sameCompetition") {
    h2hFilters.sameCompetition = !h2hFilters.sameCompetition;
  }
  // 这里可以根据筛选条件过滤数据
  console.log("筛选条件:", h2hFilters);
}

// 设置历史交锋场次
function setH2hMatchCount(count) {
  h2hFilters.matchCount = count;
  // 这里可以根据场次限制显示的数据
  console.log("显示场次:", count);
}

// 切换主队筛选器
function toggleHomeFilter(filterType) {
  if (filterType === "homeOnly") {
    homeFilters.homeOnly = !homeFilters.homeOnly;
  } else if (filterType === "sameCompetition") {
    homeFilters.sameCompetition = !homeFilters.sameCompetition;
  }
  console.log("主队筛选条件:", homeFilters);
}

// 设置主队场次
function setHomeMatchCount(count) {
  homeFilters.matchCount = count;
  console.log("主队显示场次:", count);
}

// 切换客队筛选器
function toggleAwayFilter(filterType) {
  if (filterType === "awayOnly") {
    awayFilters.awayOnly = !awayFilters.awayOnly;
  } else if (filterType === "sameCompetition") {
    awayFilters.sameCompetition = !awayFilters.sameCompetition;
  }
  console.log("客队筛选条件:", awayFilters);
}

// 设置客队场次
function setAwayMatchCount(count) {
  awayFilters.matchCount = count;
  console.log("客队显示场次:", count);
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
  border-radius: 8rpx;
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
    border-radius: 8rpx;
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
  border-radius: 8rpx;
  box-shadow: none;
  border: 1px solid #e5e7eb;
}

.primary-tab {
  flex: 1;
  padding: 10rpx;
  text-align: center;
  border-radius: 8rpx;
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
  border-radius: 8rpx;
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

// 加载/错误状态
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80rpx 40rpx;
}

.loading-text {
  font-size: 28rpx;
  color: #6b7280;
}

.error-text {
  font-size: 28rpx;
  color: #ef4444;
  margin-bottom: 20rpx;
}

.retry-btn {
  padding: 12rpx 32rpx;
  background: #0d9488;
  border-radius: 8rpx;
  text {
    color: #fff;
    font-size: 26rpx;
  }
}

// 展开箭头
.expand-arrow {
  font-size: 16rpx;
  color: #9ca3af;
  margin-left: auto;
  padding-left: 4rpx;
  flex-shrink: 0;
  transition: transform 0.2s;

  &.expanded {
    transform: rotate(90deg);
    color: #0d9488;
  }
}

// 赔率变动弹窗
.modal-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: flex-end;
  z-index: 999;
}

.modal-content {
  width: 100%;
  max-height: 70vh;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  display: flex;
  flex-direction: column;
  padding-right: 32rpx;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1px solid #e5e7eb;
}

.modal-title {
  font-size: 30rpx;
  font-weight: 500;
  color: #111827;
}

.modal-close {
  font-size: 36rpx;
  color: #9ca3af;
  padding: 8rpx;
}

.modal-loading,
.modal-empty {
  text-align: center;
  padding: 60rpx;
  text {
    font-size: 28rpx;
    color: #9ca3af;
  }
}

.modal-body {
  flex: 1;
  max-height: 60vh;
  padding: 0 48rpx 24rpx 32rpx;
}

.history-header {
  display: flex;
  padding: 16rpx 8rpx 16rpx 0;
  border-bottom: 1px solid #e5e7eb;
  position: sticky;
  top: 0;
  background: #fff;
  text {
    font-size: 24rpx;
    color: #6b7280;
    font-weight: 500;
  }
}

.history-row {
  display: flex;
  padding: 14rpx 8rpx 14rpx 0;
  border-bottom: 1px solid #f3f4f6;
  text {
    font-size: 24rpx;
    color: #374151;
  }

  &.h-row-alt {
    background: #f9fafb;
  }
}

.h-col-time {
  flex: 2.5;
  min-width: 0;
}

.h-col {
  flex: 1;
  text-align: center;
  min-width: 0;
}

// 内容区域
.content-area {
  margin-top: 20rpx;
  flex: 1;
}

.content-section {
  padding: 0 24rpx 20rpx;
  min-height: auto;
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
  border-radius: 8rpx;
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
  width: 130rpx;
  flex-shrink: 0;
  padding: 10rpx 8rpx;
  display: flex;
  align-items: center;
}

.header-data {
  flex: 1;
  display: flex;
  padding: 10rpx 8rpx 10rpx 0;
  align-items: center;

  &.asian-header {
    // 亚指特殊布局：主胜、盘、客胜
    .col-odds {
      flex: 1;
    }
    .col-handicap {
      width: 70rpx;
      flex-shrink: 0;
      text-align: center;
    }
  }
}

// 每个公司的数据组（包含初盘和即时两行）
.table-group {
  display: flex;

  &.row-even {
    background: #f8f8f8;
  }

  &:last-child {
    border-bottom: none;
  }
}

// 公司名称单元格（垂直居中两行）
.company-cell {
  width: 130rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 8rpx;
  white-space: nowrap;
  overflow: hidden;
}

.company-name {
  font-size: 22rpx;
  color: #111827;
  font-weight: normal;
  overflow: hidden;
  text-overflow: ellipsis;
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
  padding: 6rpx 8rpx 6rpx 0;
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

.col-handicap {
  width: 70rpx;
  flex-shrink: 0;
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

.handicap-value {
  font-size: 22rpx;
  color: #111827;
  font-weight: normal;
  text-align: center;
  display: inline-block;

  &.handicap-up {
    color: #ef4444;
  }

  &.handicap-down {
    color: #10b981;
  }
}

// ===== 大小球紧凑表格样式 =====
.compact-table-ou {
  background: #ffffff;
  border-radius: 8rpx;
  overflow: hidden;
  border: 1px solid #e5e7eb;
}

.table-header-ou {
  display: flex;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-size: 22rpx;
  color: #6b7280;
  font-weight: normal;

  .col-company {
    width: 100rpx;
    flex-shrink: 0;
    padding: 10rpx 16rpx;
    display: flex;
    align-items: center;
  }

  .col-label {
    width: 36rpx;
    flex-shrink: 0;
  }

  .col-over,
  .col-under,
  .col-line {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10rpx 0;
  }

  .col-over,
  .col-under {
    flex: 1;
  }

  .col-line {
    width: 80rpx;
    flex-shrink: 0;
  }
}

.table-group-ou {
  display: flex;

  &.row-even {
    background: #f8f8f8;
  }

  &:last-child {
    border-bottom: none;
  }
}

// 公司名称单元格
.company-cell-ou {
  width: 130rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 8rpx;
  white-space: nowrap;
  overflow: hidden;

  .company-name {
    font-size: 22rpx;
    color: #111827;
    font-weight: normal;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

// 数据行容器
.data-rows-ou {
  flex: 1;
  display: flex;
  flex-direction: column;
}

// 单行数据
.table-row-ou {
  display: flex;
  padding: 6rpx 0 6rpx 0;
  align-items: center;
  min-height: 36rpx;

  .col-label {
    width: 36rpx;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;

    .label-text {
      font-size: 22rpx;
      font-weight: 500;

      &.initial {
        color: #9ca3af;
      }

      &.instant {
        color: #2563eb;
      }
    }
  }

  .col-over,
  .col-under {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;

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

      .arrow-icon {
        font-size: 20rpx;
        position: absolute;
        right: -4rpx;
        top: 9rpx;
        transform: translateY(-42%);
      }
    }
  }

  .col-line {
    width: 80rpx;
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    align-items: center;

    .line-value {
      font-size: 22rpx;
      color: #0d9488;
      font-weight: 500;
      text-align: center;
      background: #f0fdfa;
      padding: 4rpx 12rpx;
      border-radius: 4rpx;
      display: inline-block;

      &.line-up {
        color: #ef4444;
        background: #fef2f2;
      }

      &.line-down {
        color: #10b981;
        background: #f0fdf4;
      }
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
  padding: 16rpx;
  background: transparent;
  border-bottom: none;
}

.section-title {
  font-size: 28rpx;
  font-weight: 500;
  margin: 0;
  color: #111827;
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
    border-radius: 8rpx;
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
.h2h-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.h2h-header-right {
  display: flex;
  align-items: center;
  gap: 0;
  flex: 1;
  justify-content: flex-end;
}

.h2h-filters {
  display: flex;
  gap: 8rpx;
}

.filter-item {
  padding: 4rpx 12rpx;
  background: transparent;
  border-radius: 8rpx;
  font-size: 22rpx;
  color: #9ca3af;
  border: none;
  transition: all 0.3s ease;
  cursor: pointer;

  &.active {
    background: #0d9488;
    color: #ffffff;
  }

  &:active {
    opacity: 0.8;
  }
}

.h2h-content {
  padding: 0 !important;
}

.h2h-filters-row {
  display: flex;
  gap: 12rpx;
  padding: 16rpx 16rpx 12rpx;
  background: transparent;
  border-bottom: none;
}

.filter-dropdown {
  display: flex;
  align-items: center;
  gap: 6rpx;
  padding: 6rpx 16rpx;
  background: #f3f4f6;
  border: none;
  border-radius: 8rpx;
  font-size: 22rpx;
  color: #6b7280;
  transition: all 0.3s ease;

  .dropdown-icon {
    font-size: 18rpx;
    color: #9ca3af;
  }
}

.h2h-table {
  background: #ffffff;
}

.h2h-table-header {
  display: flex;
  background: transparent;
  border-bottom: none;
  padding: 12rpx 16rpx;
  font-size: 22rpx;
  color: #9ca3af;
  font-weight: normal;
  align-items: center;
}

.h2h-table-row {
  display: flex;
  padding: 14rpx 16rpx;
  border-bottom: none;
  font-size: 22rpx;
  align-items: center;
  margin-bottom: 4rpx;

  &.row-alt {
    background: transparent;
  }

  &:last-child {
    border-bottom: none;
    margin-bottom: 0;
  }
}

.col-event {
  width: 90rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2rpx;
  padding-right: 12rpx;

  .event-date {
    font-size: 20rpx;
    color: #6b7280;
    white-space: nowrap;
    line-height: 1.4;
  }

  .event-name {
    font-size: 20rpx;
    color: #111827;
    white-space: nowrap;
    line-height: 1.4;
  }
}

.col-teams {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 0;

  .team-left {
    flex: 1;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    padding-right: 12rpx;
  }

  .team-right {
    flex: 1;
    display: flex;
    justify-content: flex-start;
    align-items: center;
    padding-left: 12rpx;
  }

  .team-name {
    font-size: 22rpx;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.2;

    &.team-draw {
      color: #374151;
    }

    &.team-win {
      color: #ef4444;
    }

    &.team-lose {
      color: #10b981;
    }
  }

  .score-wrapper {
    flex-shrink: 0;
    width: 80rpx;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2rpx;
  }

  .match-score {
    font-size: 24rpx;
    color: #111827;
  }

  .halftime-score {
    font-size: 20rpx;
    color: #9ca3af;
  }
}

.col-asian,
.col-ou {
  width: 88rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2rpx;
}

.data-value {
  font-size: 22rpx;
  color: #111827;

  &.win {
    color: #ef4444;
  }

  &.lose {
    color: #10b981;
  }

  &.big {
    color: #ef4444;
  }

  &.small {
    color: #10b981;
  }
}

.data-label {
  font-size: 20rpx;

  &.win {
    color: #ef4444;
  }

  &.lose {
    color: #10b981;
  }

  &.big {
    color: #ef4444;
  }

  &.small {
    color: #10b981;
  }
}

// 未来赛程
.future-schedule-wrapper {
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}

.team-schedule-section {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.team-schedule-title {
  font-size: 26rpx;
  font-weight: 500;
  color: #111827;
  padding: 0 16rpx 12rpx;
  border-bottom: none;
}

.schedule-table {
  display: flex;
  flex-direction: column;
}

.schedule-header {
  display: flex;
  background: transparent;
  padding: 12rpx 16rpx;
  font-size: 22rpx;
  color: #9ca3af;
  font-weight: normal;
  border-bottom: none;
}

.schedule-row {
  display: flex;
  padding: 14rpx 16rpx;
  background: transparent;
  border-bottom: none;
  font-size: 22rpx;
  align-items: center;
  margin-bottom: 4rpx;

  &:last-child {
    margin-bottom: 0;
  }
}

.schedule-col-time {
  width: 130rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  white-space: nowrap;
  font-size: 22rpx;
  color: #6b7280;

  .schedule-date {
    font-size: 22rpx;
    color: #6b7280;
    line-height: 1.4;
  }

  .schedule-time {
    font-size: 22rpx;
    color: #6b7280;
    line-height: 1.4;
  }
}

.schedule-col-event {
  width: 80rpx;
  flex-shrink: 0;
  text-align: center;
  font-size: 22rpx;
  color: #111827;
}

.schedule-col-match {
  flex: 1;
  font-size: 22rpx;
  color: #111827;
  padding: 0 12rpx;
  text-align: center;
}

.schedule-col-interval {
  width: 80rpx;
  flex-shrink: 0;
  text-align: center;
  font-size: 22rpx;
  color: #111827;

  .current-match {
    color: #ef4444;
    font-weight: 500;
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
