<template>
  <view class="fab" @tap="goRecord">
    <text class="icon">+</text>
    <text class="label">快速记录</text>
  </view>
</template>

<script setup>
function goRecord() {
  uni.navigateTo({ url: "/pages/record/record" });
}
</script>

<style lang="scss" scoped>
.fab {
  position: fixed;
  left: 50%;
  bottom: calc(env(safe-area-inset-bottom) + 40rpx);
  transform: translateX(-50%);
  width: 140rpx;
  height: 140rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  box-shadow: 0 8rpx 24rpx rgba(13, 148, 136, 0.4);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
  z-index: 998;
  transition: all 0.3s;
}

.fab:active {
  transform: translateX(-50%) scale(0.95);
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.4);
}

.icon {
  font-size: 48rpx;
  line-height: 1;
}

.label {
  font-size: 22rpx;
  margin-top: 6rpx;
}
</style>
