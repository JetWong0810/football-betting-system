<template>
  <view class="fab-wrapper" :style="{ bottom: fabBottom + 'rpx' }" @touchmove.stop.prevent="onDrag" @touchend="onDragEnd">
    <view class="fab-btn" @tap="openPanel">
      <text class="fab-text">查询</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['open'])

const fabBottom = ref(180)
let startY = 0
let startBottom = 0

function openPanel() {
  emit('open')
}

function onDrag(e) {
  const touch = e.touches[0]
  if (!startY) {
    startY = touch.clientY
    startBottom = fabBottom.value
  }
  const diff = (startY - touch.clientY) * 2
  fabBottom.value = Math.max(120, Math.min(800, startBottom + diff))
}

function onDragEnd() {
  startY = 0
}
</script>

<style lang="scss" scoped>
.fab-wrapper {
  position: fixed;
  right: calc(var(--app-gutter, 0px) + 32rpx);
  z-index: 999;
}

.fab-btn {
  width: 88rpx;
  height: 88rpx;
  border-radius: 50%;
  background: #0d9488;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.3);
}

.fab-text {
  color: #ffffff;
  font-size: 22rpx;
  font-weight: 500;
}
</style>
