<template>
  <view class="page-wrapper">
    <scroll-view class="page" scroll-y>
      <view class="section">
        <text class="section-title">策略参数</text>
        <view class="form-card">
          <view class="field">
            <text>初始资金 (¥)</text>
            <input type="number" v-model.number="form.startingCapital" />
          </view>
          <view class="field">
            <text>固定比例 (%)</text>
            <input type="number" v-model.number="form.fixedRatio" />
          </view>
          <view class="field">
            <text>凯利调整系数</text>
            <input type="number" v-model.number="form.kellyFactor" />
          </view>
          <view class="field">
            <text>止损次数</text>
            <input type="number" v-model.number="form.stopLossLimit" />
          </view>
          <view class="field">
            <text>月度盈利目标 (%)</text>
            <input type="number" v-model.number="form.targetMonthlyReturn" />
          </view>
          <view class="field">
            <text>主题</text>
            <picker mode="selector" :range="themes" @change="onThemeChange">
              <view class="picker-value">{{ themeLabel }}</view>
            </picker>
          </view>
          <button class="primary-btn" @tap="handleSave">保存设置</button>
        </view>
      </view>

      <view class="section">
        <text class="section-title">数据导出</text>
        <view class="form-card">
          <button class="primary-btn" @tap="exportCsv">导出 CSV</button>
          <text class="hint">导出的 CSV 会复制到剪贴板，可直接粘贴到 Excel。</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import dayjs from "dayjs";
import { computed, reactive, watch } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { useConfigStore } from "@/stores/configStore";
import { useBetStore } from "@/stores/betStore";

const config = useConfigStore();
const betStore = useBetStore();

const themes = ["light", "dark"];

const form = reactive({
  startingCapital: 10000,
  fixedRatio: 3,
  kellyFactor: 0.5,
  stopLossLimit: 3,
  targetMonthlyReturn: 10,
  theme: "light",
});

watch(
  () => ({
    startingCapital: config.startingCapital,
    fixedRatio: config.fixedRatio,
    kellyFactor: config.kellyFactor,
    stopLossLimit: config.stopLossLimit,
    targetMonthlyReturn: config.targetMonthlyReturn,
    theme: config.theme,
  }),
  (value) => {
    form.startingCapital = Number(value.startingCapital);
    form.fixedRatio = Number(value.fixedRatio) * 100;
    form.kellyFactor = Number(value.kellyFactor);
    form.stopLossLimit = Number(value.stopLossLimit);
    form.targetMonthlyReturn = Number(value.targetMonthlyReturn) * 100;
    form.theme = value.theme;
  },
  { immediate: true }
);

const themeLabel = computed(() => (form.theme === "dark" ? "深色" : "浅色"));

function onThemeChange(event) {
  form.theme = themes[Number(event.detail.value)];
}

function handleSave() {
  config.updateConfig({
    startingCapital: form.startingCapital,
    fixedRatio: form.fixedRatio / 100,
    kellyFactor: form.kellyFactor,
    stopLossLimit: form.stopLossLimit,
    targetMonthlyReturn: form.targetMonthlyReturn / 100,
    theme: form.theme,
  });
  uni.showToast({ title: "已保存", icon: "success" });
}

function formatLegForExport(leg) {
  const teams = [leg.homeTeam, leg.awayTeam].filter(Boolean).join(" vs ") || "未命名";
  const schedule = leg.matchTime ? dayjs(leg.matchTime).format("MM-DD HH:mm") : "-";
  const selection = leg.selection ? `/${leg.selection}` : "";
  return `${teams}|${leg.league || "-"}|${schedule}|${leg.betType}${selection}@${leg.odds}`;
}

function exportCsv() {
  if (!betStore.bets.length) {
    uni.showToast({ title: "暂无数据", icon: "none" });
    return;
  }
  const header = ["模式", "赛事详情", "投注额", "赔率", "结果", "盈亏", "下注时间"];
  const rows = betStore.bets.map((bet) => [bet.wagerType === "parlay" ? `串关(${bet.legs?.length || 0})` : "单关", (bet.legs || []).map(formatLegForExport).join(" / "), bet.stake, bet.odds, bet.result, bet.profit, bet.betTime].join(","));
  const csv = [header.join(","), ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      uni.showToast({ title: "已复制", icon: "success" });
    },
  });
}

onShow(() => {
  uni.$emit("tab-active", "profile");
});
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.page-wrapper {
  min-height: 100vh;
  position: relative;
  padding-bottom: 32rpx;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
}

.page {
  padding: 24rpx;
  box-sizing: border-box;
}

.section {
  margin-bottom: 24rpx;
}

.section-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 20rpx;
}

.form-card {
  @include card;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
  padding: 20rpx;
  margin-top: 10rpx;
}

.form-card .primary-btn {
  width: 100%;
  padding: 4rpx 0;
  margin-top: 8rpx;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.field text {
  font-size: 24rpx;
  color: #374151;
  font-weight: 500;
}

input,
.picker-value {
  background: #f9fafb;
  border-radius: 10rpx;
  padding: 12rpx 14rpx;
  border: 1px solid rgba(13, 148, 136, 0.15);
  transition: all 0.3s;
  font-size: 26rpx;
}

input:focus {
  border-color: #0d9488;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
}

.hint {
  font-size: 22rpx;
  color: #9ca3af;
  line-height: 1.5;
}
</style>
