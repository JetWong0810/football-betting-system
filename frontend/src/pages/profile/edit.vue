<template>
  <view class="edit-profile">
    <view class="card">
      <!-- 头像 -->
      <view class="row avatar-row" @tap="chooseAvatar">
        <text class="row-label">头像</text>
        <view class="avatar-wrap">
          <image class="avatar" :src="form.avatar || defaultAvatar" mode="aspectFill" />
          <text class="avatar-hint">点击修改</text>
        </view>
      </view>
      <view class="divider"></view>

      <!-- 昵称 -->
      <view class="row">
        <text class="row-label">昵称</text>
        <input
          class="row-input"
          v-model="form.nickname"
          placeholder="请输入昵称"
          maxlength="20"
        />
      </view>
      <view class="divider"></view>

      <!-- 用户名（只读） -->
      <view class="row">
        <text class="row-label">用户名</text>
        <text class="row-static">{{ userStore.user?.username || '-' }}</text>
      </view>
    </view>

    <view class="card" v-if="canEditContact">
      <view class="row">
        <text class="row-label">手机号</text>
        <input
          class="row-input"
          v-model="form.phone"
          placeholder="选填"
          maxlength="11"
          type="number"
        />
      </view>
      <view class="divider"></view>
      <view class="row">
        <text class="row-label">邮箱</text>
        <input class="row-input" v-model="form.email" placeholder="选填" maxlength="50" />
      </view>
    </view>

    <view class="actions">
      <button class="save-btn" :disabled="saving" @tap="handleSave">
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </view>
  </view>
</template>

<script setup>
import { reactive, ref, computed } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { useUserStore } from "@/stores/userStore";
import { requireAuth } from "@/utils/auth";

const userStore = useUserStore();
const defaultAvatar =
  "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgdmlld0JveD0iMCAwIDEwMCAxMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIiByeD0iNTAiIGZpbGw9IiMwZDk0ODgiLz4KPHBhdGggZD0iTTUwIDMwQzQwLjMzNTggMzAgMzIgMzguMzM1OCAzMiA0OEMzMiA1Ny42NjQyIDQwLjMzNTggNjYgNTAgNjZDNjkuNjY0MiA2NiA3OCA1Ny42NjQyIDc4IDQ4Qzc4IDM4LjMzNTggNjkuNjY0MiAzMCA1MCAzMFoiIGZpbGw9IndoaXRlIi8+CjxwYXRoIGQ9Ik0yMCA4MEMyMCA3My4zNzI2IDI1LjM3MjYgNjggMzIgNjhINjggNzQuNjI3NCA2OCA4MCA2OCA4NkM2OCA5Mi42Mjc0IDYyLjYyNzQgOTggNTYgOThINDBDMzMuMzcyNiA5OCAyOCA5Mi42Mjc0IDI4IDg2VjgwSDIwWiIgZmlsbD0id2hpdGUiLz4KPC9zdmc+";

const form = reactive({
  nickname: "",
  phone: "",
  email: "",
  avatar: "",
});
const saving = ref(false);

// H5 端可编辑联系方式；微信端手机号走 bind-phone 流程
const canEditContact = computed(() => {
  // #ifdef H5
  return true;
  // #endif
  // #ifndef H5
  return false;
  // #endif
});

onShow(() => {
  if (!requireAuth()) return;
  syncForm();
});

function syncForm() {
  const u = userStore.user || {};
  form.nickname = u.nickname || "";
  form.phone = u.phone || "";
  form.email = u.email || "";
  form.avatar = u.avatar || "";
}

function chooseAvatar() {
  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    success: (res) => {
      const tempPath = res.tempFilePaths[0];
      // #ifdef H5
      // H5 转 base64 存储（无独立上传服务时的一种务实方案）
      const xhr = new XMLHttpRequest();
      xhr.onload = () => {
        const reader = new FileReader();
        reader.onload = () => {
          form.avatar = reader.result;
        };
        reader.readAsDataURL(xhr.response);
      };
      xhr.open("GET", tempPath, true);
      xhr.responseType = "blob";
      xhr.send();
      // #endif
      // #ifndef H5
      form.avatar = tempPath;
      // #endif
    },
  });
}

async function handleSave() {
  if (!form.nickname.trim()) {
    uni.showToast({ title: "请输入昵称", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const payload = { nickname: form.nickname.trim() };
    if (form.avatar) payload.avatar = form.avatar;
    if (canEditContact.value) {
      if (form.phone) payload.phone = form.phone;
      if (form.email) payload.email = form.email;
    }
    await userStore.updateProfile(payload);
    uni.showToast({ title: "保存成功", icon: "success" });
    setTimeout(() => uni.navigateBack(), 800);
  } catch (e) {
    uni.showToast({ title: e.message || "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.edit-profile {
  min-height: 100vh;
  background: linear-gradient(180deg, #ecfdf5 0%, #f0fdf9 100%);
  padding: 24rpx;
  box-sizing: border-box;
}

.card {
  @include card;
  padding: 0 24rpx;
  margin-bottom: 24rpx;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 0;
  min-height: 88rpx;
  box-sizing: border-box;
}

.avatar-row {
  cursor: pointer;
}

.row-label {
  font-size: 26rpx;
  color: #374151;
  flex-shrink: 0;
}

.row-input {
  flex: 1;
  text-align: right;
  font-size: 26rpx;
  color: #111827;
}

.row-static {
  font-size: 26rpx;
  color: #9ca3af;
}

.avatar-wrap {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.avatar {
  width: 80rpx;
  height: 80rpx;
  border-radius: 50%;
  background: #e5e7eb;
}

.avatar-hint {
  font-size: 22rpx;
  color: #9ca3af;
}

.divider {
  height: 1px;
  background: #f3f4f6;
}

.actions {
  padding: 24rpx 0;
}

.save-btn {
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 10rpx;
  border: none;
}

.save-btn[disabled] {
  opacity: 0.6;
}
</style>
