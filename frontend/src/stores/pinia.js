"use strict";
import { createPinia } from "pinia";

/**
 * 全局唯一的 Pinia 实例，便于在非组件环境下获取 store
 * （如 utils/http.js 处理 401 时重置用户状态）
 */
const pinia = createPinia();

export default pinia;
