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

      <!-- 提示信息 -->
      <view class="tip-section">
        <text class="tip-text">为了更好的使用体验，需要获取您的微信头像和昵称</text>
      </view>

      <!-- 授权按钮 -->
      <view class="button-section">
        <button 
          class="auth-btn" 
          open-type="getUserProfile"
          @getuserprofile="handleGetUserProfile"
          :disabled="loading"
        >
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

async function handleGetUserProfile(e) {
  // 检查用户是否授权
  if (e.detail.errMsg !== 'getUserProfile:ok') {
    uni.showToast({
      title: "需要授权才能登录",
      icon: "none",
    });
    return;
  }

  loading.value = true;

  try {
    // 1. 获取微信登录code（每次调用都会获取新的code，有效期5分钟）
    const loginRes = await new Promise((resolve, reject) => {
      uni.login({
        provider: 'weixin',
        success: (res) => {
          if (res.code) {
            resolve(res);
          } else {
            reject(new Error('获取登录code失败'));
          }
        },
        fail: (err) => {
          reject(new Error(err.errMsg || '获取登录code失败'));
        }
      });
    });

    if (!loginRes.code) {
      throw new Error('获取登录code失败');
    }

    // 2. 调用后端微信登录接口
    // 传递code和用户信息（昵称、头像等）
    await userStore.wechatLogin({
      code: loginRes.code,
      user_info: e.detail.userInfo  // 包含 nickName, avatarUrl 等信息
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
    console.error('微信登录失败:', error);
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

/* 提示区域 */
.tip-section {
  width: 100%;
  background: #ffffff;
  border-radius: 16rpx;
  padding: 32rpx 24rpx;
  margin-bottom: 40rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}

.tip-text {
  font-size: 26rpx;
  color: #374151;
  line-height: 1.6;
  text-align: center;
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

