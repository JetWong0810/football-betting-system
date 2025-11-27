<template>
  <view v-if="visible" class="dialog-overlay" @tap="handleClose">
    <view class="dialog-content" @tap.stop>
      <view class="dialog-header">
        <text class="dialog-title">{{ editingBet ? "编辑投注记录" : "新增投注记录" }}</text>
        <view class="dialog-header-actions">
          <button class="ocr-btn" @tap="handleOcrClick" :disabled="ocrLoading">
            <text class="ocr-icon">📷</text>
            <text class="ocr-text">{{ ocrLoading ? "识别中" : "识别" }}</text>
          </button>
          <button class="close-btn" @tap="handleClose">×</button>
        </view>
      </view>

      <scroll-view class="dialog-body" scroll-y>
        <BetForm ref="betFormRef" :editing-bet="editingBet" :is-editing-betting="isEditingBetting" :hide-submit-button="true" :ocr-loading="ocrLoading" @submit="handleSubmit" @cancelEdit="handleCancelEdit" />
      </scroll-view>

      <!-- OCR 识别加载遮罩 -->
      <view v-if="ocrLoading" class="ocr-loading-overlay">
        <view class="loading-content">
          <view class="loading-spinner"></view>
          <text class="loading-text">识别中，请稍候...</text>
          <text class="loading-hint">预计需要 5-10 秒</text>
        </view>
      </view>

      <view class="dialog-footer">
        <view v-if="isEditingBetting" class="footer-buttons">
          <button class="cancel-footer-btn" @tap="handleClose" :disabled="ocrLoading">取消</button>
          <button class="settle-btn" @tap="handleSettle" :disabled="ocrLoading">结算</button>
        </view>
        <view v-else class="footer-buttons">
          <button class="save-footer-btn" @tap="submitFormWithStatus('saved')" :disabled="ocrLoading">保存</button>
          <button class="bet-footer-btn" @tap="submitFormWithStatus('betting')" :disabled="ocrLoading">投注</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { nextTick, ref, computed, watch } from "vue";
import BetForm from "@/components/BetForm.vue";
import { useBetStore } from "@/stores/betStore";
import { request } from "@/utils/http";

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
const ocrLoading = ref(false);

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

// OCR 相关：在弹窗标题右侧上传图片并自动填充表单
function handleOcrClick() {
  if (ocrLoading.value) return;

  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    sourceType: ["album", "camera"],
    success: (res) => {
      const tempFilePath = res.tempFilePaths[0];

      // #ifdef H5
      // H5 环境：通过 fetch + FileReader 读取 base64
      fetch(tempFilePath)
        .then((response) => response.blob())
        .then((blob) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            const base64 = e.target.result.split(",")[1];
            startOcr(base64);
          };
          reader.onerror = (err) => {
            console.error("读取图片失败:", err);
            uni.showToast({ title: "读取图片失败", icon: "none" });
          };
          reader.readAsDataURL(blob);
        })
        .catch((err) => {
          console.error("读取图片失败:", err);
          uni.showToast({ title: "读取图片失败", icon: "none" });
        });
      // #endif

      // #ifndef H5
      // 小程序等环境：FileSystemManager 读取 base64
      uni.getFileSystemManager().readFile({
        filePath: tempFilePath,
        encoding: "base64",
        success: (readRes) => {
          startOcr(readRes.data);
        },
        fail: (err) => {
          console.error("读取图片失败:", err);
          uni.showToast({ title: "读取图片失败", icon: "none" });
        },
      });
      // #endif
    },
    fail: (err) => {
      console.error("选择图片失败:", err);
    },
  });
}

async function startOcr(imageBase64) {
  if (!imageBase64) return;
  ocrLoading.value = true;

  try {
    const result = await request({
      url: "/api/ocr/parse-bet-image",
      method: "POST",
      timeout: 60000,
      data: { image_base64: imageBase64 },
    });

    if (!result.success) {
      uni.showToast({
        title: result.error || "识别失败",
        icon: "none",
        duration: 3000,
      });
      return;
    }

    const betData = result.data;
    if (!betData || !betData.legs || !betData.legs.length) {
      uni.showToast({ title: "未识别到有效投注信息", icon: "none" });
      return;
    }

    // 使用 BetForm 暴露的方法填充表单
    betFormRef.value?.fillFromOcr?.(betData);

    uni.showToast({ title: "识别成功，已填充表单", icon: "success" });
  } catch (error) {
    console.error("OCR识别失败:", error);
    uni.showToast({
      title: error.message || "识别失败",
      icon: "none",
      duration: 3000,
    });
  } finally {
    ocrLoading.value = false;
  }
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
  box-shadow: 0 8rpx 32rpx rgba(0, 0, 0, 0.16);
  box-sizing: border-box;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 22rpx 24rpx;
  border-bottom: 1px solid rgba(13, 148, 136, 0.06);
  flex-shrink: 0;
  box-sizing: border-box;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
}

.dialog-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #ffffff;
  flex: 1;
}

.dialog-header-actions {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.ocr-btn {
  display: flex;
  align-items: center;
  gap: 6rpx;
  padding: 0 18rpx;
  height: 44rpx;
  border-radius: 8rpx;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.45);
  font-size: 24rpx;
  color: #ffffff;
}

.ocr-btn:active {
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(1rpx);
}

.ocr-btn:disabled {
  opacity: 0.7;
}

.ocr-icon {
  font-size: 26rpx;
}

.ocr-text {
  font-size: 24rpx;
}

.close-btn {
  width: 44rpx;
  height: 44rpx;
  line-height: 44rpx;
  text-align: center;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.45);
  border-radius: 50%;
  color: #ffffff;
  font-size: 36rpx;
  font-weight: 300;
  padding: 0;
}

.close-btn:active {
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(1rpx);
}

/* OCR 识别加载遮罩 */
.ocr-loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8rpx);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: 24rpx;
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20rpx;
}

.loading-spinner {
  width: 80rpx;
  height: 80rpx;
  border: 6rpx solid rgba(13, 148, 136, 0.1);
  border-top-color: #0d9488;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.loading-text {
  font-size: 28rpx;
  color: #0d9488;
  font-weight: 600;
}

.loading-hint {
  font-size: 22rpx;
  color: #6b7280;
}

/* 按钮禁用样式 */
.save-footer-btn:disabled,
.bet-footer-btn:disabled,
.settle-btn:disabled,
.cancel-footer-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.45);
  font-size: 32rpx;
  color: #ffffff;
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
    border-radius: 8rpx;
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
