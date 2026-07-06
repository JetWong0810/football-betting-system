<template>
  <teleport to="body">
    <view v-if="visible" class="ap-overlay" @tap="handleCancel">
      <view class="ap-sheet" @tap.stop>
        <view class="ap-header">
          <text class="ap-cancel" @tap="handleCancel">取消</text>
          <text class="ap-title">{{ title }}</text>
          <text class="ap-confirm" @tap="handleConfirm">确定</text>
        </view>
        <view class="ap-options">
          <view
            v-for="(item, idx) in options"
            :key="idx"
            class="ap-option"
            :class="{ active: idx === selectedIndex }"
            @tap="selectedIndex = idx"
          >
            <text class="ap-option-label">{{ item.label || item }}</text>
            <view class="ap-option-check" v-if="idx === selectedIndex"></view>
          </view>
        </view>
      </view>
    </view>
  </teleport>
</template>

<script setup>
import { ref } from "vue";

const visible = ref(false);
const title = ref("");
const options = ref([]);
const selectedIndex = ref(0);
let resolvePromise = null;

function show(opts = {}) {
  title.value = opts.title || "请选择";
  options.value = opts.options || [];
  selectedIndex.value = opts.defaultIndex || 0;
  visible.value = true;
  return new Promise((resolve) => {
    resolvePromise = resolve;
  });
}

function handleConfirm() {
  visible.value = false;
  if (resolvePromise) resolvePromise({ index: selectedIndex.value, value: options.value[selectedIndex.value] });
}

function handleCancel() {
  visible.value = false;
  if (resolvePromise) resolvePromise(null);
}

defineExpose({ show });
</script>

<style lang="scss">
.ap-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
  z-index: 99999;
}

.ap-sheet {
  width: 100%;
  background: #ffffff;
  border-radius: 16rpx 16rpx 0 0;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.ap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1px solid #f0f1f3;
  flex-shrink: 0;
}

.ap-cancel {
  font-size: 28rpx;
  color: #6b7280;
}

.ap-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1f2937;
}

.ap-confirm {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
}

.ap-options {
  padding: 8rpx 0;
  padding-bottom: calc(8rpx + env(safe-area-inset-bottom));
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.ap-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 32rpx;
}

.ap-option.active {
  background: #f0fdfa;
}

.ap-option.active .ap-option-label {
  color: #0d9488;
  font-weight: 600;
}

.ap-option-label {
  font-size: 28rpx;
  color: #374151;
}

.ap-option-check {
  width: 20rpx;
  height: 20rpx;
  border-radius: 50%;
  background: #0d9488;
}
</style>
