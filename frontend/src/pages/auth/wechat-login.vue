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
        <button class="auth-btn" @click="handleWechatLogin" :disabled="loading">
          <text v-if="loading">登录中...</text>
          <text v-else>微信快速登录</text>
        </button>
      </view>

      <!-- 说明文字 -->
      <view class="desc-section">
        <text class="desc-text">点击按钮即表示同意获取您的微信头像和昵称</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { useUserStore } from "@/stores/userStore";

const userStore = useUserStore();
const loading = ref(false);

async function handleWechatLogin() {
  // 防止重复点击
  if (loading.value) {
    return;
  }

  loading.value = true;

  try {
    // 1. 获取用户信息（需要用户主动触发，会弹出授权弹窗）
    let userInfo = null;
    try {
      const profileRes = await new Promise((resolve, reject) => {
        uni.getUserProfile({
          desc: "用于完善会员资料", // 必填，向用户说明获取信息的用途
          success: (res) => {
            resolve(res);
          },
          fail: (err) => {
            reject(err);
          },
        });
      });

      if (profileRes && profileRes.userInfo) {
        userInfo = profileRes.userInfo; // 包含 nickName, avatarUrl 等信息
      }
    } catch (profileError) {
      // 用户拒绝授权或获取失败
      console.log("获取用户信息失败:", profileError);
      uni.showToast({
        title: "需要授权才能登录",
        icon: "none",
        duration: 2000,
      });
      loading.value = false;
      return;
    }

    // 2. 获取微信登录code（每次调用都会获取新的code，有效期5分钟）
    const loginRes = await new Promise((resolve, reject) => {
      uni.login({
        provider: "weixin",
        success: (res) => {
          if (res.code) {
            resolve(res);
          } else {
            reject(new Error("获取登录code失败"));
          }
        },
        fail: (err) => {
          reject(new Error(err.errMsg || "获取登录code失败"));
        },
      });
    });

    if (!loginRes.code) {
      throw new Error("获取登录code失败");
    }

    // 3. 调用后端微信登录接口
    // 传递code和用户信息（昵称、头像等）
    await userStore.wechatLogin({
      code: loginRes.code,
      user_info: userInfo, // 包含 nickName, avatarUrl 等信息
    });

    uni.showToast({
      title: "登录成功",
      icon: "success",
      duration: 1500,
    });

    // 延迟跳转到首页
    setTimeout(() => {
      uni.switchTab({
        url: "/pages/home/home",
      });
    }, 1500);
  } catch (error) {
    console.error("微信登录失败:", error);
    uni.showToast({
      title: error.data?.detail || error.message || "登录失败，请重试",
      icon: "none",
      duration: 2000,
    });
  } finally {
    loading.value = false;
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
