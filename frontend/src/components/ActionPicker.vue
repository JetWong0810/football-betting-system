<template>
  <view v-if="visible" class="overlay" @tap="handleCancel">
    <view class="sheet" @tap.stop>
      <view class="sheet-header">
        <text class="sheet-cancel" @tap="handleCancel">取消</text>
        <text class="sheet-title">{{ title }}</text>
        <text class="sheet-confirm" @tap="handleConfirm">确定</text>
      </view>
      <scroll-view class="sheet-options" scroll-y>
        <view
          v-for="(item, idx) in options"
          :key="idx"
          class="sheet-option"
          :class="{ active: idx === selectedIndex }"
          @tap="selectedIndex = idx"
        >
          <text class="option-label">{{ item.label || item }}</text>
          <view class="option-check" v-if="idx === selectedIndex"></view>
        </view>
      </scroll-view>
    </view>
  </view>
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

<style lang="scss" scoped>
.overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
  z-index: 9999;
}

.sheet {
  width: 100%;
  background: #ffffff;
  border-radius: 16rpx 16rpx 0 0;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1px solid #f0f1f3;
}

.sheet-cancel {
  font-size: 28rpx;
  color: #6b7280;
}

.sheet-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1f2937;
}

.sheet-confirm {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
}

.sheet-options {
  padding: 8rpx 0;
  max-height: 600rpx;
}

.sheet-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 32rpx;
}

.sheet-option.active {
  background: #f0fdfa;
}

.sheet-option.active .option-label {
  color: #0d9488;
  font-weight: 600;
}

.option-label {
  font-size: 28rpx;
  color: #374151;
}

.option-check {
  width: 20rpx;
  height: 20rpx;
  border-radius: 50%;
  background: #0d9488;
}
</style>
