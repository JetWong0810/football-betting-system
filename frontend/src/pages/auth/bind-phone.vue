<template>
  <view class="page-wrapper">
    <view class="content">
      <!-- Logo 区域 -->
      <view class="logo-section">
        <view class="logo-circle">
          <text class="logo-icon">⚽</text>
        </view>
        <text class="app-name">理性玩球小助手</text>
      </view>

      <!-- 提示信息 -->
      <view class="tip-section">
        <text class="tip-title">绑定手机号</text>
        <text class="tip-desc">为了保障您的账号安全和数据同步，请绑定手机号</text>
      </view>

      <!-- 手机号输入 -->
      <view class="form-section">
        <view class="input-group">
          <view class="input-label">
            <text class="label-icon">📱</text>
            <text>手机号</text>
          </view>
          <input
            class="input-field"
            v-model="phone"
            type="number"
            placeholder="请输入手机号"
            placeholder-class="input-placeholder"
            maxlength="11"
          />
        </view>

        <button class="submit-btn" @tap="handleBindPhone" :disabled="loading">
          <text v-if="loading">绑定中...</text>
          <text v-else>确认绑定</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { useUserStore } from "@/stores/userStore";

const userStore = useUserStore();
const phone = ref("");
const loading = ref(false);

async function handleBindPhone() {
  // 手机号验证
  if (!phone.value.trim()) {
    uni.showToast({ title: "请输入手机号", icon: "none" });
    return;
  }

  const phoneRegex = /^1[3-9]\d{9}$/;
  if (!phoneRegex.test(phone.value.trim())) {
    uni.showToast({ title: "请输入正确的手机号", icon: "none" });
    return;
  }

  loading.value = true;

  try {
    const res = await userStore.bindPhone(phone.value.trim());

    if (res.merged) {
      // 账号合并成功
      uni.showToast({
        title: "账号已合并，欢迎回来",
        icon: "success",
        duration: 2000,
      });
    } else {
      // 绑定成功
      uni.showToast({
        title: "绑定成功",
        icon: "success",
        duration: 1500,
      });
    }

    // 延迟跳转到首页
    setTimeout(() => {
      uni.switchTab({
        url: "/pages/home/home",
      });
    }, res.merged ? 2000 : 1500);
  } catch (error) {
    uni.showToast({
      title: error.data?.detail || "绑定失败",
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
}

.content {
  padding: 60rpx 40rpx;
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
  margin-bottom: 20rpx;
}

.logo-icon {
  font-size: 60rpx;
}

.app-name {
  font-size: 32rpx;
  font-weight: 600;
  color: #0d9488;
}

/* 提示信息 */
.tip-section {
  text-align: center;
  margin-bottom: 60rpx;
}

.tip-title {
  display: block;
  font-size: 36rpx;
  font-weight: 600;
  color: #111827;
  margin-bottom: 16rpx;
}

.tip-desc {
  display: block;
  font-size: 26rpx;
  color: #6b7280;
  line-height: 1.6;
}

/* 表单区域 */
.form-section {
  background: #ffffff;
  border-radius: 16rpx;
  padding: 40rpx 32rpx;
  box-shadow: 0 4rpx 16rpx rgba(0, 0, 0, 0.06);
}

.input-group {
  margin-bottom: 32rpx;
}

.input-label {
  display: flex;
  align-items: center;
  gap: 8rpx;
  font-size: 28rpx;
  color: #374151;
  font-weight: 500;
  margin-bottom: 16rpx;
}

.label-icon {
  font-size: 24rpx;
}

.input-field {
  width: 100%;
  background: #f9fafb;
  border: 2px solid #e5e7eb;
  border-radius: 12rpx;
  padding: 0 20rpx;
  font-size: 30rpx;
  color: #111827;
  transition: all 0.3s;
  box-sizing: border-box;
  height: 88rpx;
  line-height: 88rpx;
}

.input-field:focus {
  border-color: #0d9488;
  background: #ffffff;
  box-shadow: 0 0 0 4rpx rgba(13, 148, 136, 0.1);
}

.input-placeholder {
  color: #9ca3af;
}

.submit-btn {
  width: 100%;
  height: 88rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  font-size: 32rpx;
  font-weight: 600;
  border-radius: 12rpx;
  border: none;
  box-shadow: 0 8rpx 24rpx rgba(13, 148, 136, 0.35);
  transition: all 0.2s;
  padding: 0;
  line-height: 88rpx;
}

.submit-btn:active {
  transform: translateY(2rpx);
  box-shadow: 0 4rpx 12rpx rgba(13, 148, 136, 0.35);
}

.submit-btn:disabled {
  opacity: 0.6;
  transform: none;
}
</style>
