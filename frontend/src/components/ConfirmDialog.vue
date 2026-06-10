<template>
  <view v-if="visible" class="overlay" @tap="confirmCancel">
    <view class="dialog" @tap.stop>
      <text class="dialog-title" v-if="title">{{ title }}</text>
      <text class="dialog-content">{{ content }}</text>
      <view class="dialog-actions">
        <text class="btn cancel" v-if="cancelText" @tap="confirmCancel">{{ cancelText }}</text>
        <text class="btn confirm" :class="[confirmType, { full: !cancelText }]" @tap="confirmOk">{{ confirmText }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { useConfirm } from "@/utils/confirm";

const { visible, title, content, confirmText, cancelText, confirmType, confirmOk, confirmCancel } = useConfirm();
</script>

<style lang="scss" scoped>
.overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.dialog {
  width: 560rpx;
  background: #ffffff;
  border-radius: 6rpx;
  padding: 40rpx 32rpx 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.dialog-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 16rpx;
}

.dialog-content {
  font-size: 26rpx;
  color: #6b7280;
  text-align: center;
  line-height: 1.5;
  margin-bottom: 36rpx;
}

.dialog-actions {
  display: flex;
  width: 100%;
  gap: 16rpx;
}

.btn {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  border-radius: 6rpx;
  font-size: 28rpx;
  font-weight: 500;
}

.btn.cancel {
  background: #f4f5f7;
  color: #6b7280;
}

.btn.cancel:active {
  background: #e5e7eb;
}

.btn.confirm {
  color: #ffffff;
}

.btn.confirm.primary {
  background: #0d9488;
}

.btn.confirm.primary:active {
  background: #0f766e;
}

.btn.confirm.danger {
  background: #ef4444;
}

.btn.confirm.danger:active {
  background: #dc2626;
}
</style>
