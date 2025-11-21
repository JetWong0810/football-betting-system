<template>
  <view class="page-wrapper">
    <view class="content">
      <!-- 检查登录状态中的加载状态 -->
      <view v-if="silentLoginInProgress" class="silent-login-section">
        <view class="loading-spinner"></view>
        <text class="loading-text">正在检查登录状态...</text>
      </view>

      <!-- 需要手动登录的界面 -->
      <template v-else>
        <!-- Logo区域 -->
        <view class="logo-section">
          <view class="logo-circle">
            <text class="logo-icon">⚽</text>
          </view>
          <text class="app-name">理性玩球小助手</text>
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
          <text class="desc-text"> 点击按钮后，将跳转到"头像昵称填写"页，按照微信最新规范完成资料后即可登录。 </text>
        </view>
      </template>
    </view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { useUserStore } from "@/stores/userStore";

const userStore = useUserStore();
const loading = ref(false);
const silentLoginInProgress = ref(true); // 初始为true，显示检查状态
const redirectUrl = ref("/pages/home/home");
const tabPages = ["/pages/home/home", "/pages/matches/list", "/pages/record/record", "/pages/profile/profile"];

onLoad((options) => {
  if (options?.redirect) {
    redirectUrl.value = decodeURIComponent(options.redirect);
  }

  // 检查登录状态（App.vue 已在启动时尝试自动登录）
  checkLoginStatus();
});

async function checkLoginStatus() {
  // #ifndef MP-WEIXIN
  silentLoginInProgress.value = false;
  return;
  // #endif

  // #ifdef MP-WEIXIN
  // 如果已经登录，直接跳转
  if (userStore.isLoggedIn) {
    uni.showToast({
      title: "已登录",
      icon: "success",
      duration: 800,
    });
    
    setTimeout(() => {
      navigateAfterLogin();
    }, 500);
  } else {
    // 未登录，显示手动登录界面
    silentLoginInProgress.value = false;
  }
  // #endif
}

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

function navigateAfterLogin() {
  const target = redirectUrl.value || "/pages/home/home";
  if (tabPages.includes(target)) {
    uni.switchTab({
      url: target,
      fail: () => {
        uni.reLaunch({ url: target });
      },
    });
  } else {
    uni.reLaunch({ url: target });
  }
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

/* 静默登录加载区域 */
.silent-login-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32rpx;
}

.loading-spinner {
  width: 80rpx;
  height: 80rpx;
  border: 6rpx solid rgba(13, 148, 136, 0.2);
  border-top-color: #0d9488;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.loading-text {
  font-size: 28rpx;
  color: #0d9488;
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
