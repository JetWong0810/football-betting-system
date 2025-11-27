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

        <!-- 微信一键登录（主要方式） -->
        <view class="button-section">
          <button class="wechat-btn primary" :disabled="loading" @tap="handleStartLogin">
            <text v-if="loading">跳转中...</text>
            <text v-else>微信一键登录</text>
          </button>
        </view>

        <!-- 分割线 -->
        <view class="divider">
          <view class="divider-line"></view>
          <text class="divider-text">或</text>
          <view class="divider-line"></view>
        </view>

        <!-- 账号密码登录（次要方式） -->
        <view class="account-login-section">
          <view class="input-group">
            <input 
              v-model="accountForm.username" 
              placeholder="用户名/手机号" 
              placeholder-class="input-placeholder"
              class="input-field"
            />
          </view>
          <view class="input-group">
            <input 
              v-model="accountForm.password" 
              type="password" 
              placeholder="密码" 
              placeholder-class="input-placeholder"
              class="input-field"
            />
          </view>
          <button class="account-btn" @tap="handleAccountLogin" :disabled="accountLoading">
            <text v-if="accountLoading">登录中...</text>
            <text v-else>账号登录</text>
          </button>
        </view>

        <!-- 底部链接 -->
        <view class="bottom-links">
          <text class="link-text" @tap="goToRegister">还没有账号？立即注册</text>
        </view>

        <!-- 隐私协议 -->
        <view class="privacy-tips">
          <text>登录即表示同意</text>
          <text class="link">《用户协议》</text>
        </view>
      </template>
    </view>
  </view>
</template>

<script setup>
import { ref, reactive } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { useUserStore } from "@/stores/userStore";

const userStore = useUserStore();
const loading = ref(false);
const accountLoading = ref(false);
const silentLoginInProgress = ref(true); // 初始为true，显示检查状态
const redirectUrl = ref("/pages/home/home");
const tabPages = ["/pages/home/home", "/pages/matches/list", "/pages/record/record", "/pages/profile/profile"];

const accountForm = reactive({
  username: "",
  password: "",
});

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

async function handleAccountLogin() {
  if (!accountForm.username || !accountForm.password) {
    uni.showToast({ title: "请输入用户名和密码", icon: "none" });
    return;
  }

  accountLoading.value = true;

  try {
    await userStore.login({
      username: accountForm.username,
      password: accountForm.password,
    });

    uni.showToast({ title: "登录成功", icon: "success", duration: 1500 });
    setTimeout(() => {
      navigateAfterLogin();
    }, 1500);
  } catch (error) {
    uni.showToast({ 
      title: error.data?.detail || "登录失败", 
      icon: "none" 
    });
  } finally {
    accountLoading.value = false;
  }
}

function goToRegister() {
  uni.navigateTo({ url: "/pages/auth/register" });
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

.wechat-btn {
  width: 100%;
  height: 88rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  font-size: 32rpx;
  font-weight: 600;
  border-radius: 12rpx;
  border: none;
  box-shadow: 0 6rpx 20rpx rgba(13, 148, 136, 0.35);
  transition: all 0.2s;
}

.wechat-btn:active {
  transform: scale(0.98);
  opacity: 0.9;
}

.wechat-btn[disabled] {
  opacity: 0.6;
}

/* 分割线 */
.divider {
  display: flex;
  align-items: center;
  margin: 40rpx 0;
  width: 100%;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: #e5e7eb;
}

.divider-text {
  padding: 0 24rpx;
  font-size: 24rpx;
  color: #9ca3af;
}

/* 账号密码登录 */
.account-login-section {
  width: 100%;
}

.input-group {
  margin-bottom: 20rpx;
}

.input-field {
  width: 100%;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8rpx;
  padding: 0 20rpx;
  font-size: 28rpx;
  color: #111827;
  transition: all 0.3s;
  box-sizing: border-box;
  height: 80rpx;
  line-height: 80rpx;
}

.input-field:focus {
  border-color: #0d9488;
  background: #ffffff;
}

.input-placeholder {
  color: #9ca3af;
}

.account-btn {
  width: 100%;
  height: 80rpx;
  background: #ffffff;
  color: #0d9488;
  font-size: 28rpx;
  font-weight: 500;
  border-radius: 8rpx;
  border: 2px solid #0d9488;
  margin-top: 12rpx;
  transition: all 0.2s;
}

.account-btn:active {
  background: #f0fdfa;
}

.account-btn[disabled] {
  opacity: 0.6;
}

/* 底部链接 */
.bottom-links {
  display: flex;
  justify-content: center;
  margin-top: 32rpx;
}

.link-text {
  font-size: 24rpx;
  color: #0d9488;
  font-weight: 500;
}

/* 隐私协议 */
.privacy-tips {
  text-align: center;
  margin-top: 24rpx;
  font-size: 22rpx;
  color: #9ca3af;
}

.privacy-tips .link {
  color: #0d9488;
}
</style>
