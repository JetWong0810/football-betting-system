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
            <!-- 欧赔变动历史 -->
            <view v-if="expandedHistory[`euro_${index}`]" class="history-panel">
              <view v-if="historyLoading[`euro_${index}`]" class="history-loading">
                <text>加载中...</text>
              </view>
              <view v-else-if="historyData[`euro_${index}`]?.length" class="history-list">
                <view class="history-header">
                  <text class="h-col-time">时间</text>
                  <text class="h-col">主胜</text>
                  <text class="h-col">平局</text>
                  <text class="h-col">客胜</text>
                  <text class="h-col">返还</text>
                </view>
                <view v-for="(h, hi) in historyData[`euro_${index}`]" :key="hi" class="history-row" :class="{ 'h-row-alt': hi % 2 === 0 }">
                  <text class="h-col-time">{{ formatTime(h.time) }}</text>
                  <text class="h-col">{{ formatNumber(h.win) }}</text>
                  <text class="h-col">{{ formatNumber(h.draw) }}</text>
                  <text class="h-col">{{ formatNumber(h.lose) }}</text>
                  <text class="h-col">{{ h.returnRate }}%</text>
                </view>
              </view>
              <view v-else class="history-empty">
                <text>暂无变动记录</text>
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
            <!-- 亚盘变动历史 -->
            <view v-if="expandedHistory[`asian_${index}`]" class="history-panel">
              <view v-if="historyLoading[`asian_${index}`]" class="history-loading">
                <text>加载中...</text>
              </view>
              <view v-else-if="historyData[`asian_${index}`]?.length" class="history-list">
                <view class="history-header">
                  <text class="h-col-time">时间</text>
                  <text class="h-col">主队</text>
                  <text class="h-col">盘口</text>
                  <text class="h-col">客队</text>
                </view>
                <view v-for="(h, hi) in historyData[`asian_${index}`]" :key="hi" class="history-row" :class="{ 'h-row-alt': hi % 2 === 0 }">
                  <text class="h-col-time">{{ formatTime(h.time) }}</text>
                  <text class="h-col">{{ formatNumber(h.home) }}</text>
                  <text class="h-col">{{ h.handicapText || formatNumber(h.handicap) }}</text>
                  <text class="h-col">{{ formatNumber(h.away) }}</text>
                </view>
              </view>
              <view v-else class="history-empty">
                <text>暂无变动记录</text>
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
            <!-- 大小球变动历史 -->
            <view v-if="expandedHistory[`ou_${index}`]" class="history-panel">
              <view v-if="historyLoading[`ou_${index}`]" class="history-loading">
                <text>加载中...</text>
              </view>
              <view v-else-if="historyData[`ou_${index}`]?.length" class="history-list">
                <view class="history-header">
                  <text class="h-col-time">时间</text>
                  <text class="h-col">大球</text>
                  <text class="h-col">盘口</text>
                  <text class="h-col">小球</text>
                </view>
                <view v-for="(h, hi) in historyData[`ou_${index}`]" :key="hi" class="history-row" :class="{ 'h-row-alt': hi % 2 === 0 }">
                  <text class="h-col-time">{{ formatTime(h.time) }}</text>
                  <text class="h-col">{{ formatNumber(h.over) }}</text>
                  <text class="h-col">{{ formatNumber(h.line) }}</text>
                  <text class="h-col">{{ formatNumber(h.under) }}</text>
                </view>
              </view>
              <view v-else class="history-empty">
                <text>暂无变动记录</text>
              </view>
            </view>
          </template>
        </view>
      </view>

      <!-- 数据 - 基本面 -->
      <view v-if="activePrimaryTab === 'data' && activeSecondaryTab === 'fundamentals'" class="content-section">
        <!-- 1. 主队历史比赛数据 -->
        <view class="section-block">
          <view class="section-header h2h-section-header" @tap="toggleSection('homeHistory')">
            <text class="section-title">{{ matchInfo.homeTeam }} 近期战绩</text>
            <view class="h2h-header-right">
              <view class="h2h-filters">
                <view class="filter-item" :class="{ active: homeFilters.homeOnly }" @tap.stop="toggleHomeFilter('homeOnly')">
                  <text>主场</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.sameCompetition }" @tap.stop="toggleHomeFilter('sameCompetition')">
                  <text>同赛事</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.matchCount === 10 }" @tap.stop="setHomeMatchCount(10)">
                  <text>10场</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.matchCount === 20 }" @tap.stop="setHomeMatchCount(20)">
                  <text>20场</text>
                </view>
                <view class="filter-item" :class="{ active: homeFilters.matchCount === 30 }" @tap.stop="setHomeMatchCount(30)">
                  <text>30场</text>
                </view>
              </view>
            </view>
          </view>
          <view v-if="expandedSections.homeHistory" class="section-content h2h-content">
            <!-- 筛选器 -->
            <view class="h2h-filters-row">
              <view class="filter-dropdown">
                <text>36*</text>
                <text class="dropdown-icon">▼</text>
              </view>
              <view class="filter-dropdown">
                <text>初盘</text>
                <text class="dropdown-icon">▼</text>
              </view>
            </view>

            <!-- 表格 -->
            <view class="h2h-table">
              <!-- 表头 -->
              <view class="h2h-table-header">
                <view class="col-event">赛事</view>
                <view class="col-teams">主队　比分　客队</view>
                <view class="col-asian">亚指</view>
                <view class="col-ou">大小</view>
              </view>

              <!-- 数据行 -->
              <view v-for="(match, index) in recentMatches.home" :key="match.id" class="h2h-table-row" :class="{ 'row-alt': index % 2 === 0 }">
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
                  <text class="data-value" :class="match.ouClass">{{ match.ou }}</text>
                  <text class="data-label" :class="match.ouClass">{{ match.ouLabel }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 2. 客队历史比赛数据 -->
        <view class="section-block">
          <view class="section-header h2h-section-header" @tap="toggleSection('awayHistory')">
            <text class="section-title">{{ matchInfo.awayTeam }} 近期战绩</text>
            <view class="h2h-header-right">
              <view class="h2h-filters">
                <view class="filter-item" :class="{ active: awayFilters.awayOnly }" @tap.stop="toggleAwayFilter('awayOnly')">
                  <text>客场</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.sameCompetition }" @tap.stop="toggleAwayFilter('sameCompetition')">
                  <text>同赛事</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.matchCount === 10 }" @tap.stop="setAwayMatchCount(10)">
                  <text>10场</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.matchCount === 20 }" @tap.stop="setAwayMatchCount(20)">
                  <text>20场</text>
                </view>
                <view class="filter-item" :class="{ active: awayFilters.matchCount === 30 }" @tap.stop="setAwayMatchCount(30)">
                  <text>30场</text>
                </view>
              </view>
            </view>
          </view>
          <view v-if="expandedSections.awayHistory" class="section-content h2h-content">
            <!-- 筛选器 -->
            <view class="h2h-filters-row">
              <view class="filter-dropdown">
                <text>36*</text>
                <text class="dropdown-icon">▼</text>
              </view>
              <view class="filter-dropdown">
                <text>初盘</text>
                <text class="dropdown-icon">▼</text>
              </view>
            </view>

            <!-- 表格 -->
            <view class="h2h-table">
              <!-- 表头 -->
              <view class="h2h-table-header">
                <view class="col-event">赛事</view>
                <view class="col-teams">主队　比分　客队</view>
                <view class="col-asian">亚指</view>
                <view class="col-ou">大小</view>
              </view>

              <!-- 数据行 -->
              <view v-for="(match, index) in recentMatches.away" :key="match.id" class="h2h-table-row" :class="{ 'row-alt': index % 2 === 0 }">
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
                  <text class="data-value" :class="match.ouClass">{{ match.ou }}</text>
                  <text class="data-label" :class="match.ouClass">{{ match.ouLabel }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 3. 两队交锋数据 -->
        <view class="section-block">
          <view class="section-header h2h-section-header" @tap="toggleSection('h2h')">
            <text class="section-title">历史交锋</text>
            <view class="h2h-header-right">
              <view class="h2h-filters">
                <view class="filter-item" :class="{ active: h2hFilters.sameVenue }" @tap.stop="toggleH2hFilter('sameVenue')">
                  <text>同主客</text>
                </view>
                <view class="filter-item" :class="{ active: h2hFilters.sameCompetition }" @tap.stop="toggleH2hFilter('sameCompetition')">
                  <text>同赛事</text>
                </view>
                <view class="filter-item" :class="{ active: h2hFilters.matchCount === 10 }" @tap.stop="setH2hMatchCount(10)">
                  <text>10场</text>
                </view>
                <view class="filter-item" :class="{ active: h2hFilters.matchCount === 20 }" @tap.stop="setH2hMatchCount(20)">
                  <text>20场</text>
                </view>
                <view class="filter-item" :class="{ active: h2hFilters.matchCount === 30 }" @tap.stop="setH2hMatchCount(30)">
                  <text>30场</text>
                </view>
              </view>
            </view>
          </view>
          <view v-if="expandedSections.h2h" class="section-content h2h-content">
            <!-- 筛选器 -->
            <view class="h2h-filters-row">
              <view class="filter-dropdown">
                <text>36*</text>
                <text class="dropdown-icon">▼</text>
              </view>
              <view class="filter-dropdown">
                <text>初盘</text>
                <text class="dropdown-icon">▼</text>
              </view>
            </view>

            <!-- 表格 -->
            <view class="h2h-table">
              <!-- 表头 -->
              <view class="h2h-table-header">
                <view class="col-event">赛事</view>
                <view class="col-teams">主队　比分　客队</view>
                <view class="col-asian">亚指</view>
                <view class="col-ou">大小</view>
              </view>

              <!-- 数据行 -->
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
                  <text class="data-value" :class="match.ouClass">{{ match.ou }}</text>
                  <text class="data-label" :class="match.ouClass">{{ match.ouLabel }}</text>
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
              <!-- 主队赛程 -->
              <view class="team-schedule-section">
                <text class="team-schedule-title">{{ matchInfo.homeTeam }}</text>
                <view class="schedule-table">
                  <!-- 表头 -->
                  <view class="schedule-header">
                    <view class="schedule-col-time">时间</view>
                    <view class="schedule-col-event">赛事</view>
                    <view class="schedule-col-match">对阵</view>
                    <view class="schedule-col-interval">间隔</view>
                  </view>
                  <!-- 数据行 -->
                  <view v-for="match in futureSchedule.home" :key="match.id" class="schedule-row">
                    <view class="schedule-col-time">
                      <text class="schedule-date">{{ match.dateShort }}</text>
                      <text class="schedule-time">{{ match.time }}</text>
                    </view>
                    <view class="schedule-col-event">
                      <text>{{ match.competition }}</text>
                    </view>
                    <view class="schedule-col-match">
                      <text>{{ match.matchup }}</text>
                    </view>
                    <view class="schedule-col-interval">
                      <text :class="match.intervalClass">{{ match.interval }}</text>
                    </view>
                  </view>
                </view>
              </view>

              <!-- 客队赛程 -->
              <view class="team-schedule-section">
                <text class="team-schedule-title">{{ matchInfo.awayTeam }}</text>
                <view class="schedule-table">
                  <!-- 表头 -->
                  <view class="schedule-header">
                    <view class="schedule-col-time">时间</view>
                    <view class="schedule-col-event">赛事</view>
                    <view class="schedule-col-match">对阵</view>
                    <view class="schedule-col-interval">间隔</view>
                  </view>
                  <!-- 数据行 -->
                  <view v-for="match in futureSchedule.away" :key="match.id" class="schedule-row">
                    <view class="schedule-col-time">
                      <text class="schedule-date">{{ match.dateShort }}</text>
                      <text class="schedule-time">{{ match.time }}</text>
                    </view>
                    <view class="schedule-col-event">
                      <text>{{ match.competition }}</text>
                    </view>
                    <view class="schedule-col-match">
                      <text>{{ match.matchup }}</text>
                    </view>
                    <view class="schedule-col-interval">
                      <text :class="match.intervalClass">{{ match.interval }}</text>
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
        status: res.match.status || "未开赛",
        statusClass: "pending",
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

// 赔率变动历史
const expandedHistory = reactive({});
const historyData = reactive({});
const historyLoading = reactive({});

async function toggleHistory(type, cid, index) {
  const keyMap = { european: "euro", asian: "asian", overunder: "ou" };
  const key = `${keyMap[type]}_${index}`;

  if (expandedHistory[key]) {
    expandedHistory[key] = false;
    return;
  }

  expandedHistory[key] = true;

  if (historyData[key]) return;

  historyLoading[key] = true;
  try {
    const res = await request({
      url: `/api/odds/history?fid=${fid.value}&cid=${cid}&type=${type}`,
    });
    historyData[key] = res.history || [];
  } catch (e) {
    historyData[key] = [];
    console.error("加载变动历史失败:", e);
  } finally {
    historyLoading[key] = false;
  }
}

function formatTime(time) {
  if (!time) return "";
  // "2026-06-04 17:15:39" -> "06-04 17:15" or "06-04 16:56" -> as-is
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
  home: ["win", "draw", "win", "lose", "draw", "win"],
  away: ["win", "win", "draw", "win", "lose", "win"],
  homeSummary: "3胜2平1负",
  awaySummary: "4胜1平1负",
});

// 近期比赛
const recentMatches = ref({
  home: [
    {
      id: 1,
      dateShort: "24-03-10",
      competition: "英超",
      homeTeam: "曼联",
      awayTeam: "切尔西",
      score: "2:1",
      halftimeScore: "(1-0)",
      homeScore: 2,
      awayScore: 1,
      asian: "-0.5",
      asianClass: "win",
      asianLabel: "赢",
      ou: "2.5",
      ouClass: "small",
      ouLabel: "小",
    },
    {
      id: 2,
      dateShort: "24-03-03",
      competition: "英超",
      homeTeam: "曼联",
      awayTeam: "阿森纳",
      score: "1:1",
      halftimeScore: "(0-1)",
      homeScore: 1,
      awayScore: 1,
      asian: "-0.25",
      asianClass: "lose",
      asianLabel: "输",
      ou: "2.5",
      ouClass: "small",
      ouLabel: "小",
    },
    {
      id: 3,
      dateShort: "24-02-25",
      competition: "英超",
      homeTeam: "曼联",
      awayTeam: "埃弗顿",
      score: "3:0",
      halftimeScore: "(2-0)",
      homeScore: 3,
      awayScore: 0,
      asian: "-1",
      asianClass: "win",
      asianLabel: "赢",
      ou: "2.5",
      ouClass: "big",
      ouLabel: "大",
    },
    {
      id: 4,
      dateShort: "24-02-18",
      competition: "英超",
      homeTeam: "曼联",
      awayTeam: "热刺",
      score: "0:2",
      halftimeScore: "(0-1)",
      homeScore: 0,
      awayScore: 2,
      asian: "-0.5",
      asianClass: "lose",
      asianLabel: "输",
      ou: "3",
      ouClass: "small",
      ouLabel: "小",
    },
    {
      id: 5,
      dateShort: "24-02-11",
      competition: "英超",
      homeTeam: "曼联",
      awayTeam: "纽卡斯尔",
      score: "2:2",
      halftimeScore: "(1-1)",
      homeScore: 2,
      awayScore: 2,
      asian: "-0.25",
      asianClass: "lose",
      asianLabel: "输",
      ou: "2.5",
      ouClass: "big",
      ouLabel: "大",
    },
    {
      id: 6,
      dateShort: "24-02-04",
      competition: "英超",
      homeTeam: "曼联",
      awayTeam: "布莱顿",
      score: "1:0",
      halftimeScore: "(0-0)",
      homeScore: 1,
      awayScore: 0,
      asian: "-0.5",
      asianClass: "win",
      asianLabel: "赢",
      ou: "2.5",
      ouClass: "small",
      ouLabel: "小",
    },
  ],
  away: [
    {
      id: 1,
      dateShort: "24-03-10",
      competition: "英超",
      homeTeam: "曼城",
      awayTeam: "利物浦",
      score: "1:3",
      halftimeScore: "(0-2)",
      homeScore: 1,
      awayScore: 3,
      asian: "0.25",
      asianClass: "win",
      asianLabel: "赢",
      ou: "3",
      ouClass: "big",
      ouLabel: "大",
    },
    {
      id: 2,
      dateShort: "24-03-03",
      competition: "英超",
      homeTeam: "维拉",
      awayTeam: "利物浦",
      score: "1:2",
      halftimeScore: "(1-1)",
      homeScore: 1,
      awayScore: 2,
      asian: "0.5",
      asianClass: "win",
      asianLabel: "赢",
      ou: "2.5",
      ouClass: "big",
      ouLabel: "大",
    },
    {
      id: 3,
      dateShort: "24-02-25",
      competition: "英超",
      homeTeam: "西汉姆",
      awayTeam: "利物浦",
      score: "1:1",
      halftimeScore: "(0-1)",
      homeScore: 1,
      awayScore: 1,
      asian: "0.5",
      asianClass: "lose",
      asianLabel: "输",
      ou: "2.5",
      ouClass: "small",
      ouLabel: "小",
    },
    {
      id: 4,
      dateShort: "24-02-18",
      competition: "英超",
      homeTeam: "伯恩利",
      awayTeam: "利物浦",
      score: "0:3",
      halftimeScore: "(0-2)",
      homeScore: 0,
      awayScore: 3,
      asian: "1",
      asianClass: "win",
      asianLabel: "赢",
      ou: "3",
      ouClass: "big",
      ouLabel: "大",
    },
    {
      id: 5,
      dateShort: "24-02-11",
      competition: "英超",
      homeTeam: "布伦特福德",
      awayTeam: "利物浦",
      score: "3:2",
      halftimeScore: "(2-1)",
      homeScore: 3,
      awayScore: 2,
      asian: "0.75",
      asianClass: "lose",
      asianLabel: "输",
      ou: "2.5",
      ouClass: "big",
      ouLabel: "大",
    },
    {
      id: 6,
      dateShort: "24-02-04",
      competition: "英超",
      homeTeam: "谢菲尔德",
      awayTeam: "利物浦",
      score: "0:2",
      halftimeScore: "(0-1)",
      homeScore: 0,
      awayScore: 2,
      asian: "1.25",
      asianClass: "win",
      asianLabel: "赢",
      ou: "2.5",
      ouClass: "small",
      ouLabel: "小",
    },
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
    dateShort: "25-04-26",
    competition: "澳超",
    homeTeam: "墨尔本城",
    awayTeam: "阿德莱德联",
    score: "0:0",
    halftimeScore: "(0-0)",
    homeScore: 0,
    awayScore: 0,
    asian: "-0.5",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3.25",
    ouClass: "small",
    ouLabel: "小",
  },
  {
    id: 2,
    dateShort: "25-02-07",
    competition: "澳超",
    homeTeam: "阿德莱德联",
    awayTeam: "墨尔本城",
    score: "1:0",
    halftimeScore: "(0-0)",
    homeScore: 1,
    awayScore: 0,
    asian: "-0.25",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3",
    ouClass: "small",
    ouLabel: "小",
  },
  {
    id: 3,
    dateShort: "24-01-25",
    competition: "澳超",
    homeTeam: "墨尔本城",
    awayTeam: "阿德莱德联",
    score: "1:0",
    halftimeScore: "(1-0)",
    homeScore: 1,
    awayScore: 0,
    asian: "-0.5",
    asianClass: "lose",
    asianLabel: "输",
    ou: "3.5",
    ouClass: "small",
    ouLabel: "小",
  },
  {
    id: 4,
    dateShort: "23-10-29",
    competition: "澳超",
    homeTeam: "阿德莱德联",
    awayTeam: "墨尔本城",
    score: "6:0",
    halftimeScore: "(2-0)",
    homeScore: 6,
    awayScore: 0,
    asian: "0.25",
    asianClass: "win",
    asianLabel: "赢",
    ou: "2.5",
    ouClass: "big",
    ouLabel: "大",
  },
  {
    id: 5,
    dateShort: "23-03-03",
    competition: "澳超",
    homeTeam: "阿德莱德联",
    awayTeam: "墨尔本城",
    score: "4:2",
    halftimeScore: "(1-1)",
    homeScore: 4,
    awayScore: 2,
    asian: "0.5",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3",
    ouClass: "big",
    ouLabel: "大",
  },
  {
    id: 6,
    dateShort: "23-01-29",
    competition: "澳超",
    homeTeam: "墨尔本城",
    awayTeam: "阿德莱德联",
    score: "3:3",
    halftimeScore: "(1-3)",
    homeScore: 3,
    awayScore: 3,
    asian: "-1",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3",
    ouClass: "big",
    ouLabel: "大",
  },
  {
    id: 7,
    dateShort: "22-05-22",
    competition: "澳超",
    homeTeam: "墨尔本城",
    awayTeam: "阿德莱德联",
    score: "1:1",
    halftimeScore: "(0-0)",
    homeScore: 1,
    awayScore: 1,
    asian: "-1",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3",
    ouClass: "small",
    ouLabel: "小",
  },
  {
    id: 8,
    dateShort: "22-05-18",
    competition: "澳超",
    homeTeam: "阿德莱德联",
    awayTeam: "墨尔本城",
    score: "0:0",
    halftimeScore: "(0-0)",
    homeScore: 0,
    awayScore: 0,
    asian: "0.5",
    asianClass: "win",
    asianLabel: "赢",
    ou: "2.5",
    ouClass: "small",
    ouLabel: "小",
  },
  {
    id: 9,
    dateShort: "22-02-15",
    competition: "澳超",
    homeTeam: "墨尔本城",
    awayTeam: "阿德莱德联",
    score: "1:2",
    halftimeScore: "(1-1)",
    homeScore: 1,
    awayScore: 2,
    asian: "-1",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3.25",
    ouClass: "small",
    ouLabel: "小",
  },
  {
    id: 10,
    dateShort: "22-01-15",
    competition: "澳超",
    homeTeam: "阿德莱德联",
    awayTeam: "墨尔本城",
    score: "2:2",
    halftimeScore: "(0-1)",
    homeScore: 2,
    awayScore: 2,
    asian: "0.75",
    asianClass: "win",
    asianLabel: "赢",
    ou: "3",
    ouClass: "big",
    ouLabel: "大",
  },
]);

// 获取队伍颜色样式
function getTeamColorClass(match, side) {
  if (match.homeScore === match.awayScore) {
    return "team-draw"; // 平局 - 黑色
  }
  if (side === "home") {
    return match.homeScore > match.awayScore ? "team-win" : "team-lose";
  } else {
    return match.awayScore > match.homeScore ? "team-win" : "team-lose";
  }
}

// 未来赛程
const futureSchedule = ref({
  home: [
    {
      id: 1,
      dateShort: "25-11-07",
      time: "16:35",
      competition: "澳超",
      matchup: "阿德莱德联 2:0 西悉尼流浪者",
      interval: "14天",
      intervalClass: "",
    },
    {
      id: 2,
      dateShort: "25-11-21",
      time: "16:35",
      competition: "澳超",
      matchup: "阿德莱德联 vs 墨尔本城",
      interval: "本场",
      intervalClass: "current-match",
    },
    {
      id: 3,
      dateShort: "25-11-29",
      time: "12:00",
      competition: "澳超",
      matchup: "惠灵顿凤凰 vs 阿德莱德联",
      interval: "8天",
      intervalClass: "",
    },
    {
      id: 4,
      dateShort: "25-12-07",
      time: "16:35",
      competition: "澳超",
      matchup: "阿德莱德联 vs 布里斯班狮吼",
      interval: "16天",
      intervalClass: "",
    },
  ],
  away: [
    {
      id: 1,
      dateShort: "25-11-07",
      time: "16:35",
      competition: "澳超",
      matchup: "墨尔本城 1:2 悉尼FC",
      interval: "14天",
      intervalClass: "",
    },
    {
      id: 2,
      dateShort: "25-11-21",
      time: "16:35",
      competition: "澳超",
      matchup: "阿德莱德联 vs 墨尔本城",
      interval: "本场",
      intervalClass: "current-match",
    },
    {
      id: 3,
      dateShort: "25-11-28",
      time: "19:00",
      competition: "澳超",
      matchup: "墨尔本城 vs 中央海岸水手",
      interval: "7天",
      intervalClass: "",
    },
    {
      id: 4,
      dateShort: "25-12-06",
      time: "17:00",
      competition: "澳超",
      matchup: "纽卡斯尔喷气机 vs 墨尔本城",
      interval: "15天",
      intervalClass: "",
    },
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
  font-size: 18rpx;
  color: #9ca3af;
  margin-left: 4rpx;
  transition: transform 0.2s;
  display: inline-block;

  &.expanded {
    transform: rotate(90deg);
    color: #0d9488;
  }
}

// 变动历史面板
.history-panel {
  background: #f9fafb;
  margin: 0 24rpx 8rpx;
  padding: 12rpx 16rpx;
  border-radius: 0 0 8rpx 8rpx;
  border: 1px solid #e5e7eb;
  border-top: none;
}

.history-loading,
.history-empty {
  text-align: center;
  padding: 16rpx;
  text {
    font-size: 24rpx;
    color: #9ca3af;
  }
}

.history-list {
  max-height: 500rpx;
  overflow-y: auto;
}

.history-header {
  display: flex;
  padding: 8rpx 0;
  border-bottom: 1px solid #e5e7eb;
  text {
    font-size: 22rpx;
    color: #6b7280;
    font-weight: 500;
  }
}

.history-row {
  display: flex;
  padding: 8rpx 0;
  border-bottom: 1px solid #f3f4f6;
  text {
    font-size: 22rpx;
    color: #374151;
  }

  &.h-row-alt {
    background: #f3f4f6;
  }
}

.h-col-time {
  flex: 2;
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
  width: 100rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 16rpx;

  .company-name {
    font-size: 22rpx;
    color: #111827;
    font-weight: normal;
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
  padding: 24rpx 16rpx 8rpx 16rpx;
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
  align-items: flex-start;
  justify-content: center;
  gap: 0;
  padding: 0;

  .team-left {
    flex: 1;
    display: flex;
    justify-content: flex-end;
    padding-right: 12rpx;
    padding-top: 2rpx;
  }

  .team-right {
    flex: 1;
    display: flex;
    justify-content: flex-start;
    padding-left: 12rpx;
    padding-top: 2rpx;
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
  width: 100rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2rpx;
  align-items: center;

  .schedule-date {
    font-size: 20rpx;
    color: #6b7280;
    line-height: 1.4;
  }

  .schedule-time {
    font-size: 20rpx;
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
