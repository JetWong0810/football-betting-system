<template>
  <!-- 连不中 strong 提醒(打断式,不锁入口) -->
  <view v-if="showStrong" class="cooldown-mask">
    <view class="cooldown-card strong">
      <view class="cd-title">连不中提醒</view>
      <view class="cd-msg">{{ alert.message }}</view>
      <view class="cd-hint">控手比追损更重要,确认冷静后再继续</view>
      <button class="cd-btn" @tap="confirmStrong">我已冷静</button>
    </view>
  </view>

  <!-- pause 暂停(隐藏下注入口 + 冷静倒计时 + 恢复) -->
  <view v-else-if="controlStore.isPaused" class="cooldown-mask">
    <view class="cooldown-card pause">
      <view class="cd-title">下注已暂停</view>
      <view class="cd-msg">连不中触发控手,请冷静休息</view>
      <view class="cd-countdown">{{ formatTime(remaining) }}</view>
      <view v-if="remaining === 0" class="cd-hint">
        已冷静完成。恢复后首注仅可选用低信心档,赢一把逐步解锁中/高档
      </view>
      <view v-else class="cd-hint">倒计时结束后可恢复下注</view>
      <button class="cd-btn" :disabled="remaining > 0" @tap="resume">恢复下注</button>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useControlStore } from "@/stores/controlStore";
import { useBetStore } from "@/stores/betStore";

const controlStore = useControlStore();
const betStore = useBetStore();

const alert = computed(() => controlStore.controlAlert);
const showStrong = ref(false);
const lastConfirmedStreak = ref(0); // 本次 strong 已确认的连不中数,避免重复弹
const remaining = ref(0);
let timer = null;

// 监听控手告警:pause 触发暂停,strong 弹窗(未确认本次则弹)
watch(
  () => controlStore.controlAlert.level,
  (level) => {
    if (level === "pause" && !controlStore.isPaused) {
      controlStore.pause();
      showStrong.value = false;
    } else if (level === "strong" && !controlStore.isPaused) {
      if (lastConfirmedStreak.value !== betStore.consecutiveLosses) {
        showStrong.value = true;
      }
    } else if (level === "normal") {
      showStrong.value = false;
    }
  },
  { immediate: true }
);

function confirmStrong() {
  showStrong.value = false;
  lastConfirmedStreak.value = betStore.consecutiveLosses;
}

function resume() {
  if (remaining.value > 0) return;
  controlStore.resume();
}

function formatTime(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

onMounted(() => {
  // 每秒刷新倒计时(因 Date.now() 非响应式,需手动 tick)
  timer = setInterval(() => {
    remaining.value = controlStore.isPaused ? controlStore.getRemainingSeconds() : 0;
  }, 1000);
  remaining.value = controlStore.isPaused ? controlStore.getRemainingSeconds() : 0;
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.cooldown-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 32rpx;
}

.cooldown-card {
  width: 100%;
  max-width: 560rpx;
  background: #fff;
  border-radius: 12rpx;
  padding: 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16rpx;

  &.strong {
    border-top: 6rpx solid #f59e0b;
  }

  &.pause {
    border-top: 6rpx solid #ef4444;
  }
}

.cd-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #111827;
}

.cd-msg {
  font-size: 26rpx;
  color: #374151;
  text-align: center;
}

.cd-countdown {
  font-size: 56rpx;
  font-weight: 700;
  color: #ef4444;
  font-variant-numeric: tabular-nums;
  letter-spacing: 2rpx;
}

.cd-hint {
  font-size: 22rpx;
  color: #6b7280;
  text-align: center;
  line-height: 1.5;
}

.cd-btn {
  margin-top: 8rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #fff;
  border: none;
  border-radius: 8rpx;
  padding: 16rpx 48rpx;
  font-size: 28rpx;
  font-weight: 600;

  &[disabled] {
    background: #d1d5db;
    color: #fff;
  }
}

.cd-btn:active {
  transform: translateY(1rpx);
}
</style>
