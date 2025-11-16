<template>
  <view class="page-wrapper">
    <!-- 顶部渐变头部 -->
    <view class="header-section">
      <view class="header-top">
        <view class="title-wrapper">
          <view class="icon-wrapper">
            <text class="icon">📋</text>
          </view>
          <text class="title">投注记录</text>
        </view>
        <view class="header-btns">
          <button class="add-btn" @tap="showFormDialog">
            <text class="add-icon">+</text>
            <text class="btn-text">新增</text>
          </button>
        </view>
      </view>

      <!-- 统计卡片 -->
      <view class="stats-grid">
        <view class="stat-card">
          <view class="stat-label">
            <view class="stat-icon-wrapper">¥</view>
            <text>总投注</text>
          </view>
          <view class="stat-value">¥{{ totalAmount }}</view>
        </view>
        <view class="stat-card">
          <view class="stat-label">
            <view class="stat-icon-wrapper">#</view>
            <text>记录数</text>
          </view>
          <view class="stat-value">{{ betStore.bets.length }}</view>
        </view>
      </view>
    </view>

    <scroll-view class="content-wrapper" scroll-y>
      <!-- 标签切换 -->
      <view class="tabs-wrapper">
        <view class="tabs-list">
          <view class="tab-item" :class="{ active: activeTab === 'all' }" @tap="activeTab = 'all'"> 全部记录 </view>
          <view class="tab-item" :class="{ active: activeTab === 'parlay' }" @tap="activeTab = 'parlay'"> 串关记录 </view>
        </view>
      </view>

      <!-- 记录列表 -->
      <view class="records-section">
        <view v-if="displayedBets.length === 0" class="empty-state">
          <view class="empty-icon-wrapper">
            <text class="empty-icon">-</text>
          </view>
          <text class="empty-text">{{ activeTab === "parlay" ? "暂无串关记录" : "暂无投注记录" }}</text>
        </view>

        <view v-else class="bet-list">
          <view v-for="bet in displayedBets" :key="bet.id" class="bet-card">
            <!-- 卡片头部 -->
            <view class="card-header">
              <view class="header-left">
                <view class="badge-row">
                  <view class="badge" :class="bet.legs?.length > 1 ? 'parlay' : 'single'">
                    {{ bet.legs?.length > 1 ? getParlayTypeLabel(bet) : "单关" }}
                  </view>
                  <text class="league-text">
                    {{ bet.legs?.length > 1 ? `共${bet.legs.length}场` : bet.legs?.[0]?.league || "未知联赛" }}
                  </text>
                </view>
                <view class="match-title">{{ primaryMatch(bet) }}</view>
              </view>
              <view class="header-right">
                <view class="status-actions">
                  <view class="badges-row">
                    <view class="status-badge" :class="bet.status">
                      {{ statusText(bet) }}
                    </view>
                    <view class="result-badge" :class="bet.result" v-if="bet.status === 'settled'">
                      {{ resultText(bet) }}
                    </view>
                  </view>
                  <view class="action-btns">
                    <button v-if="bet.status !== 'saved' && bet.status !== 'settled'" class="icon-btn edit" @tap.stop="() => startEdit(bet)">
                      <text class="btn-icon">✎</text>
                    </button>
                    <button v-if="bet.status !== 'settled'" class="icon-btn delete" @tap.stop="() => removeBet(bet.id)">
                      <text class="btn-icon">×</text>
                    </button>
                  </view>
                </view>
              </view>
            </view>

            <!-- 串关详情 -->
            <view v-if="bet.legs?.length > 1" class="parlay-details">
              <view v-for="leg in bet.legs" :key="leg.id" class="parlay-match">
                <view class="parlay-teams">{{ formatTeams(leg) }}</view>
                <view class="parlay-info"> {{ leg.league || "未知" }} · {{ leg.betType }} · @{{ leg.odds }} </view>
              </view>
            </view>

            <!-- 卡片内容 -->
            <view class="card-content">
              <view class="info-row">
                <view class="calendar-icon">
                  <text>📅</text>
                </view>
                <text class="info-text">{{ formatDate(bet.legs?.[0]?.matchTime || bet.betTime) }}</text>
              </view>

              <view class="divider"></view>

              <view class="bottom-row">
                <view class="odds-section">
                  <text class="odds-label"> {{ bet.legs?.length === 1 ? `${bet.legs[0].betType} · ` : "" }}赔率 @{{ bet.odds }} </text>
                </view>
                <view class="amount-section">
                  <text class="amount-label">投注金额</text>
                  <text class="amount-value">¥{{ bet.stake }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- 表单弹窗 -->
    <view v-if="showDialog" class="dialog-overlay" @tap="closeDialog">
      <view class="dialog-content" @tap.stop>
        <view class="dialog-header">
          <text class="dialog-title">{{ editingBet ? "编辑投注记录" : "新增投注记录" }}</text>
          <button class="close-btn" @tap="closeDialog">×</button>
        </view>
        <scroll-view class="dialog-body" scroll-y>
          <BetForm ref="betFormRef" :editing-bet="editingBet" :is-editing-betting="isEditingBetting" :hide-submit-button="true" @submit="handleSubmit" @cancelEdit="cancelEdit" />
        </scroll-view>
        <view class="dialog-footer">
          <view v-if="isEditingBetting" class="footer-buttons">
            <button class="cancel-footer-btn" @tap="closeDialog">取消</button>
            <button class="settle-btn" @tap="handleSettle">结算</button>
          </view>
          <view v-else class="footer-buttons">
            <button class="save-footer-btn" @tap="() => submitFormWithStatus('saved')">保存</button>
            <button class="bet-footer-btn" @tap="() => submitFormWithStatus('betting')">投注</button>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import dayjs from "dayjs";
import BetForm from "@/components/BetForm.vue";
import { useBetStore } from "@/stores/betStore";
import { ref, computed } from "vue";

const betStore = useBetStore();
const editingBet = ref(null);
const activeTab = ref("all");
const showDialog = ref(false);
const betFormRef = ref(null);

// 判断是否在编辑"投注中"的记录
const isEditingBetting = computed(() => {
  return editingBet.value && editingBet.value.status === "betting";
});

// 计算总投注金额
const totalAmount = computed(() => {
  return betStore.bets.reduce((sum, bet) => sum + (Number(bet.stake) || 0), 0);
});

// 根据选中的标签过滤投注记录
const displayedBets = computed(() => {
  if (activeTab.value === "parlay") {
    return betStore.bets.filter((bet) => bet.legs?.length > 1);
  }
  return betStore.bets;
});

function showFormDialog() {
  editingBet.value = null;
  showDialog.value = true;
  // 打开新增弹窗时，确保表单是干净的
  setTimeout(() => {
    if (betFormRef.value && betFormRef.value.resetForm) {
      betFormRef.value.resetForm();
    }
  }, 50);
}

function closeDialog() {
  showDialog.value = false;
  editingBet.value = null;
  // 延迟重置表单，确保动画完成后再清空
  setTimeout(() => {
    if (betFormRef.value && betFormRef.value.resetForm) {
      betFormRef.value.resetForm();
    }
  }, 300);
}

function submitFormWithStatus(status) {
  // 触发 BetForm 的提交方法，传递状态
  if (betFormRef.value && betFormRef.value.handleSubmitWithStatus) {
    betFormRef.value.handleSubmitWithStatus(status);
  }
}

function handleSubmit(payload) {
  try {
    if (payload.id) {
      betStore.updateBet(payload.id, payload);
      editingBet.value = null;
      uni.showToast({ title: "记录已更新", icon: "success" });
    } else {
      betStore.addBet(payload);
      const statusText = payload.status === "betting" ? "投注成功" : "保存成功";
      uni.showToast({ title: statusText, icon: "success" });
    }
    closeDialog(); // closeDialog 中会自动重置表单
  } catch (error) {
    uni.showToast({ title: error.message || "操作失败", icon: "none" });
  }
}

// 处理结算
function handleSettle() {
  if (!editingBet.value) return;

  // 触发表单提交，将状态改为settled
  if (betFormRef.value && betFormRef.value.handleSubmitWithStatus) {
    betFormRef.value.handleSubmitWithStatus("settled");
  }
}

function removeBet(id) {
  uni.showModal({
    title: "删除记录",
    content: "确认删除这条投注记录吗？",
    success: (res) => {
      if (res.confirm) {
        if (editingBet.value?.id === id) {
          editingBet.value = null;
        }
        betStore.removeBet(id);
        uni.showToast({ title: "已删除", icon: "success" });
      }
    },
  });
}

function startEdit(bet) {
  // 已保存状态不允许编辑
  if (bet.status === "saved") {
    uni.showToast({ title: "已保存的记录不可编辑，只能删除", icon: "none" });
    return;
  }
  // 已结算状态不允许编辑
  if (bet.status === "settled") {
    uni.showToast({ title: "已结算的记录不可编辑", icon: "none" });
    return;
  }

  editingBet.value = bet;
  showDialog.value = true;
}

function cancelEdit() {
  editingBet.value = null;
  closeDialog();
}

function formatDate(value) {
  if (!value) return "-";
  return dayjs(value).format("MM-DD HH:mm");
}

function resultText(bet) {
  const dict = {
    win: "全赢",
    lose: "全输",
    pending: "进行中",
    "half-win": "赢半",
    "half-lose": "输半",
  };
  return dict[bet.result] || "未知";
}

function statusText(bet) {
  const dict = {
    saved: "已保存",
    betting: "投注中",
    settled: "已结算",
  };
  return dict[bet.status] || "未知";
}

function primaryMatch(bet) {
  const legs = bet.legs || [];
  if (!legs.length) {
    return bet.matchName || "未命名比赛";
  }
  const title = formatTeams(legs[0]);
  if (legs.length === 1) return title;
  return `${title}`;
}

function formatTeams(leg) {
  const home = leg?.homeTeam || "主队";
  const away = leg?.awayTeam || "客队";
  return `${home} vs ${away}`;
}

function formatSelection(leg) {
  if (leg?.selection) return leg.selection;
  if (leg?.betType === "大小球") return "大小盘";
  if (leg?.betType === "让球") return "盘口方向";
  return "投注方向";
}

function getParlayTypeLabel(bet) {
  if (!bet.legs || bet.legs.length < 2) return "单关";

  // 如果有保存的parlayType，使用它
  if (bet.parlayType) {
    const [m, n] = bet.parlayType.split("_");
    return `${m}串${n}`;
  }

  // 否则默认显示N串1
  return `${bet.legs.length}串1`;
}
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

/* 页面容器 */
.page-wrapper {
  min-height: 100vh;
  width: 100%;
  max-width: 100vw;
  overflow-x: hidden;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

/* ========== 顶部头部区域 ========== */
.header-section {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  padding: 40rpx 24rpx 24rpx;
  border-radius: 0 0 24rpx 24rpx;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.15);
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24rpx;
  width: 100%;
}

.title-wrapper {
  display: flex;
  align-items: center;
  gap: 10rpx;
  flex: 1;
}

.icon-wrapper {
  width: 36rpx;
  height: 36rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 8rpx;
}

.icon {
  font-size: 20rpx;
  line-height: 1;
}

.title {
  font-size: 36rpx;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: 0.5rpx;
}

.header-btns {
  display: flex;
  align-items: center;
  gap: 10rpx;
  flex-shrink: 0;
  margin-left: 16rpx;
}

.add-btn {
  background: #ffffff;
  color: #0d9488;
  border-radius: 12rpx;
  padding: 6rpx 16rpx;
  font-size: 24rpx;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.1);
  border: none;
  flex-shrink: 0;
  transition: all 0.2s ease;
  height: 52rpx;
  line-height: 1;
}

.add-btn:active {
  transform: scale(0.98);
  box-shadow: 0 1rpx 4rpx rgba(0, 0, 0, 0.1);
}

.add-icon {
  font-size: 26rpx;
  font-weight: 700;
}

.btn-text {
  line-height: 1;
}

/* 统计卡片网格 */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16rpx;
}

.stat-card {
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(10px);
  border-radius: 16rpx;
  padding: 18rpx;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.stat-label {
  display: flex;
  align-items: center;
  gap: 6rpx;
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.85);
  margin-bottom: 10rpx;
}

.stat-icon-wrapper {
  width: 28rpx;
  height: 28rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 6rpx;
  font-size: 18rpx;
  font-weight: 600;
  color: #ffffff;
}

.stat-value {
  font-size: 36rpx;
  font-weight: 700;
  color: #ffffff;
}

/* ========== 内容区域 ========== */
.content-wrapper {
  flex: 1;
  padding: 0 24rpx 24rpx;
  box-sizing: border-box;
  width: 100%;
}

/* 标签切换 */
.tabs-wrapper {
  margin: 24rpx 0 20rpx;
}

.tabs-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  background: #ffffff;
  border-radius: 14rpx;
  padding: 4rpx;
  border: 1px solid rgba(13, 148, 136, 0.1);
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}

.tab-item {
  padding: 14rpx;
  text-align: center;
  font-size: 26rpx;
  font-weight: 500;
  color: #6b7280;
  border-radius: 10rpx;
  transition: all 0.3s;
}

.tab-item.active {
  background: #0d9488;
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);
}

/* ========== 记录列表区域 ========== */
.records-section {
  padding-bottom: 24rpx;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100rpx 0;
  background: #ffffff;
  border-radius: 16rpx;
  border: 1px solid rgba(13, 148, 136, 0.1);
}

.empty-icon-wrapper {
  width: 80rpx;
  height: 80rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(13, 148, 136, 0.1) 0%, rgba(20, 184, 166, 0.1) 100%);
  border-radius: 50%;
  margin-bottom: 20rpx;
}

.empty-icon {
  font-size: 40rpx;
  color: #0d9488;
  opacity: 0.5;
}

.empty-text {
  font-size: 26rpx;
  color: #9ca3af;
}

/* 投注卡片列表 */
.bet-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.bet-card {
  background: #ffffff;
  border-radius: 16rpx;
  padding: 20rpx;
  border: 1px solid rgba(13, 148, 136, 0.1);
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
  width: 100%;
}

/* 卡片头部 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16rpx;
}

.header-left {
  flex: 1;
}

.badge-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 12rpx;
}

.badge {
  display: inline-flex;
  padding: 6rpx 16rpx;
  border-radius: 10rpx;
  font-size: 22rpx;
  font-weight: 600;
  color: #ffffff;
}

.badge.parlay {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
}

.badge.single {
  background: #e5e7eb;
  color: #374151;
}

.league-text {
  font-size: 22rpx;
  color: #9ca3af;
}

.match-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #111827;
  line-height: 1.4;
  word-break: break-all;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.header-right {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  margin-left: 16rpx;
  align-items: flex-end;
}

.status-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12rpx;
}

.action-btns {
  display: flex;
  gap: 12rpx;
}

.icon-btn {
  width: 48rpx;
  height: 48rpx;
  border-radius: 10rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  padding: 0;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.icon-btn:active {
  transform: scale(0.95);
}

.icon-btn.edit {
  background: rgba(13, 148, 136, 0.1);
}

.icon-btn.delete {
  background: rgba(239, 68, 68, 0.1);
}

.btn-icon {
  font-size: 24rpx;
  font-weight: 600;
  color: #0d9488;
}

.icon-btn.delete .btn-icon {
  color: #ef4444;
  font-size: 28rpx;
}

/* 串关详情 */
.parlay-details {
  background: linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%);
  border-radius: 12rpx;
  padding: 16rpx;
  margin-bottom: 16rpx;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.parlay-match {
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.parlay-teams {
  font-size: 26rpx;
  font-weight: 600;
  color: #065f46;
}

.parlay-info {
  font-size: 22rpx;
  color: #047857;
}

/* 卡片内容 */
.card-content {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.calendar-icon {
  width: 40rpx;
  height: 40rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(13, 148, 136, 0.1) 0%, rgba(20, 184, 166, 0.1) 100%);
  border-radius: 8rpx;
  font-size: 20rpx;
  flex-shrink: 0;
}

.info-text {
  font-size: 24rpx;
  color: #6b7280;
}

.divider {
  height: 1px;
  background: rgba(13, 148, 136, 0.1);
  margin: 10rpx 0;
}

.bottom-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.odds-section {
  flex: 1;
}

.odds-label {
  font-size: 24rpx;
  color: #6b7280;
}

.amount-section {
  text-align: right;
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 8rpx;
}

.amount-label {
  font-size: 24rpx;
  color: #6b7280;
  white-space: nowrap;
}

.amount-value {
  font-size: 32rpx;
  font-weight: 700;
  color: #0d9488;
  white-space: nowrap;
}

/* 结果徽章 */
.result-badge {
  display: inline-flex;
  padding: 4rpx 12rpx;
  border-radius: 8rpx;
  font-size: 20rpx;
  font-weight: 600;
  color: #ffffff;
  white-space: nowrap;
  flex-shrink: 0;
}

.result-badge.win {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.result-badge.lose {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

.result-badge.pending {
  background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
}

.result-badge.half-win {
  background: linear-gradient(135deg, #84cc16 0%, #65a30d 100%);
}

.result-badge.half-lose {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

/* 徽章容器 */
.badges-row {
  display: flex;
  align-items: center;
  gap: 8rpx;
  margin-bottom: 8rpx;
}

/* 状态徽章 */
.status-badge {
  display: inline-flex;
  padding: 4rpx 12rpx;
  border-radius: 8rpx;
  font-size: 20rpx;
  font-weight: 600;
  color: #ffffff;
  white-space: nowrap;
  flex-shrink: 0;
}

.status-badge.saved {
  background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
}

.status-badge.betting {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.status-badge.settled {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
}

/* ========== 弹窗样式 ========== */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  z-index: 500;
  padding: 0;
}

.dialog-content {
  background: #ffffff;
  border-radius: 32rpx 32rpx 0 0;
  width: 100vw;
  max-width: 100%;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 -8rpx 32rpx rgba(0, 0, 0, 0.15);
  animation: slideUp 0.3s ease-out;
  box-sizing: border-box;
}

@keyframes slideUp {
  from {
    transform: translateY(100%);
  }
  to {
    transform: translateY(0);
  }
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24rpx;
  border-bottom: 1px solid rgba(13, 148, 136, 0.1);
  flex-shrink: 0;
  box-sizing: border-box;
}

.dialog-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #0d9488;
  flex: 1;
}

.close-btn {
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: rgba(13, 148, 136, 0.1);
  border: none;
  font-size: 40rpx;
  color: #0d9488;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
  margin-left: 20rpx;
}

.close-btn:active {
  background: rgba(13, 148, 136, 0.2);
}

.dialog-body {
  flex: 1;
  padding: 24rpx;
  overflow-y: auto;
  box-sizing: border-box;
}

.dialog-footer {
  padding: 16rpx 24rpx;
  padding-bottom: calc(16rpx + env(safe-area-inset-bottom));
  border-top: 1px solid rgba(13, 148, 136, 0.1);
  background: #ffffff;
  flex-shrink: 0;
  box-sizing: border-box;
}

.footer-buttons {
  display: flex;
  gap: 12rpx;
  width: 100%;

  button {
    flex: 1;
    height: 72rpx;
    border-radius: 12rpx;
    font-size: 26rpx;
    font-weight: 600;
    border: none;
    transition: all 0.2s;
    box-sizing: border-box;
  }
}

.save-footer-btn {
  background: #f5f5f5;
  color: #666;

  &:active {
    background: #e5e5e5;
    transform: translateY(1rpx);
  }
}

.bet-footer-btn {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.3);

  &:active {
    transform: translateY(1rpx);
    box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);
  }
}

.cancel-footer-btn {
  background: #f5f5f5;
  color: #666;

  &:active {
    background: #e5e5e5;
    transform: translateY(1rpx);
  }
}

.settle-btn {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: #ffffff;
  box-shadow: 0 4rpx 16rpx rgba(16, 185, 129, 0.3);

  &:active {
    transform: translateY(1rpx);
    box-shadow: 0 2rpx 8rpx rgba(16, 185, 129, 0.3);
  }
}
</style>
