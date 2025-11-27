<template>
  <view class="page-wrapper">
    <scroll-view class="content" scroll-y>
      <!-- Logo区域 -->
      <view class="logo-section">
        <view class="logo-circle">
          <text class="logo-icon">⚽</text>
        </view>
        <text class="app-name">理性玩球小助手</text>
        <text class="welcome-text">创建新账号</text>
      </view>

      <!-- 注册表单 -->
      <view class="form-section">
        <view class="input-group">
          <view class="input-label">
            <text class="label-icon">👤</text>
            <text>用户名</text>
          </view>
          <input class="input-field" v-model="form.username" placeholder="请输入用户名" placeholder-class="input-placeholder" />
        </view>

        <view class="input-group">
          <view class="input-label">
            <text class="label-icon">✨</text>
            <text>昵称</text>
          </view>
          <input class="input-field" v-model="form.nickname" placeholder="请输入昵称（可选）" placeholder-class="input-placeholder" />
        </view>

        <view class="input-group">
          <view class="input-label">
            <text class="label-icon">📱</text>
            <text>手机号</text>
          </view>
          <input class="input-field" v-model="form.phone" type="number" placeholder="请输入手机号（可选）" placeholder-class="input-placeholder" />
        </view>

        <view class="input-group">
          <view class="input-label">
            <text class="label-icon">🔒</text>
            <text>密码</text>
          </view>
          <input class="input-field" v-model="form.password" type="password" placeholder="请输入密码（至少6位）" placeholder-class="input-placeholder" />
        </view>

        <view class="input-group">
          <view class="input-label">
            <text class="label-icon">🔒</text>
            <text>确认密码</text>
          </view>
          <input class="input-field" v-model="form.confirmPassword" type="password" placeholder="请再次输入密码" placeholder-class="input-placeholder" />
        </view>

        <button class="register-btn" @tap="handleRegister" :disabled="loading">
          <text v-if="loading">注册中...</text>
          <text v-else>注册</text>
        </button>

        <view class="action-links">
          <text class="link-text" @tap="goToLogin">已有账号？立即登录</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useUserStore } from "@/stores/userStore";

const userStore = useUserStore();
const loading = ref(false);

const form = reactive({
  username: "",
  nickname: "",
  phone: "",
  password: "",
  confirmPassword: "",
});

async function handleRegister() {
  // 验证表单
  if (!form.username.trim()) {
    uni.showToast({ title: "请输入用户名", icon: "none" });
    return;
  }

  if (form.username.trim().length < 3) {
    uni.showToast({ title: "用户名至少3个字符", icon: "none" });
    return;
  }

  if (!form.password.trim()) {
    uni.showToast({ title: "请输入密码", icon: "none" });
    return;
  }

  if (form.password.trim().length < 6) {
    uni.showToast({ title: "密码至少6个字符", icon: "none" });
    return;
  }

  if (form.password !== form.confirmPassword) {
    uni.showToast({ title: "两次密码不一致", icon: "none" });
    return;
  }

  loading.value = true;

  try {
    const data = {
      username: form.username.trim(),
      password: form.password.trim(),
    };

    if (form.nickname.trim()) {
      data.nickname = form.nickname.trim();
    }

    if (form.phone.trim()) {
      data.phone = form.phone.trim();
    }

    await userStore.register(data);

    uni.showToast({
      title: "注册成功",
      icon: "success",
      duration: 1500,
    });

    // 延迟返回
    setTimeout(() => {
      uni.redirectTo({
        url: "/pages/auth/login",
      });
    }, 1500);
  } catch (error) {
    uni.showToast({
      title: error.data?.detail || "注册失败",
      icon: "none",
    });
  } finally {
    loading.value = false;
  }
}

function goToLogin() {
  uni.navigateTo({
    url: "/pages/auth/login",
  });
}
</script>

<style lang="scss" scoped>
.page-wrapper {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
}

.content {
  min-height: 100vh;
  padding: 30rpx 20rpx;
  max-width: 750rpx;
  margin: 0 auto;
  box-sizing: border-box;
}

/* Logo区域 */
.logo-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 30rpx 0 40rpx;
}

.logo-circle {
  width: 100rpx;
  height: 100rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4rpx 12rpx rgba(13, 148, 136, 0.2);
  margin-bottom: 16rpx;
}

.logo-icon {
  font-size: 48rpx;
}

.app-name {
  font-size: 26rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 8rpx;
}

.welcome-text {
  font-size: 22rpx;
  color: #6b7280;
}

/* 表单区域 */
.form-section {
  background: #ffffff;
  border-radius: 8rpx;
  padding: 32rpx 24rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}

.input-group {
  margin-bottom: 24rpx;
}

.input-label {
  display: flex;
  align-items: center;
  gap: 8rpx;
  font-size: 24rpx;
  color: #374151;
  font-weight: 500;
  margin-bottom: 12rpx;
}

.label-icon {
  font-size: 20rpx;
}

.input-field {
  width: 100%;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8rpx;
  padding: 0 16rpx;
  font-size: 26rpx;
  color: #111827;
  transition: all 0.3s;
  box-sizing: border-box;
  height: 60rpx;
  line-height: 60rpx;
}

.input-field:focus {
  border-color: #0d9488;
  background: #ffffff;
  box-shadow: 0 0 0 3rpx rgba(13, 148, 136, 0.06);
}

.input-placeholder {
  color: #9ca3af;
}

.register-btn {
  width: 100%;
  height: 72rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  font-size: 26rpx;
  font-weight: 600;
  border-radius: 8rpx;
  border: none;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.3);
  margin-top: 32rpx;
  transition: all 0.2s;
  padding: 0;
  line-height: 72rpx;
}

.register-btn:active {
  transform: translateY(1rpx);
  box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);
}

.register-btn:disabled {
  opacity: 0.6;
  transform: none;
}

.action-links {
  display: flex;
  justify-content: center;
  margin-top: 24rpx;
}

.link-text {
  font-size: 24rpx;
  color: #0d9488;
  font-weight: 500;
}
</style>
