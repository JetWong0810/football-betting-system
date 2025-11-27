<template>
  <view class="page-wrapper">
    <view class="content">
      <view class="form-card">
        <view class="card-header">
          <text class="title">完善头像昵称</text>
          <text class="subtitle">头像昵称仅用于展示，可在登录后修改</text>
        </view>
        <view class="form-row avatar-row">
          <text class="label">头像</text>
          <view class="avatar-field">
            <image class="avatar-preview" :src="avatarPreview" mode="aspectFill" />
            <button class="choose-avatar-btn" open-type="chooseAvatar" @chooseavatar="handleChooseAvatar" hover-class="choose-avatar-btn-active">选择微信头像</button>
          </view>
        </view>

        <view class="divider" />

        <view class="form-row">
          <text class="label">昵称</text>
          <input class="nickname-input" type="nickname" placeholder="请输入昵称" :value="nickname" maxlength="32" confirm-type="done" @input="handleNicknameInput" />
        </view>

        <text class="tip-text">昵称限 2-32 个字符</text>
      </view>

      <button class="confirm-btn" :disabled="loading" @tap="handleSubmit" hover-class="confirm-btn-active">
        <text v-if="loading">登录中...</text>
        <text v-else>确认并登录</text>
      </button>
    </view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { useUserStore } from "@/stores/userStore";

const userStore = useUserStore();
const loading = ref(false);
const nickname = ref("");
const avatarPreview = ref("https://thirdwx.qlogo.cn/mmopen/vi_32/Q0j4TwGTfTJicicP7ic0YgicOQ8J0ibk5UnJhHLib3dIYh1aS7Qic0NiaP1gQibg3VGZoibm5lZiaQXL4d1CjibU2iaZD4Vvibg/132");
const avatarTempPath = ref("");
const avatarFileExt = ref("png");
const redirectUrl = ref("/pages/home/home");
const tabPages = ["/pages/home/home", "/pages/matches/list", "/pages/record/record", "/pages/profile/profile"];

onLoad((options) => {
  if (options?.redirect) {
    redirectUrl.value = decodeURIComponent(options.redirect);
  }
});

function handleChooseAvatar(event) {
  const url = event?.detail?.avatarUrl;
  if (url) {
    avatarTempPath.value = normalizeWechatFilePath(url);
    avatarPreview.value = url;
    avatarFileExt.value = extractFileExtension(url);
  }
}

function handleNicknameInput(event) {
  nickname.value = event?.detail?.value || "";
}

function extractFileExtension(path) {
  if (!path) {
    return "png";
  }
  const cleaned = path.split("?")[0];
  const parts = cleaned.split(".");
  if (parts.length > 1) {
    return parts.pop().toLowerCase();
  }
  return "png";
}

function convertAvatarToBase64(filePath) {
  return new Promise((resolve, reject) => {
    if (!filePath) {
      reject(new Error("请先选择头像"));
      return;
    }
    // #ifdef MP-WEIXIN
    const normalizedPath = normalizeWechatFilePath(filePath);
    uni.getFileSystemManager().readFile({
      filePath: normalizedPath,
      encoding: "base64",
      success: (res) => resolve(res.data),
      fail: (err) => reject(new Error(err?.errMsg || "读取头像失败")),
    });
    // #endif
    // #ifndef MP-WEIXIN
    reject(new Error("当前平台不支持头像读取"));
    // #endif
  });
}

function normalizeWechatFilePath(path) {
  if (!path) {
    return "";
  }
  if (path.startsWith("http://tmp/") || path.startsWith("https://tmp/")) {
    return path.replace(/^https?:\/\//, "wxfile://");
  }
  return path;
}

async function handleSubmit() {
  if (loading.value) {
    return;
  }

  // #ifndef MP-WEIXIN
  uni.showToast({
    title: "请在微信小程序内使用",
    icon: "none",
  });
  return;
  // #endif

  const trimmedNickname = nickname.value.trim();
  if (!trimmedNickname) {
    uni.showToast({
      title: "请输入昵称",
      icon: "none",
    });
    return;
  }

  if (trimmedNickname.length < 2) {
    uni.showToast({
      title: "昵称至少 2 个字符",
      icon: "none",
    });
    return;
  }

  if (!avatarTempPath.value) {
    uni.showToast({
      title: "请选择头像",
      icon: "none",
    });
    return;
  }

  loading.value = true;

  try {
    const avatarBase64 = await convertAvatarToBase64(avatarTempPath.value);
    await userStore.loginWithWeChatMiniProgram({
      requireProfile: false,
      providedNickname: trimmedNickname,
      avatarBase64,
      avatarFileExt: avatarFileExt.value,
    });

    uni.showToast({
      title: "登录成功",
      icon: "success",
      duration: 1400,
    });

    setTimeout(() => {
      navigateAfterLogin();
    }, 1200);
  } catch (error) {
    console.error("完善资料登录失败:", error);
    uni.showToast({
      title: error?.data?.detail || error?.message || "登录失败，请重试",
      icon: "none",
      duration: 2000,
    });
  } finally {
    loading.value = false;
  }
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
  background: #f7f9fb;
  padding: 40rpx 30rpx 60rpx;
  display: flex;
  flex-direction: column;
}

.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 32rpx;
}

.form-card {
  background: #ffffff;
  border-radius: 24rpx;
  padding: 32rpx;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  border: 2rpx solid #eef2f7;
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.title {
  font-size: 32rpx;
  font-weight: 600;
  color: #111827;
}

.subtitle {
  font-size: 24rpx;
  color: #94a3b8;
}

.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.avatar-row {
  align-items: center;
}

.label {
  font-size: 28rpx;
  color: #0f172a;
  font-weight: 500;
}

.avatar-field {
  display: flex;
  align-items: center;
  gap: 24rpx;
}

.avatar-preview {
  width: 104rpx;
  height: 104rpx;
  border-radius: 50%;
  background: #f8fafc;
  border: 2rpx solid #d0e5ff;
}

.choose-avatar-btn {
  height: 72rpx;
  padding: 0 32rpx;
  border-radius: 8rpx;
  border: 2rpx dashed #0ea5e9;
  color: #0f172a;
  font-size: 26rpx;
  background: rgba(14, 165, 233, 0.08);
}

.choose-avatar-btn-active {
  opacity: 0.8;
}

.divider {
  height: 1px;
  background: rgba(148, 163, 184, 0.3);
}

.nickname-input {
  flex: 1;
  text-align: right;
  font-size: 28rpx;
  padding: 0 12rpx;
  color: #0f172a;
}

.nickname-input::placeholder {
  color: #cbd5f5;
}

.tip-text {
  font-size: 22rpx;
  color: #94a3b8;
  margin-top: 8rpx;
}

.confirm-btn {
  width: 100%;
  height: 96rpx;
  border-radius: 8rpx;
  background: #0d9488;
  color: #ffffff;
  font-size: 32rpx;
  font-weight: 600;
  border: none;
  box-shadow: 0 12rpx 20rpx rgba(13, 148, 136, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-btn-active {
  opacity: 0.9;
}

.confirm-btn[disabled] {
  opacity: 0.6;
}
</style>
