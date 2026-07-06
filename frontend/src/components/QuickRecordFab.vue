<template>
  <view class="fab" @tap="goRecord">
    <text class="icon">+</text>
    <text class="label">记录</text>
  </view>
</template>

<script setup>
function goRecord() {
  // 提示记录页打开新增弹窗
  uni.setStorageSync('open-new-bet', true);
  uni.switchTab({ url: "/pages/record/record" });
}
</script>

<style lang="scss" scoped>
.fab {
  position: fixed;
  left: 32rpx;
  bottom: calc(env(safe-area-inset-bottom) + 180rpx);
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  box-shadow: 0 6rpx 20rpx rgba(13, 148, 136, 0.35);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
  z-index: 998;
  transition: transform 0.2s;
}

.fab:active {
  transform: scale(0.92);
}

.icon {
  font-size: 40rpx;
  line-height: 1;
}

.label {
  font-size: 18rpx;
  margin-top: 2rpx;
}
</style>
