<template>
  <view class="page-wrapper">
    <scroll-view class="page" scroll-y>
      <!-- 风险策略选择 -->
      <view class="section">
        <text class="section-title">风险策略</text>
        <view class="form-card">
          <view class="risk-levels">
            <view
              v-for="level in riskLevels"
              :key="level.key"
              class="risk-card"
              :class="{ active: form.riskLevel === level.key }"
              @tap="selectRiskLevel(level.key)"
            >
              <text class="risk-name">{{ level.label }}</text>
              <text class="risk-desc">{{ level.desc }}</text>
            </view>
          </view>

          <view class="params-preview">
            <view class="param-row">
              <text class="param-label">单注上限</text>
              <text class="param-value">{{ form.fixedRatio }}% 资金池</text>
            </view>
            <view class="param-row">
              <text class="param-label">Kelly系数</text>
              <text class="param-value">{{ form.kellyFactor }}</text>
            </view>
            <view class="param-row">
              <text class="param-label">连败止损</text>
              <text class="param-value">{{ form.stopLossLimit }} 场</text>
            </view>
            <view class="param-row">
              <text class="param-label">最低置信度</text>
              <text class="param-value">{{ form.minConfidence }}%</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 资金设置 -->
      <view class="section">
        <text class="section-title">资金设置</text>
        <view class="form-card">
          <view class="field">
            <text class="field-label">初始资金 (¥)</text>
            <input type="number" v-model.number="form.startingCapital" />
          </view>
          <view class="field">
            <text class="field-label">月度盈利目标 (%)</text>
            <input type="number" v-model.number="form.targetMonthlyReturn" />
          </view>
        </view>
      </view>

      <!-- 资金分层与控手 -->
      <view class="section">
        <text class="section-title">资金分层与控手</text>
        <view class="form-card">
          <view class="field">
            <text class="field-label">盈利金计入系数 (%)</text>
            <input type="number" v-model.number="form.profitAggressiveRatio" />
            <text class="field-hint">盈利金按此比例计入有效资金(50=半数,越低越保守,抑制仓位雪球)</text>
          </view>
          <view class="field">
            <text class="field-label">出金阀阈值 (%)</text>
            <input type="number" v-model.number="form.withdrawThreshold" />
            <text class="field-hint">盈利金达本金此比例时提示出金落袋</text>
          </view>
          <view class="field">
            <text class="field-label">出金提取比例 (%)</text>
            <input type="number" v-model.number="form.withdrawRatio" />
            <text class="field-hint">触发出金时建议提取盈利金的比例</text>
          </view>
          <view class="field">
            <text class="field-label">冷静时长 (小时)</text>
            <input type="number" v-model.number="form.coolHours" />
            <text class="field-hint">连不中暂停后需冷静多久才能恢复下注</text>
          </view>
          <view class="field">
            <text class="field-label">控手阈值 (高/中/低 信心档连不中把数)</text>
            <view class="tier-thresholds">
              <input type="number" v-model.number="form.tierThresholdHigh" placeholder="高" />
              <input type="number" v-model.number="form.tierThresholdMid" placeholder="中" />
              <input type="number" v-model.number="form.tierThresholdLow" placeholder="低" />
            </view>
            <text class="field-hint">高信心档最早触发(默认 3/4/5,再+1 把隐藏下注入口)</text>
          </view>
        </view>
      </view>

      <!-- 高级参数 -->
      <view class="section">
        <view class="section-header" @tap="showAdvanced = !showAdvanced">
          <text class="section-title">高级参数</text>
          <text class="toggle-arrow">{{ showAdvanced ? '收起' : '展开' }}</text>
        </view>
        <view class="form-card" v-if="showAdvanced">
          <view class="field">
            <text class="field-label">固定比例 (%)</text>
            <input type="number" v-model.number="form.fixedRatio" @input="form.riskLevel = 'custom'" />
          </view>
          <view class="field">
            <text class="field-label">凯利调整系数</text>
            <input type="number" v-model.number="form.kellyFactor" @input="form.riskLevel = 'custom'" />
          </view>
          <view class="field">
            <text class="field-label">止损次数</text>
            <input type="number" v-model.number="form.stopLossLimit" @input="form.riskLevel = 'custom'" />
          </view>
          <view class="field">
            <text class="field-label">最低置信度 (%)</text>
            <input type="number" v-model.number="form.minConfidence" @input="form.riskLevel = 'custom'" />
          </view>
          <text class="field-hint">手动修改参数后策略变为"自定义"</text>
        </view>
      </view>

      <!-- 保存按钮 -->
      <view class="section">
        <button class="save-btn" @tap="handleSave">保存设置</button>
      </view>

      <!-- 数据导出 -->
      <view class="section">
        <text class="section-title">数据导出</text>
        <view class="form-card">
          <button class="export-btn" @tap="exportCsv">导出 CSV</button>
          <text class="field-hint">导出的 CSV 会复制到剪贴板，可直接粘贴到 Excel。</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import dayjs from "dayjs";
import { computed, reactive, ref, watch } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { useConfigStore } from "@/stores/configStore";
import { useBetStore } from "@/stores/betStore";
import { requireAuth } from "@/utils/auth";
import { getStrategyPreset, getAllPresets } from "@/utils/strategyEngine";

const config = useConfigStore();
const betStore = useBetStore();
const showAdvanced = ref(false);

const riskLevels = [
  { key: 'conservative', label: '保守', desc: '低风险，稳定为主' },
  { key: 'balanced', label: '稳健', desc: '均衡收益与风险' },
  { key: 'aggressive', label: '激进', desc: '高收益，高波动' },
];

const form = reactive({
  startingCapital: 10000,
  fixedRatio: 5,
  kellyFactor: 0.5,
  stopLossLimit: 3,
  targetMonthlyReturn: 10,
  minConfidence: 60,
  riskLevel: 'balanced',
  // 资金分层与控手(百分比/数值)
  profitAggressiveRatio: 50,
  withdrawThreshold: 30,
  withdrawRatio: 50,
  coolHours: 2,
  tierThresholdHigh: 3,
  tierThresholdMid: 4,
  tierThresholdLow: 5,
});

function selectRiskLevel(level) {
  form.riskLevel = level;
  const preset = getStrategyPreset(level);
  form.fixedRatio = preset.maxRatio * 100;
  form.kellyFactor = preset.kellyFactor;
  form.stopLossLimit = preset.stopLossLimit;
  form.minConfidence = preset.minConfidence;
}

watch(
  () => ({
    startingCapital: config.startingCapital,
    fixedRatio: config.fixedRatio,
    kellyFactor: config.kellyFactor,
    stopLossLimit: config.stopLossLimit,
    targetMonthlyReturn: config.targetMonthlyReturn,
    riskTolerance: config.riskTolerance,
  }),
  (value) => {
    form.startingCapital = Number(value.startingCapital);
    form.fixedRatio = Number(value.fixedRatio) * 100;
    form.kellyFactor = Number(value.kellyFactor);
    form.stopLossLimit = Number(value.stopLossLimit);
    form.targetMonthlyReturn = Number(value.targetMonthlyReturn) * 100;
    form.riskLevel = value.riskTolerance || 'balanced';
    const preset = getStrategyPreset(form.riskLevel);
    // 自定义模式保留用户已设置的 minConfidence；命名预设用预设值
    form.minConfidence = form.riskLevel === 'custom'
      ? (config.minConfidence || preset.minConfidence)
      : preset.minConfidence;
    form.profitAggressiveRatio = Number(config.profitAggressiveRatio) * 100;
    form.withdrawThreshold = Number(config.withdrawThreshold) * 100;
    form.withdrawRatio = Number(config.withdrawRatio) * 100;
    form.coolHours = Number(config.coolHours);
    form.tierThresholdHigh = config.tierThresholds?.high ?? 3;
    form.tierThresholdMid = config.tierThresholds?.mid ?? 4;
    form.tierThresholdLow = config.tierThresholds?.low ?? 5;
  },
  { immediate: true }
);

async function handleSave() {
  try {
    await config.updateConfig({
      startingCapital: form.startingCapital,
      fixedRatio: form.fixedRatio / 100,
      kellyFactor: form.kellyFactor,
      stopLossLimit: form.stopLossLimit,
      targetMonthlyReturn: form.targetMonthlyReturn / 100,
      riskTolerance: form.riskLevel,
      minConfidence: form.minConfidence,
      profitAggressiveRatio: form.profitAggressiveRatio / 100,
      withdrawThreshold: form.withdrawThreshold / 100,
      withdrawRatio: form.withdrawRatio / 100,
      coolHours: form.coolHours,
      tierThresholds: { high: form.tierThresholdHigh, mid: form.tierThresholdMid, low: form.tierThresholdLow },
    });
    uni.showToast({ title: "已保存", icon: "success" });
  } catch (error) {
    uni.showToast({ title: error.message || "保存失败", icon: "none" });
  }
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
  if (!requireAuth()) return;
});
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.page-wrapper {
  min-height: 100vh;
  background: #f4f5f7;
}

.page {
  padding: 24rpx;
  box-sizing: border-box;
  min-height: 100vh;
}

.section {
  margin-bottom: 28rpx;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #374151;
  margin-bottom: 16rpx;
}

.toggle-arrow {
  font-size: 24rpx;
  color: #0d9488;
  margin-bottom: 16rpx;
}

.form-card {
  background: #fff;
  border-radius: 6rpx;
  padding: 24rpx;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

/* 风险策略卡片 */
.risk-levels {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12rpx;
  margin-bottom: 24rpx;
}

.risk-card {
  padding: 20rpx 12rpx;
  border: 2px solid #e5e7eb;
  border-radius: 6rpx;
  text-align: center;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 6rpx;

  &.active {
    border-color: #0d9488;
    background: #f0fdfa;
  }

  &:active {
    transform: scale(0.97);
  }
}

.risk-name {
  font-size: 26rpx;
  font-weight: 600;
  color: #1f2937;
}

.risk-card.active .risk-name {
  color: #0d9488;
}

.risk-desc {
  font-size: 20rpx;
  color: #9ca3af;
}

/* 参数预览 */
.params-preview {
  padding: 16rpx 0 0;
  border-top: 1px solid #f3f4f6;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.param-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.param-label {
  font-size: 24rpx;
  color: #6b7280;
}

.param-value {
  font-size: 24rpx;
  color: #1f2937;
  font-weight: 500;
}

/* 表单字段 */
.field {
  margin-bottom: 16rpx;

  &:last-child {
    margin-bottom: 0;
  }
}

.field-label {
  font-size: 24rpx;
  color: #374151;
  font-weight: 500;
  margin-bottom: 8rpx;
  display: block;
}

.field-hint {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 12rpx;
  display: block;
}

.tier-thresholds {
  display: flex;
  gap: 12rpx;

  input {
    flex: 1;
    text-align: center;
  }
}

input {
  background: #f9fafb;
  border-radius: 6rpx;
  padding: 16rpx;
  border: 1px solid #e5e7eb;
  font-size: 26rpx;
  color: #1f2937;
  transition: border-color 0.2s;

  &:focus {
    border-color: #0d9488;
    background: #fff;
  }
}

/* 按钮 */
.save-btn {
  width: 100%;
  height: 80rpx;
  background: #0d9488;
  color: #fff;
  font-size: 28rpx;
  font-weight: 600;
  border-radius: 6rpx;
  border: none;
  line-height: 80rpx;

  &:active {
    background: #0f766e;
  }
}

.export-btn {
  width: 100%;
  height: 72rpx;
  background: #f3f4f6;
  color: #374151;
  font-size: 26rpx;
  font-weight: 500;
  border-radius: 6rpx;
  border: none;
  line-height: 72rpx;
  margin-bottom: 8rpx;

  &:active {
    background: #e5e7eb;
  }
}
</style>
