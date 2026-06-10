<template>
  <view v-if="visible" class="dp-mask" @tap="handleCancel"></view>
  <view class="dp-panel" :class="{ visible }">
    <view class="dp-header">
      <text class="dp-cancel" @tap="handleCancel">取消</text>
      <text class="dp-title">选择日期</text>
      <text class="dp-confirm" @tap="handleConfirm">确定</text>
    </view>
    <view class="dp-body">
      <view class="dp-month-nav">
        <text class="dp-arrow" @tap="prevMonth">&lt;</text>
        <text class="dp-month-label">{{ year }}年{{ month }}月</text>
        <text class="dp-arrow" @tap="nextMonth">&gt;</text>
      </view>
      <view class="dp-weekdays">
        <text class="dp-wd" v-for="w in ['日','一','二','三','四','五','六']" :key="w">{{ w }}</text>
      </view>
      <view class="dp-days">
        <text
          v-for="(d, i) in days"
          :key="i"
          class="dp-day"
          :class="{ 'other-month': d.other, 'is-today': d.isToday, 'is-selected': d.dateStr === selected }"
          @tap="!d.other && (selected = d.dateStr)"
        >{{ d.day }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from "vue";

const visible = ref(false);
const year = ref(2026);
const month = ref(6);
const selected = ref("");
let resolvePromise = null;

const days = computed(() => {
  const y = year.value;
  const m = month.value;
  const firstDay = new Date(y, m - 1, 1).getDay();
  const daysInMonth = new Date(y, m, 0).getDate();
  const daysInPrev = new Date(y, m - 1, 0).getDate();
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const cells = [];

  for (let i = firstDay - 1; i >= 0; i--) {
    const day = daysInPrev - i;
    const pm = m - 1 < 1 ? 12 : m - 1;
    const py = m - 1 < 1 ? y - 1 : y;
    cells.push({ day, other: true, dateStr: `${py}-${String(pm).padStart(2, "0")}-${String(day).padStart(2, "0")}`, isToday: false });
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, other: false, dateStr, isToday: dateStr === todayStr });
  }

  const remaining = 42 - cells.length;
  for (let d = 1; d <= remaining; d++) {
    const nm = m + 1 > 12 ? 1 : m + 1;
    const ny = m + 1 > 12 ? y + 1 : y;
    cells.push({ day: d, other: true, dateStr: `${ny}-${String(nm).padStart(2, "0")}-${String(d).padStart(2, "0")}`, isToday: false });
  }

  return cells;
});

function show(options = {}) {
  const initDate = options.value || "";
  if (initDate) {
    const parts = initDate.split("-");
    year.value = parseInt(parts[0]);
    month.value = parseInt(parts[1]);
    selected.value = initDate;
  } else {
    const now = new Date();
    year.value = now.getFullYear();
    month.value = now.getMonth() + 1;
    selected.value = "";
  }
  visible.value = true;
  return new Promise((resolve) => { resolvePromise = resolve; });
}

function prevMonth() {
  if (month.value === 1) { month.value = 12; year.value--; }
  else month.value--;
}

function nextMonth() {
  if (month.value === 12) { month.value = 1; year.value++; }
  else month.value++;
}

function handleConfirm() {
  visible.value = false;
  if (resolvePromise) resolvePromise(selected.value || null);
  resolvePromise = null;
}

function handleCancel() {
  visible.value = false;
  if (resolvePromise) resolvePromise(null);
  resolvePromise = null;
}

defineExpose({ show });
</script>

<style lang="scss" scoped>
.dp-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 9998;
}

.dp-panel {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
  border-radius: 16rpx 16rpx 0 0;
  z-index: 9999;
  transform: translateY(100%);
  transition: transform 0.3s ease;
}

.dp-panel.visible {
  transform: translateY(0);
}

.dp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1px solid #f3f4f6;
}

.dp-cancel {
  font-size: 28rpx;
  color: #6b7280;
}

.dp-title {
  font-size: 28rpx;
  color: #1f2937;
  font-weight: 600;
}

.dp-confirm {
  font-size: 28rpx;
  color: #0d9488;
  font-weight: 600;
}

.dp-body {
  padding: 20rpx 24rpx 48rpx;
}

.dp-month-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 40rpx;
  margin-bottom: 20rpx;
}

.dp-arrow {
  font-size: 28rpx;
  color: #6b7280;
  padding: 8rpx 16rpx;
}

.dp-arrow:active {
  color: #0d9488;
}

.dp-month-label {
  font-size: 28rpx;
  color: #1f2937;
  font-weight: 500;
}

.dp-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 12rpx;
}

.dp-wd {
  text-align: center;
  font-size: 22rpx;
  color: #9ca3af;
  line-height: 2;
}

.dp-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4rpx 0;
}

.dp-day {
  text-align: center;
  font-size: 26rpx;
  color: #374151;
  line-height: 2.4;
  border-radius: 6rpx;
}

.dp-day.other-month {
  color: #e5e7eb;
}

.dp-day.is-today {
  color: #0d9488;
  font-weight: 600;
}

.dp-day.is-selected {
  background: #0d9488;
  color: #fff;
  font-weight: 600;
}
</style>
