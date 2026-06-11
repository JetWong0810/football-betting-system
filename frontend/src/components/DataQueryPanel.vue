<template>
  <view v-if="visible" class="panel-mask" @tap.self="close">
    <view class="panel" :class="{ fullscreen: isFullscreen }">
      <!-- 顶部 -->
      <view class="panel-top">
        <view class="handle-bar" @tap="toggleFullscreen"></view>
        <view class="panel-header">
          <text class="panel-title">数据查询</text>
          <text class="panel-close" @tap="close">收起</text>
        </view>
      </view>

      <!-- 消息列表 -->
      <scroll-view class="msg-list" scroll-y :scroll-into-view="scrollTarget" scroll-with-animation>
        <view class="msg-inner">
          <!-- 欢迎 -->
          <view v-if="messages.length === 0" class="welcome">
            <text class="welcome-lead">输入问题，自动查询数据库</text>
            <text class="welcome-sub">支持世界杯(2014-2022) + 竞彩(2026)</text>
            <view class="example-list">
              <view class="example-item" v-for="(q, i) in exampleQuestions" :key="i" @tap="sendExample(q)">
                <text class="example-text">{{ q }}</text>
              </view>
            </view>
          </view>

          <!-- 消息 -->
          <view v-for="(msg, idx) in messages" :key="idx" :id="'msg-' + idx" class="msg-row" :class="msg.role">
            <!-- 用户 -->
            <view v-if="msg.role === 'user'" class="user-msg">
              <text class="user-text">{{ msg.content }}</text>
            </view>

            <!-- AI -->
            <view v-else class="ai-msg">
              <!-- Loading -->
              <view v-if="msg.loading" class="loading-state">
                <view class="loader-track">
                  <view class="loader-fill"></view>
                </view>
                <text class="loader-label">{{ msg.loadingText || '分析中' }}</text>
              </view>

              <template v-else>
                <!-- 数据源 + 记录数 -->
                <view class="result-meta">
                  <text class="meta-source">{{ msg.source }}</text>
                  <text v-if="msg.count != null" class="meta-count">{{ msg.count }} 条</text>
                </view>

                <!-- 统计摘要 -->
                <view v-if="msg.summary" class="stat-row">
                  <view v-for="(item, si) in msg.summary" :key="si" class="stat-block">
                    <text class="stat-num">{{ item.value }}</text>
                    <text class="stat-label">{{ item.label }}</text>
                  </view>
                </view>

                <!-- 表格 -->
                <scroll-view v-if="msg.table" class="table-wrap" scroll-x>
                  <view class="data-table">
                    <view class="dt-head">
                      <text v-for="col in msg.table.columns" :key="col" class="dt-th">{{ col }}</text>
                    </view>
                    <view v-for="(row, ri) in msg.table.rows" :key="ri" class="dt-row">
                      <text v-for="(col, ci) in msg.table.columns" :key="ci" class="dt-td" :class="{ 'td-first': ci === 0 }">{{ row[col] ?? '-' }}</text>
                    </view>
                  </view>
                </scroll-view>

                <!-- 分析文字 -->
                <text v-if="msg.text" class="result-text">{{ msg.text }}</text>

                <!-- SQL -->
                <view v-if="msg.sql" class="sql-section">
                  <text class="sql-toggle" @tap="msg.showSql = !msg.showSql">{{ msg.showSql ? '收起SQL' : '查看SQL' }}</text>
                  <view v-if="msg.showSql" class="sql-pre">
                    <text class="sql-code">{{ msg.sql }}</text>
                  </view>
                </view>
              </template>
            </view>
          </view>
        </view>
      </scroll-view>

      <!-- 快捷标签 -->
      <scroll-view v-if="showQuickTags && messages.length > 0" class="quick-bar" scroll-x>
        <view class="quick-inner">
          <view class="qtag" v-for="(q, i) in quickTags" :key="i" @tap="sendExample(q)">
            <text>{{ q }}</text>
          </view>
        </view>
      </scroll-view>

      <!-- 输入 -->
      <view class="input-area">
        <view class="input-row">
          <input
            class="query-input"
            v-model="inputText"
            placeholder="输入你的问题..."
            placeholder-class="input-placeholder"
            confirm-type="send"
            @confirm="sendMessage"
            :disabled="sending"
          />
          <view class="send-btn" :class="{ ready: inputText.trim() && !sending }" @tap="sendMessage">
            <text class="send-text">发送</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, nextTick, computed } from 'vue'
import { BASE_URL } from '@/utils/http'

const props = defineProps({
  visible: { type: Boolean, default: false }
})
const emit = defineEmits(['close'])

const messages = ref([])
const inputText = ref('')
const sending = ref(false)
const scrollTarget = ref('')
const isFullscreen = ref(false)

const exampleQuestions = [
  '法国vs尼日利亚盘口数据',
  '历届世界杯最大冷门',
  '英超让1球上盘赢盘率',
  '2022阿根廷所有比赛亚盘',
]

const quickTags = [
  '上盘率',
  '冷门统计',
  '让1球',
  '大小球',
  '水位异动',
  '盘口反转',
]

const showQuickTags = computed(() => !sending.value)

function close() {
  emit('close')
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function sendExample(q) {
  inputText.value = q
  sendMessage()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sending.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  sending.value = true

  await nextTick()
  scrollToBottom()

  const aiMsg = { role: 'ai', loading: true, loadingText: '生成SQL' }
  messages.value.push(aiMsg)
  await nextTick()
  scrollToBottom()

  try {
    const res = await queryApi(text)
    aiMsg.loading = false

    if (!res.success) {
      aiMsg.text = res.error || '查询失败，换个问法试试'
      aiMsg.sql = res.sql || null
      aiMsg.source = res.db === 'worldcup' ? '世界杯' : '竞彩'
    } else {
      aiMsg.source = res.source
      aiMsg.sql = res.sql
      aiMsg.count = res.count
      aiMsg.showSql = false

      if (res.rows.length <= 3 && res.columns.length <= 5) {
        aiMsg.summary = res.columns.map((col, i) => ({
          label: col,
          value: res.rows[0]?.[col] ?? '-'
        }))
      } else {
        aiMsg.table = {
          columns: res.columns,
          rows: res.rows.slice(0, 20),
        }
      }
    }
  } catch (e) {
    aiMsg.loading = false
    aiMsg.text = '网络错误，请检查后端服务是否启动'
  }

  sending.value = false
  await nextTick()
  scrollToBottom()
}

async function queryApi(question) {
  const url = BASE_URL.replace(/\/api$/, '') + '/api/nl-query'
  const resp = await new Promise((resolve, reject) => {
    uni.request({
      url,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { question, model: 'claude' },
      timeout: 60000,
      success: (res) => resolve(res.data),
      fail: (err) => reject(err),
    })
  })
  return resp
}

function scrollToBottom() {
  scrollTarget.value = ''
  nextTick(() => {
    scrollTarget.value = 'msg-' + (messages.value.length - 1)
  })
}
</script>

<style lang="scss" scoped>
.panel-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 1000;
  display: flex;
  align-items: flex-end;
}

.panel {
  width: 100%;
  height: 72vh;
  background: #f0fdf9;
  border-radius: 20rpx 20rpx 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: height 0.25s ease;
  box-shadow: 0 -4rpx 30rpx rgba(13, 148, 136, 0.08);

  &.fullscreen {
    height: 94vh;
  }
}

.panel-top {
  flex-shrink: 0;
  padding: 12rpx 32rpx 0;
}

.handle-bar {
  width: 48rpx;
  height: 6rpx;
  background: #cbd5e1;
  border-radius: 3rpx;
  margin: 0 auto 14rpx;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 18rpx;
  border-bottom: 1px solid rgba(13, 148, 136, 0.1);
}

.panel-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #1c1c1c;
}

.panel-close {
  font-size: 24rpx;
  color: #94a3b8;
}

// 消息列表 - scroll-view 内部用 view 包裹控制 padding
.msg-list {
  flex: 1;
  overflow: hidden;
}

.msg-inner {
  padding: 24rpx 32rpx;
}

// 欢迎
.welcome {
  padding: 8rpx 0;
}

.welcome-lead {
  display: block;
  font-size: 28rpx;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 6rpx;
}

.welcome-sub {
  display: block;
  font-size: 23rpx;
  color: #64748b;
  margin-bottom: 28rpx;
}

.example-list {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.example-item {
  background: #ffffff;
  border: 1px solid rgba(13, 148, 136, 0.12);
  border-radius: 6rpx;
  padding: 20rpx 22rpx;
  box-sizing: border-box;

  &:active {
    background: #ecfdf5;
    border-color: rgba(13, 148, 136, 0.3);
  }
}

.example-text {
  font-size: 26rpx;
  color: #334155;
}

// 用户消息
.msg-row {
  margin-bottom: 24rpx;

  &.user {
    display: flex;
    justify-content: flex-end;
  }
}

.user-msg {
  max-width: 82%;
  background: #0d9488;
  border-radius: 6rpx;
  padding: 16rpx 22rpx;
}

.user-text {
  font-size: 27rpx;
  color: #ffffff;
  line-height: 1.5;
}

// AI 消息
.ai-msg {
  width: 100%;
  box-sizing: border-box;
}

// Loading
.loading-state {
  padding: 8rpx 0;
}

.loader-track {
  height: 4rpx;
  width: 120rpx;
  background: rgba(13, 148, 136, 0.12);
  border-radius: 2rpx;
  overflow: hidden;
  margin-bottom: 10rpx;
}

.loader-fill {
  height: 100%;
  width: 40%;
  background: #0d9488;
  border-radius: 2rpx;
  animation: loader-slide 1.2s ease-in-out infinite;
}

@keyframes loader-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

.loader-label {
  font-size: 22rpx;
  color: #94a3b8;
}

// 结果元信息
.result-meta {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 14rpx;
}

.meta-source {
  font-size: 22rpx;
  color: #0d9488;
  background: rgba(13, 148, 136, 0.08);
  padding: 4rpx 14rpx;
  border-radius: 4rpx;
}

.meta-count {
  font-size: 22rpx;
  color: #94a3b8;
}

// 统计卡
.stat-row {
  display: flex;
  gap: 12rpx;
  margin-bottom: 16rpx;
}

.stat-block {
  flex: 1;
  background: #ffffff;
  border: 1px solid rgba(13, 148, 136, 0.1);
  border-radius: 6rpx;
  padding: 16rpx 10rpx;
  text-align: center;
  box-sizing: border-box;
}

.stat-num {
  display: block;
  font-size: 32rpx;
  font-weight: 700;
  color: #0d9488;
}

.stat-label {
  display: block;
  font-size: 20rpx;
  color: #64748b;
  margin-top: 4rpx;
}

// 表格
.table-wrap {
  margin-bottom: 14rpx;
  white-space: nowrap;
  background: #ffffff;
  border: 1px solid rgba(13, 148, 136, 0.1);
  border-radius: 6rpx;
  overflow: hidden;
}

.data-table {
  display: inline-block;
  min-width: 100%;
}

.dt-head {
  display: flex;
  background: #f1f9f8;
  border-bottom: 1px solid rgba(13, 148, 136, 0.08);
}

.dt-th {
  font-size: 21rpx;
  font-weight: 600;
  color: #475569;
  padding: 14rpx 16rpx;
  min-width: 100rpx;
  white-space: nowrap;
}

.dt-row {
  display: flex;
  border-bottom: 1px solid #f1f5f9;

  &:last-child {
    border-bottom: none;
  }
}

.dt-td {
  font-size: 23rpx;
  color: #475569;
  padding: 13rpx 16rpx;
  min-width: 100rpx;
  white-space: nowrap;

  &.td-first {
    color: #0f172a;
    font-weight: 500;
  }
}

// 结果文字
.result-text {
  display: block;
  font-size: 25rpx;
  color: #475569;
  line-height: 1.6;
  margin-bottom: 10rpx;
}

// SQL
.sql-section {
  margin-top: 8rpx;
}

.sql-toggle {
  font-size: 22rpx;
  color: #94a3b8;
  display: inline-block;
}

.sql-pre {
  margin-top: 10rpx;
  background: #1e293b;
  border-radius: 6rpx;
  padding: 16rpx 18rpx;
  overflow-x: auto;
}

.sql-code {
  font-size: 20rpx;
  color: #7dd3fc;
  font-family: Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

// 快捷标签
.quick-bar {
  flex-shrink: 0;
  white-space: nowrap;
  border-top: 1px solid rgba(13, 148, 136, 0.08);
  overflow: hidden;
}

.quick-inner {
  display: inline-flex;
  gap: 10rpx;
  padding: 14rpx 32rpx;
}

.qtag {
  flex-shrink: 0;
  background: #ffffff;
  border: 1px solid rgba(13, 148, 136, 0.15);
  border-radius: 6rpx;
  padding: 10rpx 18rpx;

  text {
    font-size: 23rpx;
    color: #0d9488;
    white-space: nowrap;
  }

  &:active {
    background: #ecfdf5;
  }
}

// 输入区
.input-area {
  flex-shrink: 0;
  padding: 14rpx 32rpx;
  padding-bottom: calc(14rpx + env(safe-area-inset-bottom));
  background: #ffffff;
  border-top: 1px solid rgba(13, 148, 136, 0.08);
}

.input-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.query-input {
  flex: 1;
  height: 72rpx;
  background: #f1f5f9;
  border-radius: 6rpx;
  padding: 0 20rpx;
  font-size: 27rpx;
  color: #1c1c1c;
  box-sizing: border-box;
}

.input-placeholder {
  color: #94a3b8;
}

.send-btn {
  flex-shrink: 0;
  height: 72rpx;
  padding: 0 28rpx;
  background: #e2e8f0;
  border-radius: 6rpx;
  display: flex;
  align-items: center;
  justify-content: center;

  &.ready {
    background: #0d9488;

    .send-text {
      color: #ffffff;
    }
  }
}

.send-text {
  font-size: 27rpx;
  font-weight: 500;
  color: #94a3b8;
}
</style>
