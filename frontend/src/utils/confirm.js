import { ref } from "vue";

const visible = ref(false);
const title = ref("");
const content = ref("");
const confirmText = ref("确定");
const cancelText = ref("取消");
const confirmType = ref("primary");
let resolvePromise = null;

export function showConfirm(options = {}) {
  title.value = options.title || "";
  content.value = options.content || "";
  confirmText.value = options.confirmText || "确定";
  cancelText.value = options.cancelText || "取消";
  confirmType.value = options.type || "primary";
  visible.value = true;
  return new Promise((resolve) => {
    resolvePromise = resolve;
  });
}

export function confirmOk() {
  visible.value = false;
  if (resolvePromise) resolvePromise(true);
  resolvePromise = null;
}

export function confirmCancel() {
  visible.value = false;
  if (resolvePromise) resolvePromise(false);
  resolvePromise = null;
}

export function useConfirm() {
  return { visible, title, content, confirmText, cancelText, confirmType, confirmOk, confirmCancel };
}
