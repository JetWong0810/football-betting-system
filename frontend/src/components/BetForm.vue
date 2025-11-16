<template>
  <view class="bet-form">
    <view v-if="isEditing" class="editing-banner">
      <text>{{ isEditingBetting ? "正在编辑投注中的记录（只能修改投注结果）" : "正在编辑已保存的记录" }}</text>
      <button class="ghost-btn" @tap="handleCancelEdit">取消</button>
    </view>

    <view v-if="!isFieldsDisabled" class="legs-wrapper">
      <view v-for="(leg, index) in form.legs" :key="leg.id" class="leg-card">
        <view class="leg-header">
          <text class="leg-title">赛事 {{ index + 1 }}</text>
          <button v-if="form.legs.length > 1" class="ghost-btn small" @tap="() => removeLeg(leg.id)">删除</button>
        </view>

        <view class="field inline">
          <view class="inline-item">
            <text class="label">主队</text>
            <input v-model="leg.homeTeam" placeholder="主队名称" />
          </view>
          <view class="inline-item">
            <text class="label">客队</text>
            <input v-model="leg.awayTeam" placeholder="客队名称" />
          </view>
        </view>

        <view class="field inline">
          <view class="inline-item">
            <text class="label">联赛</text>
            <input v-model="leg.league" placeholder="英超 / 欧冠..." />
          </view>
          <view class="inline-item">
            <text class="label">比赛时间</text>
            <picker class="picker-wrapper" mode="date" :value="leg.matchDate || currentDate" @change="(e) => onLegDateChange(leg.id, e.detail.value)" :start="currentDate">
              <view class="picker-value">{{ leg.matchDate || "选择日期" }}</view>
            </picker>
          </view>
        </view>

        <view class="field inline">
          <view class="inline-item">
            <text class="label">投注类型</text>
            <picker class="picker-wrapper" mode="selector" :range="betTypeOptions" @change="(e) => onLegBetTypeChange(leg.id, e.detail.value)">
              <view class="picker-value">{{ leg.betType }}</view>
            </picker>
          </view>
          <view class="inline-item">
            <text class="label">投注方向</text>
            <input v-model="leg.selection" placeholder="例：主胜 / 大3" />
          </view>
        </view>

        <view class="field">
          <text class="label">赔率</text>
          <input type="digit" v-model="leg.odds" placeholder="例：1.85" />
        </view>

      </view>
    </view>

    <button v-if="!isFieldsDisabled" class="secondary-btn" @tap="addLeg">+ 添加赛事</button>

    <!-- 串关方式选择（横向滚动） -->
    <view v-if="isParlay && !isFieldsDisabled" class="parlay-selector">
      <view class="selector-label">过关方式</view>
      <scroll-view class="parlay-options" scroll-x>
        <view 
          v-for="option in parlayTypeOptions" 
          :key="option.value"
          class="parlay-option"
          :class="{ active: form.parlayType === option.value }"
          @tap="() => selectParlayType(option.value)"
        >
          {{ option.label }}
        </view>
      </scroll-view>
    </view>

    <view v-if="!isFieldsDisabled" class="field inline">
      <view class="inline-item">
        <text class="label">下注金额 (¥)</text>
        <input type="digit" v-model="form.stake" placeholder="例：100" />
      </view>
      <view class="inline-item">
        <text class="label">总赔率</text>
        <input type="digit" v-model="form.odds" placeholder="例：1.85" :disabled="isParlay" />
      </view>
    </view>

    <!-- 串关信息提示 -->
    <view v-if="isParlay && !isFieldsDisabled" class="odds-info-row">
      <view class="info-item">
        <text class="info-label">计算赔率</text>
        <text class="info-value">@{{ calculatedOdds }}</text>
      </view>
      <view class="info-item" v-if="form.stake">
        <text class="info-label">最高可赢</text>
        <text class="info-value winning">¥{{ maxWinning }}</text>
      </view>
    </view>

    <!-- 单关信息提示 -->
    <view v-if="!isParlay && !isFieldsDisabled && form.stake && form.odds" class="odds-info-row">
      <view class="info-item">
        <text class="info-label">最高可赢金额</text>
        <text class="info-value winning">¥{{ maxWinning }}</text>
      </view>
    </view>

    <view class="field">
      <text class="label">投注结果</text>
      <picker class="picker-wrapper" mode="selector" :range="resultOptions" range-key="label" @change="onResultChange">
        <view class="picker-value">{{ resultLabel }}</view>
      </picker>
    </view>

    <!-- 表单验证提示（只在尝试提交后显示） -->
    <view v-if="!isFieldsDisabled && hasAttemptedSubmit && !isFormValid && formErrors.length > 0" class="validation-tips">
      <view class="tip-icon">⚠️</view>
      <view class="tip-content">
        <text class="tip-title">请完善以下信息：</text>
        <text class="tip-error">{{ formErrors[0] }}</text>
        <text v-if="formErrors.length > 1" class="tip-more">还有 {{ formErrors.length - 1 }} 项需要填写</text>
      </view>
    </view>

    <button v-if="!hideSubmitButton" class="primary-btn" @tap="handleSubmit">
      {{ isEditing ? "更新记录" : "保存记录" }}
    </button>
  </view>
</template>

<script setup>
import dayjs from "dayjs";
import { computed, reactive, ref, watch } from "vue";

const props = defineProps({
  editingBet: {
    type: Object,
    default: null,
  },
  hideSubmitButton: {
    type: Boolean,
    default: false,
  },
  isEditingBetting: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["submit", "cancelEdit"]);

const betTypeOptions = ["胜平负", "让球", "大小球", "角球", "单双", "其他"];
const resultOptions = [
  { label: "进行中", value: "pending" },
  { label: "全赢", value: "win" },
  { label: "全输", value: "lose" },
  { label: "赢半", value: "half-win" },
  { label: "输半", value: "half-lose" },
];
const resultDict = {
  pending: "进行中",
  win: "全赢",
  lose: "全输",
  "half-win": "赢半",
  "half-lose": "输半",
};

const form = reactive({
  id: "",
  stake: null,
  odds: null,
  result: "pending",
  betTime: dayjs().format("YYYY-MM-DD HH:mm"),
  legs: [createLeg()],
  parlayType: "2_1", // 默认2串1
});

// 是否已尝试提交（用于控制验证提示显示）
const hasAttemptedSubmit = ref(false);

const isEditing = computed(() => Boolean(form.id));
const isParlay = computed(() => form.legs.length > 1);
const resultLabel = computed(() => resultDict[form.result] || "进行中");

// 全部赛事连乘赔率（仅供参考）
const combinedOdds = computed(() => {
  const raw = form.legs.reduce((acc, leg) => acc * (Number(leg.odds) || 1), 1);
  return Number(raw.toFixed(2));
});

// 根据选择的串关方式计算实际赔率
const calculatedOdds = computed(() => {
  if (!isParlay.value) {
    // 单关直接返回总赔率或第一场赔率
    return Number(form.odds || form.legs[0]?.odds || 0);
  }
  
  // 解析串关方式（如 "3_1" 表示3串1）
  const [m, n] = form.parlayType.split("_");
  const parlaySize = parseInt(m); // 串关数
  const parlayCount = parseInt(n); // 注数（通常为1）
  
  // 获取有效赔率的赛事
  const validLegs = form.legs.filter(leg => leg.odds && Number(leg.odds) > 0);
  
  if (validLegs.length < parlaySize) {
    return 0; // 赔率不足
  }
  
  // N串1：取前N场的赔率连乘
  const selectedLegs = validLegs.slice(0, parlaySize);
  
  // 计算串关总赔率（连乘）
  const totalOdds = selectedLegs.reduce((acc, leg) => acc * Number(leg.odds), 1);
  
  return Number(totalOdds.toFixed(2));
});

// 最高可赢金额
const maxWinning = computed(() => {
  const stake = Number(form.stake) || 0;
  const odds = Number(form.odds) || 0;
  if (!stake || !odds) return 0;
  const winning = stake * odds;
  return Number(winning.toFixed(2));
});

// 编辑投注中的记录时，只能修改投注结果
const isFieldsDisabled = computed(() => props.isEditingBetting);

// 表单验证
const formErrors = computed(() => {
  const errors = [];
  
  // 验证赛事信息
  form.legs.forEach((leg, index) => {
    if (!leg.homeTeam?.trim()) {
      errors.push(`赛事${index + 1}：请填写主队名称`);
    }
    if (!leg.awayTeam?.trim()) {
      errors.push(`赛事${index + 1}：请填写客队名称`);
    }
    if (!leg.league?.trim()) {
      errors.push(`赛事${index + 1}：请填写联赛`);
    }
    if (!leg.matchDate) {
      errors.push(`赛事${index + 1}：请选择比赛时间`);
    }
    if (!leg.selection?.trim()) {
      errors.push(`赛事${index + 1}：请填写投注方向`);
    }
    if (!leg.odds || Number(leg.odds) <= 0) {
      errors.push(`赛事${index + 1}：请填写有效的赔率`);
    }
  });
  
  // 验证下注金额
  if (!form.stake || Number(form.stake) <= 0) {
    errors.push("请填写下注金额");
  }
  
  // 验证总赔率
  if (!form.odds || Number(form.odds) <= 0) {
    errors.push("请填写有效的总赔率");
  }
  
  return errors;
});

// 表单是否有效
const isFormValid = computed(() => formErrors.value.length === 0);

// 串关方式选项（2串1到N串1）
const parlayTypeOptions = computed(() => {
  const legsCount = form.legs.length;
  if (legsCount < 2) return [];
  
  const options = [];
  for (let i = 2; i <= legsCount; i++) {
    options.push({
      label: `${i}串1`,
      value: `${i}_1`
    });
  }
  return options;
});

// 当前选中的串关方式标签
const parlayTypeLabel = computed(() => {
  if (!isParlay.value) return "";
  const option = parlayTypeOptions.value.find(opt => opt.value === form.parlayType);
  return option ? option.label : `${form.legs.length}串1`;
});

// 当前日期（用于 picker 默认值）
const currentDate = computed(() => dayjs().format("YYYY-MM-DD"));

// 监听赛事数量变化，自动调整串关方式
watch(() => form.legs.length, (newLength, oldLength) => {
  if (newLength < 2) return;
  
  // 如果赛事数量增加，自动选择最大串关（N串1）
  if (newLength > oldLength) {
    form.parlayType = `${newLength}_1`;
    // 自动更新总赔率
    if (!isFieldsDisabled.value) {
      form.odds = calculatedOdds.value;
    }
  }
  
  // 如果赛事数量减少，检查当前选择是否还有效
  const [m] = form.parlayType.split("_");
  const currentM = parseInt(m);
  if (currentM > newLength) {
    form.parlayType = `${newLength}_1`;
    // 自动更新总赔率
    if (!isFieldsDisabled.value) {
      form.odds = calculatedOdds.value;
    }
  }
});

// 监听串关方式变化，自动更新赔率
watch(() => form.parlayType, () => {
  if (isParlay.value && !isFieldsDisabled.value) {
    form.odds = calculatedOdds.value;
  }
});

// 监听赛事赔率变化，自动更新总赔率
watch(() => form.legs.map(leg => leg.odds), () => {
  if (isParlay.value && !isFieldsDisabled.value) {
    form.odds = calculatedOdds.value;
  }
}, { deep: true });

watch(
  () => props.editingBet,
  (bet) => {
    if (bet && bet.id) {
      hydrate(bet);
    } else if (!bet) {
      reset();
    }
  },
  { immediate: true }
);

function createLeg(overrides = {}) {
  return {
    id: overrides.id || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    homeTeam: overrides.homeTeam || "",
    awayTeam: overrides.awayTeam || "",
    league: overrides.league || "",
    matchDate: overrides.matchDate || overrides.matchTime?.split(" ")[0] || "",
    betType: overrides.betType || "胜平负",
    selection: overrides.selection || "",
    odds: overrides.odds !== undefined ? Number(overrides.odds) : null,
  };
}

function hydrate(bet) {
  form.id = bet.id;
  form.stake = Number(bet.stake || 0);
  form.odds = Number(bet.odds || 1);
  form.result = bet.result || "pending";
  form.parlayType = bet.parlayType || `${bet.legs?.length || 2}_1`;
  const sourceLegs =
    Array.isArray(bet.legs) && bet.legs.length
      ? bet.legs
      : [
          createLeg({
            homeTeam: bet.matchName?.split(" vs ")[0] || bet.matchName,
            awayTeam: bet.matchName?.split(" vs ")[1] || "",
            league: bet.league,
            matchDate: bet.betTime?.split(" ")[0] || "",
            betType: bet.betType,
          }),
        ];
  form.legs = sourceLegs.map((leg) => createLeg(leg));
}

function addLeg() {
  form.legs = [...form.legs, createLeg()];
  // 添加赛事后，如果是串关，自动更新赔率
  if (isParlay.value && !isFieldsDisabled.value) {
    // 等待下一个tick，确保串关选项已更新
    setTimeout(() => {
      form.odds = calculatedOdds.value;
    }, 0);
  }
}

function removeLeg(legId) {
  if (form.legs.length === 1) {
    uni.showToast({ title: "至少保留一场赛事", icon: "none" });
    return;
  }
  form.legs = form.legs.filter((leg) => leg.id !== legId);
}

function onLegBetTypeChange(legId, valueIndex) {
  const leg = form.legs.find((item) => item.id === legId);
  if (leg) {
    leg.betType = betTypeOptions[Number(valueIndex)];
  }
}

function onLegDateChange(legId, value) {
  const leg = form.legs.find((item) => item.id === legId);
  if (leg) {
    leg.matchDate = value;
  }
}

function onResultChange(event) {
  const index = Number(event.detail.value);
  form.result = resultOptions[index].value;
}

function selectParlayType(value) {
  form.parlayType = value;
  // 选择串关方式后自动更新赔率
  if (!isFieldsDisabled.value) {
    form.odds = calculatedOdds.value;
  }
}

function normalizePayload(status) {
  return {
    id: form.id || undefined,
    wagerType: form.legs.length > 1 ? "parlay" : "single",
    stake: form.stake ? Number(form.stake) : 0,
    odds: form.odds ? Number(form.odds) : 0,
    result: form.result,
    betTime: form.betTime,
    status: status || undefined,
    parlayType: form.legs.length > 1 ? form.parlayType : undefined,
    legs: form.legs.map((leg) => ({
      ...leg,
      odds: leg.odds ? Number(leg.odds) : 0,
    })),
  };
}

function reset() {
  form.id = "";
  form.stake = null;
  form.odds = null;
  form.result = "pending";
  form.betTime = dayjs().format("YYYY-MM-DD HH:mm");
  form.legs = [createLeg()];
  form.parlayType = "2_1";
  // 重置提交尝试标记
  hasAttemptedSubmit.value = false;
}

function handleCancelEdit() {
  emit("cancelEdit");
  reset();
}

function validateForm() {
  // 标记已尝试提交
  hasAttemptedSubmit.value = true;
  
  if (!form.legs.length) {
    uni.showToast({ title: "请至少添加一场赛事", icon: "none", duration: 2000 });
    return false;
  }
  
  if (!isFormValid.value) {
    // 显示第一个错误
    uni.showToast({ 
      title: formErrors.value[0], 
      icon: "none",
      duration: 2500
    });
    return false;
  }
  
  return true;
}

function handleSubmit() {
  if (!validateForm()) return;
  
  emit("submit", normalizePayload());
  if (!isEditing.value) {
    reset();
  }
}

function handleSubmitWithStatus(status) {
  // 编辑投注中的记录时，只需验证投注结果
  if (isFieldsDisabled.value) {
    emit("submit", normalizePayload(status));
    return;
  }
  
  if (!validateForm()) return;
  
  emit("submit", normalizePayload(status));
  if (!isEditing.value) {
    reset();
  }
}

// 暴露方法给父组件使用，包括重置方法
defineExpose({
  handleSubmit,
  handleSubmitWithStatus,
  resetForm: reset,
});
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.bet-form {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  width: 100%;
  box-sizing: border-box;
}

.editing-banner {
  @extend .flex-between;
  padding: 12rpx 16rpx;
  border-radius: 10rpx;
  background: rgba(13, 148, 136, 0.08);
  font-size: 22rpx;
  color: #0d9488;
  font-weight: 500;
  border: 1px solid rgba(13, 148, 136, 0.12);
}

.legs-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.leg-card {
  padding: 12rpx;
  border-radius: 10rpx;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  width: 100%;
  box-sizing: border-box;
}

.leg-header {
  @extend .flex-between;
  font-weight: 500;
  color: #0d9488;
  font-size: 24rpx;
  align-items: center;
  width: 100%;
  margin-bottom: 4rpx;
}

.leg-title {
  flex: 1;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.inline {
  flex-direction: row;
  justify-content: space-between;
  gap: 12rpx;

  .inline-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6rpx;
  }
}

.label {
  font-size: 22rpx;
  color: #666;
  font-weight: 400;
  margin-bottom: 0;
}

input,
.picker-value {
  background-color: #fff;
  border-radius: 8rpx;
  padding: 0 12rpx;
  font-size: 24rpx;
  border: 1px solid #e5e7eb;
  color: #111;
  transition: all 0.2s;
  width: 100%;
  box-sizing: border-box;
  height: 56rpx;
  line-height: 56rpx;
}

input {
  display: block;
}

input:focus {
  border-color: #0d9488;
  background: #fff;
}

input:disabled {
  background: #f5f5f5;
  color: #999;
  cursor: not-allowed;
}

.picker-value {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #374151;
  position: relative;
}

.picker-value::after {
  content: "▼";
  font-size: 18rpx;
  color: #999;
  margin-left: 8rpx;
  flex-shrink: 0;
}

.picker-wrapper {
  width: 100%;
  display: block;
}

.helper {
  font-size: 20rpx;
  color: #0d9488;
  font-weight: 400;
}

.odds-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10rpx 12rpx;
  background: rgba(13, 148, 136, 0.06);
  border: 1px solid rgba(13, 148, 136, 0.15);
  border-radius: 8rpx;
  gap: 16rpx;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8rpx;
  flex: 1;
  
  &:last-child {
    justify-content: flex-end;
  }
}

.info-label {
  font-size: 20rpx;
  color: #666;
  white-space: nowrap;
}

.info-value {
  font-size: 24rpx;
  font-weight: 600;
  color: #0d9488;
  white-space: nowrap;
  
  &.winning {
    font-size: 26rpx;
    color: #10b981;
  }
}

/* 表单验证提示 */
.validation-tips {
  display: flex;
  align-items: flex-start;
  gap: 10rpx;
  padding: 12rpx;
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 8rpx;
}

.tip-icon {
  font-size: 24rpx;
  flex-shrink: 0;
  margin-top: 2rpx;
}

.tip-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.tip-title {
  font-size: 22rpx;
  color: #92400e;
  font-weight: 500;
}

.tip-error {
  font-size: 20rpx;
  color: #d97706;
  font-weight: 400;
}

.tip-more {
  font-size: 18rpx;
  color: #b45309;
  font-weight: 400;
  margin-top: 2rpx;
}

/* 串关选择器 */
.parlay-selector {
  padding: 10rpx 12rpx;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8rpx;
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.selector-label {
  font-size: 22rpx;
  color: #666;
  flex-shrink: 0;
  font-weight: 400;
}

.parlay-options {
  flex: 1;
  display: flex;
  white-space: nowrap;
  overflow-x: auto;
}

.parlay-option {
  display: inline-block;
  padding: 6rpx 16rpx;
  margin-right: 10rpx;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8rpx;
  font-size: 22rpx;
  color: #666;
  transition: all 0.2s;
  flex-shrink: 0;
  
  &:last-child {
    margin-right: 0;
  }
  
  &.active {
    background: #0d9488;
    border-color: #0d9488;
    color: #fff;
    font-weight: 500;
  }
}

.ghost-btn {
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 8rpx;
  height: 44rpx;
  line-height: 44rpx;
  padding: 0 16rpx;
  font-size: 22rpx;
  background: #fff;
  color: #ef4444;
  transition: all 0.2s;
  flex-shrink: 0;
  margin-left: 12rpx;
}

.ghost-btn:active {
  background: rgba(239, 68, 68, 0.05);
  transform: scale(0.98);
}

.ghost-btn.small {
  height: 36rpx;
  line-height: 36rpx;
  padding: 0 12rpx;
  font-size: 20rpx;
}

.secondary-btn {
  border: 1px dashed rgba(13, 148, 136, 0.3);
  border-radius: 8rpx;
  padding: 12rpx 0;
  font-size: 24rpx;
  background: #ffffff;
  color: #0d9488;
  font-weight: 500;
  transition: all 0.2s;
  width: 100%;
  box-sizing: border-box;
  height: 56rpx;
  line-height: 1;
}

.secondary-btn:active {
  background: rgba(13, 148, 136, 0.05);
  border-color: #0d9488;
}

.primary-btn {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  border-radius: 8rpx;
  padding: 12rpx 0;
  font-size: 26rpx;
  font-weight: 600;
  border: none;
  box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);
  transition: all 0.2s;
  width: 100%;
  box-sizing: border-box;
  height: 56rpx;
  line-height: 1;
}

.primary-btn:active {
  transform: translateY(1rpx);
  box-shadow: 0 1rpx 4rpx rgba(13, 148, 136, 0.3);
}
</style>
