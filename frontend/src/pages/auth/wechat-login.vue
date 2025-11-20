<template>
  <view class="page-wrapper">
    <view class="content">
      <!-- Logo区域 -->
      <view class="logo-section">
        <view class="logo-circle">
          <text class="logo-icon">⚽</text>
        </view>
        <text class="app-name">足球理性投资助手</text>
        <text class="welcome-text">欢迎使用</text>
      </view>

      <!-- 授权按钮 -->
      <view class="button-section">
        <button class="auth-btn" :disabled="loading" @tap="handleStartLogin" hover-class="auth-btn-active">
          <text v-if="loading">跳转中...</text>
          <text v-else>微信快速登录</text>
        </button>
      </view>

      <!-- 说明文字 -->
      <view class="desc-section">
        <text class="desc-text"> 点击按钮后，将跳转到“头像昵称填写”页，按照微信最新规范完成资料后即可登录。 </text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";

const loading = ref(false);
const redirectUrl = ref("/pages/home/home");

onLoad((options) => {
  if (options?.redirect) {
    redirectUrl.value = decodeURIComponent(options.redirect);
  }
});

function handleStartLogin() {
  if (loading.value) {
    return;
  }

  // #ifndef MP-WEIXIN
  uni.showToast({
    title: "请在微信小程序内使用微信登录",
    icon: "none",
  });
  return;
  // #endif

  loading.value = true;
  uni.navigateTo({
    url: `/pages/auth/wechat-profile?redirect=${encodeURIComponent(redirectUrl.value)}`,
    complete: () => {
      loading.value = false;
    },
  });
}
</script>

<style lang="scss" scoped>
.page-wrapper {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40rpx 20rpx;
}

.content {
  width: 100%;
  max-width: 600rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* Logo区域 */
.logo-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 60rpx;
}

.logo-circle {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8rpx 24rpx rgba(13, 148, 136, 0.3);
  margin-bottom: 24rpx;
}

.logo-icon {
  font-size: 56rpx;
}

.app-name {
  font-size: 32rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 12rpx;
}

.welcome-text {
  font-size: 24rpx;
  color: #6b7280;
}

/* 按钮区域 */
.button-section {
  width: 100%;
  margin-bottom: 32rpx;
}

.auth-btn {
  width: 100%;
  height: 88rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  font-size: 32rpx;
  font-weight: 600;
  border-radius: 44rpx;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.3);
  transition: all 0.3s;
}

.auth-btn:active {
  transform: scale(0.98);
  opacity: 0.9;
}

.auth-btn[disabled] {
  opacity: 0.6;
}

/* 说明区域 */
.desc-section {
  width: 100%;
  text-align: center;
}

.desc-text {
  font-size: 22rpx;
  color: #9ca3af;
  line-height: 1.5;
}
</style>
