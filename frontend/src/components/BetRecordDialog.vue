<template>
  <view v-if="visible" class="dialog-overlay" @tap="handleClose">
    <view class="dialog-content" @tap.stop>
      <view class="dialog-header">
        <text class="dialog-title">{{ editingBet ? "编辑投注记录" : "新增投注记录" }}</text>
        <button class="close-btn" @tap="handleClose">×</button>
      </view>

      <scroll-view class="dialog-body" scroll-y>
        <BetForm ref="betFormRef" :editing-bet="editingBet" :is-editing-betting="isEditingBetting" :hide-submit-button="true" @submit="handleSubmit" @cancelEdit="handleCancelEdit" />
      </scroll-view>

      <view class="dialog-footer">
        <view v-if="isEditingBetting" class="footer-buttons">
          <button class="cancel-footer-btn" @tap="handleClose">取消</button>
          <button class="settle-btn" @tap="handleSettle">结算</button>
        </view>
        <view v-else class="footer-buttons">
          <button class="save-footer-btn" @tap="submitFormWithStatus('saved')">保存</button>
          <button class="bet-footer-btn" @tap="submitFormWithStatus('betting')">投注</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { nextTick, ref, computed, watch } from "vue";
import BetForm from "@/components/BetForm.vue";
import { useBetStore } from "@/stores/betStore";

const betStore = useBetStore();

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  editingBet: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["update:visible", "success"]);

const betFormRef = ref(null);

const isEditingBetting = computed(() => {
  return props.editingBet && props.editingBet.status === "betting";
});

watch(
  () => props.visible,
  (visible) => {
    if (visible && !props.editingBet) {
      nextTick(() => {
        betFormRef.value?.resetForm?.();
      });
    }
  }
);

function handleClose() {
  emit("update:visible", false);
}

function submitFormWithStatus(status) {
  betFormRef.value?.handleSubmitWithStatus?.(status);
}

async function handleSubmit(payload) {
  try {
    if (payload.id) {
      await betStore.updateBet(payload.id, payload);
      uni.showToast({ title: "记录已更新", icon: "success" });
    } else {
      await betStore.addBet(payload);
      const statusText = payload.status === "betting" ? "投注成功" : "保存成功";
      uni.showToast({ title: statusText, icon: "success" });
    }

    // 先关闭弹窗
    emit("update:visible", false);

    // 延迟触发 success 回调，确保弹窗 DOM 已移除，避免与页面跳转冲突
    setTimeout(() => {
      emit("success", payload);
    }, 100);
  } catch (error) {
    console.error("Submit error:", error);
    uni.showToast({ title: error.message || "操作失败", icon: "none" });
  }
}

function handleSettle() {
  betFormRef.value?.handleSubmitWithStatus?.("settled");
}

function handleCancelEdit() {
  emit("update:visible", false);
}

defineExpose({
  open: () => emit("update:visible", true),
  close: handleClose,
});
</script>

<style lang="scss" scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 500;
  padding: 40rpx;
  box-sizing: border-box;
}

.dialog-content {
  background: #ffffff;
  border-radius: 24rpx;
  width: 100%;
  max-width: 680rpx;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8rpx 32rpx rgba(0, 0, 0, 0.2);
  box-sizing: border-box;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24rpx;
  border-bottom: 1px solid rgba(13, 148, 136, 0.1);
  flex-shrink: 0;
  box-sizing: border-box;
}

.dialog-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #0d9488;
  flex: 1;
}

.close-btn {
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: rgba(13, 148, 136, 0.1);
  border: none;
  font-size: 40rpx;
  color: #0d9488;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
  margin-left: 20rpx;
}

.close-btn:active {
  background: rgba(13, 148, 136, 0.2);
}

.dialog-body {
  flex: 1;
  padding: 24rpx;
  overflow-y: auto;
  box-sizing: border-box;
}

.dialog-footer {
  padding: 16rpx 24rpx;
  padding-bottom: calc(16rpx + env(safe-area-inset-bottom));
  border-top: 1px solid rgba(13, 148, 136, 0.1);
  background: #ffffff;
  flex-shrink: 0;
  box-sizing: border-box;
}

.footer-buttons {
  display: flex;
  gap: 12rpx;
  width: 100%;

  button {
    flex: 1;
    height: 72rpx;
    border-radius: 12rpx;
    font-size: 26rpx;
    font-weight: 600;
    border: none;
    transition: all 0.2s;
    box-sizing: border-box;
  }
}

.save-footer-btn {
  background: #f5f5f5;
  color: #666;

  &:active {
    background: #e5e5e5;
    transform: translateY(1rpx);
  }
}

.bet-footer-btn {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  color: #ffffff;
  box-shadow: 0 4rpx 16rpx rgba(13, 148, 136, 0.3);

  &:active {
    transform: translateY(1rpx);
    box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);
  }
}

.cancel-footer-btn {
  background: #f5f5f5;
  color: #666;

  &:active {
    background: #e5e5e5;
    transform: translateY(1rpx);
  }
}

.settle-btn {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: #ffffff;
  box-shadow: 0 4rpx 16rpx rgba(16, 185, 129, 0.3);

  &:active {
    transform: translateY(1rpx);
    box-shadow: 0 2rpx 8rpx rgba(16, 185, 129, 0.3);
  }
}
</style>
