<template>
  <view class="page-wrapper">
    <!-- 头部用户信息区域 -->
    <view class="header-section">
      <view class="header-inner">
        <view class="user-info" v-if="userStore.isLoggedIn">
          <image class="avatar" :src="userStore.user?.avatar || defaultAvatar" mode="aspectFill" @error="handleImageError" />
          <view class="user-details">
            <text class="nickname">{{ userStore.user?.nickname || "用户" }}</text>
            <text class="username">@{{ userStore.user?.username }}</text>
          </view>
        </view>

        <view class="login-prompt" v-else @tap="goToLogin">
          <image class="avatar" :src="defaultAvatar" mode="aspectFill" @error="handleImageError" />
          <view class="login-text">
            <text class="title">点击登录</text>
            <text class="subtitle">登录后享受更多功能</text>
          </view>
          <text class="arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 菜单列表 -->
    <scroll-view class="content-wrapper" scroll-y>
      <view class="content-inner">
        <!-- 功能菜单组 -->
        <view class="menu-group">
          <text class="group-title">功能</text>
          <view class="menu-card">
            <view class="menu-item" @tap="navigateTo('/pages/strategy/strategy')">
              <view class="menu-left">
                <view class="menu-icon" style="background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)">
                  <text class="icon-text">📊</text>
                </view>
                <text class="menu-label">投注策略</text>
              </view>
              <text class="menu-arrow">›</text>
            </view>

            <view class="divider"></view>

            <view class="menu-item" @tap="navigateTo('/pages/settings/settings')">
              <view class="menu-left">
                <view class="menu-icon" style="background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%)">
                  <text class="icon-text">⚙️</text>
                </view>
                <text class="menu-label">策略设置</text>
              </view>
              <text class="menu-arrow">›</text>
            </view>

            <view class="divider"></view>

            <view class="menu-item" @tap="navigateTo('/pages/analysis/analysis')">
              <view class="menu-left">
                <view class="menu-icon" style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)">
                  <text class="icon-text">📈</text>
                </view>
                <text class="menu-label">数据分析</text>
              </view>
              <text class="menu-arrow">›</text>
            </view>
          </view>
        </view>

        <!-- 账户菜单组 (登录后显示) -->
        <view class="menu-group" v-if="userStore.isLoggedIn">
          <text class="group-title">账户</text>
          <view class="menu-card">
            <view class="menu-item" @tap="handleEditProfile">
              <view class="menu-left">
                <view class="menu-icon" style="background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)">
                  <text class="icon-text">👤</text>
                </view>
                <text class="menu-label">个人资料</text>
              </view>
              <text class="menu-arrow">›</text>
            </view>
          </view>
        </view>

        <!-- 其他菜单组 -->
        <view class="menu-group">
          <text class="group-title">其他</text>
          <view class="menu-card">
            <view class="menu-item" @tap="handleHelp">
              <view class="menu-left">
                <view class="menu-icon" style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%)">
                  <text class="icon-text">❓</text>
                </view>
                <text class="menu-label">帮助中心</text>
              </view>
              <text class="menu-arrow">›</text>
            </view>

            <view class="divider"></view>

            <view class="menu-item" @tap="handleAbout">
              <view class="menu-left">
                <view class="menu-icon" style="background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%)">
                  <text class="icon-text">ℹ️</text>
                </view>
                <text class="menu-label">关于我们</text>
              </view>
              <text class="menu-arrow">›</text>
            </view>
          </view>
        </view>

        <!-- 退出登录按钮 -->
        <view class="logout-section" v-if="userStore.isLoggedIn">
          <button class="logout-btn" @tap="handleLogout">退出登录</button>
        </view>

        <!-- 版本信息 -->
        <view class="version-info">
          <text>v1.0.0</text>
        </view>
      </view>
    </scroll-view>
    <ConfirmDialog />
  </view>
</template>

<script setup>
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useUserStore } from "@/stores/userStore";
import { requireAuth } from "@/utils/auth";
import { showConfirm } from "@/utils/confirm";

const userStore = useUserStore();
// 使用 base64 编码的默认头像，避免小程序中加载外部图片失败
// 这是一个简单的圆形头像占位符（用户图标）
const defaultAvatar =
  "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgdmlld0JveD0iMCAwIDEwMCAxMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIiByeD0iNTAiIGZpbGw9IiMwZDk0ODgiLz4KPHBhdGggZD0iTTUwIDMwQzQwLjMzNTggMzAgMzIgMzguMzM1OCAzMiA0OEMzMiA1Ny42NjQyIDQwLjMzNTggNjYgNTAgNjZDNjkuNjY0MiA2NiA3OCA1Ny42NjQyIDc4IDQ4Qzc4IDM4LjMzNTggNjkuNjY0MiAzMCA1MCAzMFoiIGZpbGw9IndoaXRlIi8+CjxwYXRoIGQ9Ik0yMCA4MEMyMCA3My4zNzI2IDI1LjM3MjYgNjggMzIgNjhINjggNzQuNjI3NCA2OCA4MCA2OCA4NkM2OCA5Mi42Mjc0IDYyLjYyNzQgOTggNTYgOThINDBDMzMuMzcyNiA5OCAyOCA5Mi42Mjc0IDI4IDg2VjgwSDIwWiIgZmlsbD0id2hpdGUiLz4KPC9zdmc+";

function navigateTo(url) {
  uni.navigateTo({ url });
}

function goToLogin() {
  // 使用requireAuth来跳转，会自动根据环境跳转到正确的登录页面
  requireAuth();
}

function handleEditProfile() {
  uni.navigateTo({ url: "/pages/profile/edit" });
}

function handleHelp() {
  showConfirm({ title: "帮助中心", content: "如有问题，请联系客服", confirmText: "知道了", cancelText: "" });
}

function handleAbout() {
  showConfirm({ title: "关于我们", content: "理性玩球小助手 v1.0.0\n帮助您理性投注，科学决策", confirmText: "知道了", cancelText: "" });
}

async function handleLogout() {
  const confirmed = await showConfirm({
    title: "退出登录",
    content: "确定要退出登录吗？",
    confirmText: "退出",
    type: "danger",
  });
  if (confirmed) {
    userStore.logout();
    uni.showToast({ title: "已退出登录", icon: "success", duration: 1500 });
    setTimeout(() => {
      // #ifdef MP-WEIXIN
      uni.reLaunch({ url: "/pages/auth/wechat-login" });
      // #endif
      // #ifndef MP-WEIXIN
      uni.reLaunch({ url: "/pages/auth/login" });
      // #endif
    }, 1500);
  }
}

function handleImageError(e) {
  // 图片加载失败时的处理，可以设置一个默认的 base64 图片或隐藏图片
  console.warn("头像图片加载失败", e);
  // 如果需要，可以设置一个 base64 编码的默认头像
}

onShow(() => {
  // 检查登录状态（profile页面允许未登录查看，但会显示登录提示）
  // 如果已登录，刷新用户信息
  if (userStore.isLoggedIn) {
    userStore.fetchUserProfile();
  }
  uni.$emit("tab-active", "profile");
});
</script>

<style lang="scss" scoped>
@import "@/uni.scss";

.page-wrapper {
  min-height: 100vh;
  background: #f5f5f5;
  display: flex;
  flex-direction: column;
}

/* 头部用户信息区域 */
.header-section {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  padding: 56rpx 24rpx 40rpx;
  border-radius: 0 0 28rpx 28rpx;
  box-shadow: 0 2rpx 12rpx rgba(13, 148, 136, 0.15);
  box-sizing: border-box;
}

.header-inner {
  width: 100%;
  max-width: 720rpx;
  margin: 0 auto;
  padding: 0 12rpx;
  box-sizing: border-box;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.login-prompt {
  display: flex;
  align-items: center;
  gap: 16rpx;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  padding: 16rpx;
  border-radius: 8rpx;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.avatar {
  width: 100rpx;
  height: 100rpx;
  border-radius: 50%;
  border: 3rpx solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.1);
}

.user-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.nickname {
  font-size: 30rpx;
  font-weight: 600;
  color: #ffffff;
}

.username {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.8);
}

.login-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.login-text .title {
  font-size: 28rpx;
  font-weight: 600;
  color: #ffffff;
}

.login-text .subtitle {
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.8);
}

.arrow {
  font-size: 40rpx;
  color: rgba(255, 255, 255, 0.6);
  font-weight: 200;
}

/* 内容区域 */
.content-wrapper {
  flex: 1;
  padding: 32rpx 0 40rpx;
  box-sizing: border-box;
}

.content-inner {
  width: 100%;
  max-width: 720rpx;
  margin: 0 auto;
  padding: 0 24rpx 48rpx;
  box-sizing: border-box;
}

/* 菜单组 */
.menu-group {
  margin-bottom: 24rpx;
}

.group-title {
  font-size: 22rpx;
  color: #9ca3af;
  font-weight: 600;
  margin-bottom: 12rpx;
  margin-left: 6rpx;
  display: block;
}

.menu-card {
  background: #ffffff;
  border-radius: 8rpx;
  overflow: hidden;
  box-shadow: 0 2rpx 6rpx rgba(0, 0, 0, 0.04);
}

.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx;
  transition: background 0.2s;
}

.menu-item:active {
  background: #f9fafb;
}

.menu-left {
  display: flex;
  align-items: center;
  gap: 16rpx;
  flex: 1;
}

.menu-icon {
  width: 64rpx;
  height: 64rpx;
  border-radius: 8rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.08);
}

.icon-text {
  font-size: 28rpx;
}

.menu-label {
  font-size: 26rpx;
  color: #111827;
  font-weight: 500;
}

.menu-arrow {
  font-size: 36rpx;
  color: #d1d5db;
  font-weight: 200;
}

.divider {
  height: 1px;
  background: #f3f4f6;
  margin: 0 20rpx;
}

/* 退出登录区域 */
.logout-section {
  margin-top: 32rpx;
  padding: 12rpx 0 32rpx;
  display: flex;
  justify-content: center;
}

.logout-btn {
  width: 100%;
  max-width: 520rpx;
  height: 72rpx;
  background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
  color: #ffffff;
  font-size: 26rpx;
  font-weight: 600;
  border-radius: 8rpx;
  border: none;
  box-shadow: 0 6rpx 18rpx rgba(239, 68, 68, 0.25);
  line-height: 72rpx;
}

.logout-btn:active {
  transform: translateY(1rpx);
}

/* 版本信息 */
.version-info {
  text-align: center;
  padding: 30rpx 0;
  color: #9ca3af;
  font-size: 20rpx;
}
</style>
