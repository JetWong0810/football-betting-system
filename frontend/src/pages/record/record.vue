<template>
  <view class="page-wrapper">
    <!-- 顶部工具栏 -->
    <view class="toolbar">
      <view class="tabs-list">
        <view class="tab-item" :class="{ active: activeTab === 'saved' }" @tap="activeTab = 'saved'">保存记录</view>
        <view class="tab-item" :class="{ active: activeTab === 'betting' }" @tap="activeTab = 'betting'">投注记录</view>
      </view>
    </view>

    <!-- 列表 -->
    <mescroll-body ref="mescrollRef" :down="downOption" :up="upOption" :bottombar="false" @init="mescrollInit" @down="downCallback" @up="upCallback">
      <view class="records-section">
        <!-- 保存记录 tab -->
        <view v-if="activeTab === 'saved'">
          <view v-if="displayedBets.length === 0 && !betStore.loading" class="empty-state">
            <text class="empty-text">暂无保存记录</text>
            <text class="empty-hint">从赛事列表页选择比赛并保存</text>
          </view>

          <view v-else class="bet-list">
            <view v-for="bet in displayedBets" :key="bet.id" class="saved-card" :class="{ 'is-parlay': getMatchCount(bet) > 1, 'bet-hit': getBetHitStatus(bet) === 'hit', 'bet-miss': getBetHitStatus(bet) === 'miss' }">
              <!-- 串关标识条 -->
              <view class="parlay-bar" v-if="getMatchCount(bet) > 1">
                <text class="parlay-label">{{ getParlayTypeLabel(bet) }}</text>
                <text class="parlay-total">总赔率 {{ bet.odds }}</text>
                <view class="parlay-bar-right">
                  <text class="hit-badge hit" v-if="getBetHitStatus(bet) === 'hit'">命中</text>
                  <text class="hit-badge miss" v-else-if="getBetHitStatus(bet) === 'miss'">未中</text>
                  <text class="card-delete" @tap.stop="() => removeBet(bet.id)">删除</text>
                </view>
              </view>

              <!-- 单关的操作区 -->
              <view class="single-bar" v-if="getMatchCount(bet) <= 1">
                <text class="hit-badge hit" v-if="getBetHitStatus(bet) === 'hit'">命中</text>
                <text class="hit-badge miss" v-else-if="getBetHitStatus(bet) === 'miss'">未中</text>
                <text class="card-delete corner" @tap.stop="() => removeBet(bet.id)">删除</text>
              </view>

              <!-- 按比赛分组展示 -->
              <view v-for="(group, idx) in groupLegs(bet.legs)" :key="group.key" class="leg" :class="{ 'leg--divider': idx > 0 }">
                <view class="leg-row1">
                  <text class="leg-teams">{{ formatTeams(group.legs[0]) }}</text>
                </view>
                <text class="leg-sub">{{ group.legs[0].league }} {{ formatDate(group.legs[0].matchTime) }}</text>
                <view v-for="leg in group.legs" :key="leg.id" class="leg-row3">
                  <view class="sel-chip" :class="{ 'chip-hit': getLegHitStatus(leg) === 'hit', 'chip-miss': getLegHitStatus(leg) === 'miss' }">{{ leg.selection || '未选' }}</view>
                  <text class="leg-type">{{ leg.betType }}</text>
                  <text class="leg-at">@{{ leg.odds }}</text>
                  <text class="leg-hit-icon" v-if="getLegHitStatus(leg) === 'hit'">✓</text>
                  <text class="leg-miss-icon" v-else-if="getLegHitStatus(leg) === 'miss'">✗</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 投注记录 tab -->
        <view v-else>
          <!-- 筛选栏始终显示 -->
          <view class="filter-bar">
            <view class="filter-tabs">
              <text class="filter-tab" :class="{ active: betFilter === 'all' }" @tap="betFilter = 'all'">全部</text>
              <text class="filter-tab" :class="{ active: betFilter === 'unsettled' }" @tap="betFilter = 'unsettled'">未结算</text>
              <text class="filter-tab" :class="{ active: betFilter === 'settled' }" @tap="betFilter = 'settled'">已结算</text>
            </view>
            <text class="add-link" @tap="showFormDialog">+ 新增</text>
          </view>

          <view v-if="displayedBets.length === 0 && !betStore.loading" class="empty-state">
            <text class="empty-text">{{ betFilter === 'settled' ? '暂无已结算记录' : betFilter === 'unsettled' ? '暂无未结算记录' : '暂无投注记录' }}</text>
            <text class="empty-hint" v-if="betFilter === 'all'">点击"+ 新增"添加投注记录</text>
          </view>

          <view v-else class="bet-list">
            <view v-for="bet in displayedBets" :key="bet.id" class="bet-card">
              <view class="bet-card-header">
                <view class="bet-card-left">
                  <text class="bet-card-title">{{ primaryMatch(bet) }}</text>
                  <text class="bet-card-sub">{{ getMatchCount(bet) > 1 ? `${getMatchCount(bet)}场串关` : bet.legs?.[0]?.league || '' }} · {{ formatDate(bet.legs?.[0]?.matchTime || bet.betTime) }}</text>
                </view>
                <view class="bet-card-badges">
                  <view class="badge-status" :class="bet.status">{{ statusText(bet) }}</view>
                  <view class="badge-result" :class="bet.result" v-if="bet.status === 'settled'">{{ resultText(bet) }}</view>
                  <view
                    class="badge-prediction"
                    :class="{ 'pred-hit': bet.predictionHit === true, 'pred-miss': bet.predictionHit === false }"
                    v-if="bet.status === 'settled' && bet.predictionHit != null"
                  >预测{{ bet.predictionHit ? '命中' : '未中' }}</view>
                </view>
              </view>

              <!-- 串关展开（按比赛分组） -->
              <view v-if="getMatchCount(bet) > 1" class="bet-legs-list">
                <view v-for="group in groupLegs(bet.legs)" :key="group.key" class="bet-leg-group">
                  <text class="bet-leg-name">{{ formatTeams(group.legs[0]) }}</text>
                  <view v-for="leg in group.legs" :key="leg.id" class="bet-leg-row">
                    <view class="bet-leg-right">
                      <view class="sel-chip sm">{{ leg.selection || leg.betType }}</view>
                      <text class="bet-leg-type">{{ leg.betType }}</text>
                      <text class="bet-leg-odds">@{{ leg.odds }}</text>
                    </view>
                  </view>
                </view>
              </view>

              <!-- 底部 -->
              <view class="bet-card-footer">
                <view class="bet-card-info-row">
                  <view class="bet-card-sel" v-if="getMatchCount(bet) <= 1">
                    <template v-for="leg in (bet.legs || [])" :key="leg.id">
                      <view class="sel-chip sm">{{ leg.selection }}</view>
                    </template>
                    <text class="bet-card-type">{{ bet.legs?.[0]?.betType }} @{{ bet.odds }}</text>
                  </view>
                  <view class="bet-card-sel" v-else>
                    <text class="bet-card-type">总赔率 @{{ bet.odds }}</text>
                  </view>
                  <text class="bet-amount" v-if="bet.stake">¥{{ bet.stake }}</text>
                </view>
                <view class="bet-card-settled-row" v-if="bet.status === 'settled' && bet.profit != null">
                  <text class="settled-profit" :class="{ win: Number(bet.profit) > 0, lose: Number(bet.profit) < 0 }">
                    {{ Number(bet.profit) > 0 ? '+' : '' }}¥{{ parseFloat(Number(bet.profit).toFixed(2)) }}
                  </text>
                </view>
                <view class="bet-card-actions" v-if="bet.status === 'betting'">
                  <text class="act-link settle" @tap.stop="() => startSettle(bet)">结算</text>
                  <text class="act-link edit" @tap.stop="() => startEdit(bet)">编辑</text>
                  <text class="act-link del" @tap.stop="() => removeBet(bet.id)">删除</text>
                </view>
              </view>
            </view>
          </view>
        </view>
      </view>
    </mescroll-body>

    <BetRecordDialog v-model:visible="showDialog" :editing-bet="editingBet" :settle-mode="settleMode" @success="handleRecordSuccess" />
    <ConfirmDialog />
  </view>
</template>

<script setup>
import dayjs from "dayjs";
import BetRecordDialog from "@/components/BetRecordDialog.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import MescrollBody from "mescroll-uni/mescroll-body.vue";
import { useBetStore } from "@/stores/betStore";
import { showConfirm } from "@/utils/confirm";
import { request } from "@/utils/http";
import { ref, computed, onMounted, watch } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { requireAuth } from "@/utils/auth";

const betStore = useBetStore();
const editingBet = ref(null);
const settleMode = ref(false);
const activeTab = ref("saved");
const betFilter = ref("all");
const showDialog = ref(false);

// 赛果数据缓存：{ "YYYY-MM-DD": [match items] }
const resultsCache = ref({});

const mescrollRef = ref(null);
let mescroll = null;


function mescrollInit(mescrollInstance) {
  mescroll = mescrollInstance;
  setTimeout(() => {
    if (mescroll && mescroll.triggerUpScroll) mescroll.triggerUpScroll();
  }, 100);
}

function downCallback() {
  betStore.refreshBets()
    .then(() => { if (mescroll) mescroll.endSuccess(); })
    .catch(() => { if (mescroll) mescroll.endErr(); });
}

function upCallback() {
  betStore.loadMore()
    .then(() => { if (mescroll) mescroll.endSuccess(displayedBets.value.length, betStore.hasMore); })
    .catch(() => { if (mescroll) mescroll.endErr(); });
}

const downOption = { auto: false };
const upOption = { auto: false, page: { num: 0, size: betStore.pageSize }, noMoreSize: 0, empty: { use: false } };

onMounted(() => {
  if (!requireAuth()) return;
  if (betStore.bets.length === 0) betStore.bootstrap();
});

onShow(() => {
  if (betStore.pendingTab) {
    activeTab.value = betStore.pendingTab;
    betStore.pendingTab = null;
  }
  if (betStore.bets.length > 0) betStore.refreshBets();

  const prefill = uni.getStorageSync('predict-bet-prefill');
  if (prefill) {
    uni.removeStorageSync('predict-bet-prefill');
    activeTab.value = 'betting';
    editingBet.value = null;
    settleMode.value = false;
    setTimeout(() => {
      showDialog.value = true;
      betStore.predictPrefill = prefill;
    }, 300);
  }

  // 来自首页 QuickRecordFab 的快速记录入口
  const openNew = uni.getStorageSync('open-new-bet');
  if (openNew) {
    uni.removeStorageSync('open-new-bet');
    editingBet.value = null;
    settleMode.value = false;
    activeTab.value = 'betting';
    setTimeout(() => { showDialog.value = true; }, 300);
  }
});

const allBets = computed(() => betStore.bets);

// 监听保存记录变化，自动加载赛果
watch(() => betStore.bets, () => { loadResultsForSavedBets(); }, { deep: true });

async function loadResultsForSavedBets() {
  const savedBets = allBets.value.filter(b => b.status === 'saved')
  const dates = new Set()
  savedBets.forEach(bet => {
    (bet.legs || []).forEach(leg => {
      if (leg.matchTime || leg.matchDate) {
        const d = dayjs(leg.matchTime || leg.matchDate).format('YYYY-MM-DD')
        if (d && d !== 'Invalid Date') {
          dates.add(d)
          // 凌晨场（00:00-06:00）归属前一天期号
          const hour = dayjs(leg.matchTime || leg.matchDate).hour()
          if (hour < 6) {
            dates.add(dayjs(d).subtract(1, 'day').format('YYYY-MM-DD'))
          }
        }
      }
    })
  })
  for (const date of dates) {
    if (resultsCache.value[date]) continue
    try {
      const data = await request({ url: '/api/match-results', method: 'GET', data: { date } })
      resultsCache.value[date] = data.items || []
    } catch (e) {
      resultsCache.value[date] = []
    }
  }
}

function findMatchResult(leg) {
  const home = (leg.homeTeam || '').trim()
  const away = (leg.awayTeam || '').trim()
  if (!home || !away) return null
  // 搜索所有已缓存的赛果
  for (const items of Object.values(resultsCache.value)) {
    if (!items || !items.length) continue
    const found = items.find(m => {
      const mHome = (m.homeTeam?.name || m.homeTeam || '').trim()
      const mAway = (m.awayTeam?.name || m.awayTeam || '').trim()
      return (mHome === home && mAway === away) || (mHome.includes(home) && mAway.includes(away)) || (home.includes(mHome) && away.includes(mAway))
    })
    if (found) return found
  }
  return null
}

function getLegHitStatus(leg) {
  const match = findMatchResult(leg)
  if (!match) return null // 未找到赛果
  if (match.homeScore === null || match.homeScore === undefined) return null // 比赛未结束

  const hs = Number(match.homeScore)
  const as = Number(match.awayScore)
  const selection = (leg.selection || '').trim()
  const betType = (leg.betType || '').trim()

  if (betType.includes('让球')) {
    // 让球胜平负：从 handicap 或 note 中提取让球数
    let handicap = 0
    if (leg.handicap !== undefined && leg.handicap !== null) {
      handicap = Number(leg.handicap)
    } else if (leg.note) {
      const m = leg.note.match(/\(([+-]?\d+\.?\d*)\)/)
      if (m) handicap = Number(m[1])
    }
    const adjusted = hs + handicap - as
    let actualResult = ''
    if (adjusted > 0) actualResult = '胜'
    else if (adjusted === 0) actualResult = '平'
    else actualResult = '负'
    return selection === actualResult ? 'hit' : 'miss'
  }

  if (betType.includes('胜平负') || betType === '胜平负') {
    let actualResult = ''
    if (hs > as) actualResult = '胜'
    else if (hs === as) actualResult = '平'
    else actualResult = '负'
    return selection === actualResult ? 'hit' : 'miss'
  }

  if (betType.includes('总进球')) {
    const totalGoals = hs + as
    // selection 格式如 "0", "1", "2", "3", "4", "5", "6", "7+"
    if (selection.includes('+')) {
      const min = parseInt(selection)
      return totalGoals >= min ? 'hit' : 'miss'
    }
    return totalGoals === parseInt(selection) ? 'hit' : 'miss'
  }

  if (betType.includes('半全场')) {
    // 需要半场比分数据，暂不支持
    return null
  }

  if (betType.includes('比分')) {
    // selection 格式如 "1:0", "2:1"
    const parts = selection.split(':')
    if (parts.length === 2) {
      return (hs === parseInt(parts[0]) && as === parseInt(parts[1])) ? 'hit' : 'miss'
    }
    return null
  }

  return null
}

function getBetHitStatus(bet) {
  const legs = bet.legs || []
  if (!legs.length) return null
  const statuses = legs.map(getLegHitStatus)
  if (statuses.some(s => s === null)) return null // 有比赛未出结果
  if (statuses.every(s => s === 'hit')) return 'hit'
  return 'miss'
}

const displayedBets = computed(() => {
  if (activeTab.value === "saved") return allBets.value.filter((b) => b.status === "saved");
  const bettingList = allBets.value.filter((b) => b.status === "betting" || b.status === "settled");
  if (betFilter.value === "unsettled") return bettingList.filter((b) => b.status === "betting");
  if (betFilter.value === "settled") return bettingList.filter((b) => b.status === "settled");
  return bettingList;
});

function showFormDialog() { editingBet.value = null; showDialog.value = true; }
function handleRecordSuccess(payload) {
  editingBet.value = null;
  if (payload && payload.status === "betting") {
    activeTab.value = "betting";
    betFilter.value = "unsettled";
  }
}

async function removeBet(id) {
  const confirmed = await showConfirm({
    title: "删除记录",
    content: "确认删除这条记录吗？删除后不可恢复。",
    confirmText: "删除",
    type: "danger",
  });
  if (!confirmed) return;
  try {
    if (editingBet.value?.id === id) editingBet.value = null;
    await betStore.removeBet(id);
    uni.showToast({ title: "已删除", icon: "success" });
  } catch (e) {
    uni.showToast({ title: e.message || "删除失败", icon: "none" });
  }
}

function startEdit(bet) {
  if (bet.status === "settled") { uni.showToast({ title: "已结算不可编辑", icon: "none" }); return; }
  settleMode.value = false;
  editingBet.value = bet; showDialog.value = true;
}

function startSettle(bet) {
  settleMode.value = true;
  editingBet.value = bet; showDialog.value = true;
}

function formatDate(v) { return v ? dayjs(v).format("MM-DD HH:mm") : "-"; }
function resultText(b) { return { win: "赢", lose: "输", pending: "待定", "half-win": "赢半", "half-lose": "输半" }[b.result] || ""; }
function statusText(b) { return { saved: "已保存", betting: "投注中", settled: "已结算" }[b.status] || ""; }
function primaryMatch(b) {
  const legs = b.legs || [];
  if (!legs.length) return b.matchName || "未命名";
  const mc = getMatchCount(b)
  if (mc === 1) return formatTeams(legs[0]);
  return `${formatTeams(legs[0])} 等${mc}场`;
}
function formatTeams(l) { return `${l?.homeTeam || "主队"} vs ${l?.awayTeam || "客队"}`; }

function groupLegs(legs) {
  if (!legs) return []
  const map = {}
  legs.forEach(leg => {
    const key = `${leg.homeTeam}-${leg.awayTeam}-${leg.matchTime}`
    if (!map[key]) map[key] = { key, legs: [] }
    map[key].legs.push(leg)
  })
  return Object.values(map)
}

function getMatchCount(bet) {
  return groupLegs(bet.legs).length
}

function getParlayTypeLabel(b) {
  const mc = getMatchCount(b)
  if (mc < 2) return "单关";
  if (b.parlayType) { const [m, n] = b.parlayType.split("_"); return `${m}串${n}`; }
  return `${mc}串1`;
}
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.page-wrapper {
  min-height: 100vh;
  background: #f4f5f7;
}

/* ===== 工具栏 ===== */
.toolbar {
  display: flex;
  align-items: center;
  padding: 16rpx 24rpx;
  gap: 16rpx;
  background: #ffffff;
  border-bottom: 1px solid #eceef2;
}

.tabs-list {
  flex: 1;
  display: flex;
  background: #f4f5f7;
  border-radius: 6rpx;
  padding: 4rpx;
}

.tab-item {
  flex: 1;
  padding: 14rpx 0;
  text-align: center;
  font-size: 26rpx;
  font-weight: 500;
  color: #6b7280;
  border-radius: 6rpx;
}

.tab-item.active {
  background: #ffffff;
  color: #1f2937;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}


/* ===== 列表区域 ===== */
.records-section {
  padding: 16rpx 24rpx 40rpx;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 200rpx 40rpx;
}

.empty-text {
  font-size: 28rpx;
  color: #9ca3af;
}

.empty-hint {
  font-size: 24rpx;
  color: #d1d5db;
  margin-top: 8rpx;
}

.bet-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

/* ===== 保存记录卡片 ===== */
.saved-card {
  background: #ffffff;
  border-radius: 6rpx;
  padding: 20rpx;
  position: relative;
}

.saved-card.is-parlay {
  padding-top: 0;
}

.parlay-bar {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 14rpx 0;
  margin-bottom: 8rpx;
  border-bottom: 1px solid #f0f1f3;
}

.parlay-label {
  font-size: 22rpx;
  font-weight: 600;
  color: #0d9488;
  background: #ecfdf5;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;
}

.parlay-total {
  font-size: 22rpx;
  color: #6b7280;
  flex: 1;
}

.parlay-bar-right {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.single-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12rpx;
  padding-bottom: 4rpx;
}

.hit-badge {
  font-size: 20rpx;
  font-weight: 600;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;

  &.hit {
    background: #ecfdf5;
    color: #059669;
  }

  &.miss {
    background: #fef2f2;
    color: #dc2626;
  }
}

.saved-card.bet-hit {
  border-left: 6rpx solid #10b981;
}

.saved-card.bet-miss {
  border-left: 6rpx solid #ef4444;
}

.card-delete {
  font-size: 22rpx;
  color: #ef4444;
  background: #fef2f2;
  padding: 4rpx 14rpx;
  border-radius: 6rpx;
}

.card-delete:active {
  opacity: 0.7;
}

/* Leg 样式 */
.leg {
  padding: 12rpx 0;
}

.leg--divider {
  border-top: 1px dashed #eceef2;
  margin-top: 8rpx;
  padding-top: 16rpx;
}

.leg-row1 {
  margin-bottom: 2rpx;
}

.leg-teams {
  font-size: 28rpx;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.5rpx;
}

.leg-sub {
  font-size: 22rpx;
  color: #a0a5ae;
  margin-bottom: 12rpx;
}

.leg-row3 {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-top: 8rpx;
}

.sel-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #0d9488;
  color: #ffffff;
  font-size: 22rpx;
  font-weight: 600;
  padding: 6rpx 16rpx;
  border-radius: 6rpx;
  min-width: 48rpx;

  &.chip-hit {
    background: #059669;
  }

  &.chip-miss {
    background: #9ca3af;
  }
}

.sel-chip.sm {
  font-size: 20rpx;
  padding: 4rpx 12rpx;
}

.leg-hit-icon {
  font-size: 24rpx;
  color: #059669;
  font-weight: 700;
}

.leg-miss-icon {
  font-size: 24rpx;
  color: #ef4444;
  font-weight: 700;
}

.leg-type {
  font-size: 24rpx;
  color: #4b5563;
}

.leg-at {
  font-size: 24rpx;
  color: #0d9488;
  font-weight: 600;
}

/* ===== 筛选栏 ===== */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16rpx;
}

.filter-tabs {
  display: flex;
  align-items: center;
  gap: 8rpx;
}

.filter-tab {
  font-size: 24rpx;
  color: #6b7280;
  padding: 8rpx 16rpx;
  border-radius: 6rpx;
}

.filter-tab.active {
  color: #0d9488;
  background: #ecfdf5;
  font-weight: 600;
}

.add-link {
  font-size: 24rpx;
  font-weight: 500;
  color: #0d9488;
}

.add-link:active {
  opacity: 0.6;
}

/* ===== 投注记录卡片 ===== */
.bet-card {
  background: #ffffff;
  border-radius: 6rpx;
  padding: 20rpx;
}

.bet-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12rpx;
}

.bet-card-left {
  flex: 1;
  min-width: 0;
}

.bet-card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1f2937;
  display: block;
  margin-bottom: 4rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bet-card-sub {
  font-size: 22rpx;
  color: #a0a5ae;
}

.bet-card-badges {
  display: flex;
  gap: 8rpx;
  margin-left: 12rpx;
  flex-shrink: 0;
}

.badge-status {
  font-size: 20rpx;
  font-weight: 500;
  padding: 4rpx 10rpx;
  border-radius: 6rpx;
}

.badge-status.saved {
  background: #f1f5f9;
  color: #64748b;
}

.badge-status.betting {
  background: #fef3c7;
  color: #92400e;
}

.badge-status.settled {
  background: #ecfdf5;
  color: #065f46;
}

.badge-result {
  font-size: 20rpx;
  font-weight: 600;
  padding: 4rpx 10rpx;
  border-radius: 6rpx;
  color: #ffffff;
}

.badge-result.win { background: #10b981; }
.badge-result.lose { background: #ef4444; }
.badge-result.pending { background: #94a3b8; }
.badge-result.half-win { background: #84cc16; }
.badge-result.half-lose { background: #f59e0b; }

.badge-prediction {
  font-size: 18rpx;
  font-weight: 600;
  padding: 4rpx 10rpx;
  border-radius: 6rpx;
  border: 1px solid transparent;
}

.badge-prediction.pred-hit {
  color: #059669;
  background: #d1fae5;
  border-color: #a7f3d0;
}

.badge-prediction.pred-miss {
  color: #ef4444;
  background: #fee2e2;
  border-color: #fecaca;
}

.bet-legs-list {
  background: #f9fafb;
  border-radius: 6rpx;
  padding: 12rpx 16rpx;
  margin-bottom: 12rpx;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.bet-leg-group {
  &:not(:first-child) {
    border-top: 1px dashed #eceef2;
    padding-top: 10rpx;
  }
}

.bet-leg-row {
  display: flex;
  align-items: center;
  margin-top: 6rpx;
}

.bet-leg-name {
  font-size: 24rpx;
  color: #374151;
  font-weight: 500;
}

.bet-leg-right {
  display: flex;
  align-items: center;
  gap: 8rpx;
}

.bet-leg-type {
  font-size: 22rpx;
  color: #9ca3af;
}

.bet-leg-odds {
  font-size: 22rpx;
  color: #6b7280;
}

.bet-card-footer {
  padding-top: 12rpx;
  border-top: 1px solid #f0f1f3;
}

.bet-card-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.bet-card-sel {
  display: flex;
  align-items: center;
  gap: 8rpx;
}

.bet-card-type {
  font-size: 22rpx;
  color: #6b7280;
}

.bet-card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 24rpx;
  margin-top: 12rpx;
}

.bet-amount {
  font-size: 28rpx;
  font-weight: 700;
  color: #1f2937;
}

.bet-card-settled-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 12rpx;
}

.settled-profit {
  font-size: 28rpx;
  font-weight: 700;

  &.win {
    color: #10b981;
  }

  &.lose {
    color: #ef4444;
  }
}

.act-link {
  font-size: 24rpx;
}

.act-link.settle {
  color: #0d9488;
  font-weight: 600;
}

.act-link.edit {
  color: #6b7280;
}

.act-link.del {
  color: #ef4444;
}
</style>
