<template>
  <view class="ocr-upload-page">
    <view class="container">
      <!-- 上传区域 -->
      <view class="upload-section">
        <view v-if="!imageBase64" class="upload-box" @click="chooseImage">
          <view class="upload-icon">📷</view>
          <text class="upload-text">点击上传投注图片</text>
          <text class="upload-hint">支持 JPG/PNG 格式</text>
        </view>
        
        <view v-else class="preview-box">
          <image :src="imagePreview" mode="aspectFit" class="preview-image" />
          <view class="preview-actions">
            <button class="action-btn reselect" @click="chooseImage" size="mini">重新选择</button>
            <button class="action-btn recognize" @click="recognizeImage" :loading="recognizing" :disabled="recognizing" size="mini" type="primary">
              {{ recognizing ? '识别中...' : '开始识别' }}
            </button>
          </view>
        </view>
      </view>

      <!-- 识别结果 -->
      <view v-if="ocrResult" class="result-section">
        <view class="section-title">识别结果</view>
        
        <!-- 识别状态 -->
        <view v-if="!ocrResult.success" class="error-box">
          <text class="error-icon">⚠️</text>
          <text class="error-text">{{ ocrResult.error || '识别失败' }}</text>
        </view>
        
        <!-- 识别成功 -->
        <view v-else class="success-box">
          <!-- 原始文本 -->
          <view class="raw-text-box">
            <text class="label">识别文本：</text>
            <text class="raw-text">{{ ocrResult.raw_text }}</text>
            <text class="confidence">置信度: {{ (ocrResult.ocr_confidence * 100).toFixed(1) }}%</text>
          </view>
          
          <!-- 解析的投注信息 -->
          <view v-if="ocrResult.data && ocrResult.data.legs && ocrResult.data.legs.length > 0" class="bet-info-box">
            <text class="label">解析的投注信息：</text>
            
            <view v-for="(leg, index) in ocrResult.data.legs" :key="index" class="bet-leg">
              <view class="leg-header">第 {{ index + 1 }} 场</view>
              <view class="leg-row">
                <text class="leg-label">联赛：</text>
                <text class="leg-value">{{ leg.league || '未识别' }}</text>
              </view>
              <view class="leg-row">
                <text class="leg-label">对阵：</text>
                <text class="leg-value">{{ leg.homeTeam }} vs {{ leg.awayTeam }}</text>
              </view>
              <view class="leg-row">
                <text class="leg-label">日期：</text>
                <text class="leg-value">{{ leg.matchDate }}</text>
              </view>
              <view class="leg-row">
                <text class="leg-label">投注类型：</text>
                <text class="leg-value">{{ leg.betType }}</text>
              </view>
              <view class="leg-row">
                <text class="leg-label">选项：</text>
                <text class="leg-value">{{ leg.selection || '未识别' }}</text>
              </view>
              <view class="leg-row">
                <text class="leg-label">赔率：</text>
                <text class="leg-value">{{ leg.odds || '未识别' }}</text>
              </view>
            </view>
            
            <view class="bet-stake">
              <text class="stake-label">投注金额：</text>
              <text class="stake-value">{{ ocrResult.data.stake || 0 }} 元</text>
            </view>
            
            <view v-if="ocrResult.data.parlayType" class="bet-parlay">
              <text class="parlay-label">串关方式：</text>
              <text class="parlay-value">{{ ocrResult.data.parlayType }}</text>
            </view>
            
            <text class="parse-confidence">解析置信度: {{ (ocrResult.data.confidence * 100).toFixed(1) }}%</text>
          </view>
          
          <!-- 保存按钮 -->
          <button 
            v-if="ocrResult.data && ocrResult.data.legs && ocrResult.data.legs.length > 0" 
            class="save-btn" 
            @click="saveBet" 
            :loading="saving" 
            :disabled="saving"
            type="primary"
          >
            {{ saving ? '保存中...' : '保存为投注记录' }}
          </button>
        </view>
      </view>

      <!-- 使用说明 -->
      <view class="tips-section">
        <view class="section-title">使用说明</view>
        <view class="tip-item">1. 请上传清晰的投注截图</view>
        <view class="tip-item">2. 确保图片中包含：球队、联赛、赔率等信息</view>
        <view class="tip-item">3. 支持识别：胜平负、让球、大小球等玩法</view>
        <view class="tip-item">4. 识别后可手动调整，再保存为投注记录</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { request } from '@/utils/http'
import { useBetStore } from '@/stores/betStore'

const betStore = useBetStore()

const imageBase64 = ref('')
const imagePreview = ref('')
const recognizing = ref(false)
const saving = ref(false)
const ocrResult = ref(null)

// 选择图片
const chooseImage = () => {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'],
    success: (res) => {
      const tempFilePath = res.tempFilePaths[0]
      imagePreview.value = tempFilePath
      
      // #ifdef H5
      // H5环境：使用 fetch + FileReader 读取 base64
      fetch(tempFilePath)
        .then(response => response.blob())
        .then(blob => {
          const reader = new FileReader()
          reader.onload = (e) => {
            // 获取 base64 字符串（移除 data:image/...;base64, 前缀）
            const base64 = e.target.result.split(',')[1]
            imageBase64.value = base64
            ocrResult.value = null
          }
          reader.onerror = (err) => {
            console.error('读取图片失败:', err)
            uni.showToast({
              title: '读取图片失败',
              icon: 'none'
            })
          }
          reader.readAsDataURL(blob)
        })
        .catch(err => {
          console.error('读取图片失败:', err)
          uni.showToast({
            title: '读取图片失败',
            icon: 'none'
          })
        })
      // #endif
      
      // #ifndef H5
      // 小程序环境：使用 FileSystemManager
      uni.getFileSystemManager().readFile({
        filePath: tempFilePath,
        encoding: 'base64',
        success: (readRes) => {
          imageBase64.value = readRes.data
          ocrResult.value = null // 清空之前的识别结果
        },
        fail: (err) => {
          console.error('读取图片失败:', err)
          uni.showToast({
            title: '读取图片失败',
            icon: 'none'
          })
        }
      })
      // #endif
    },
    fail: (err) => {
      console.error('选择图片失败:', err)
    }
  })
}

// 识别图片
const recognizeImage = async () => {
  if (!imageBase64.value) {
    uni.showToast({
      title: '请先选择图片',
      icon: 'none'
    })
    return
  }
  
  recognizing.value = true
  
  try {
    const result = await request({
      url: '/api/ocr/parse-bet-image',
      method: 'POST',
      timeout: 60000, // 60秒超时（OCR 首次初始化需要较长时间）
      data: {
        image_base64: imageBase64.value
      }
    })
    
    ocrResult.value = result
    
    if (!result.success) {
      uni.showToast({
        title: result.error || '识别失败',
        icon: 'none',
        duration: 3000
      })
    } else {
      uni.showToast({
        title: '识别成功',
        icon: 'success'
      })
    }
  } catch (error) {
    console.error('OCR识别失败:', error)
    uni.showToast({
      title: error.message || '识别失败',
      icon: 'none',
      duration: 3000
    })
    
    ocrResult.value = {
      success: false,
      error: error.message || '识别失败，请重试'
    }
  } finally {
    recognizing.value = false
  }
}

// 保存为投注记录
const saveBet = async () => {
  if (!ocrResult.value || !ocrResult.value.data) {
    return
  }
  
  saving.value = true
  
  try {
    const betData = ocrResult.value.data
    
    // 构造投注记录数据
    const betRecord = {
      bet_data: {
        legs: betData.legs,
        parlayType: betData.parlayType || '1_1'
      },
      stake: betData.stake || 0,
      odds: betData.legs.reduce((acc, leg) => acc * (leg.odds || 1), 1), // 计算总赔率
      status: 'saved',
      bet_time: new Date().toISOString(),
      result: null,
      profit: null
    }
    
    await request({
      url: '/api/bets',
      method: 'POST',
      data: betRecord
    })
    
    uni.showToast({
      title: '保存成功',
      icon: 'success'
    })
    
    // 刷新投注记录列表
    await betStore.fetchBets()
    
    // 延迟返回上一页
    setTimeout(() => {
      uni.navigateBack()
    }, 1500)
    
  } catch (error) {
    console.error('保存失败:', error)
    uni.showToast({
      title: error.message || '保存失败',
      icon: 'none'
    })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ocr-upload-page {
  min-height: 100vh;
  background-color: #f5f5f5;
}

.container {
  padding: 20rpx;
}

/* 上传区域 */
.upload-section {
  margin-bottom: 30rpx;
}

.upload-box {
  background: white;
  border-radius: 16rpx;
  padding: 80rpx 40rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2rpx dashed #d1d5db;
}

.upload-icon {
  font-size: 80rpx;
  margin-bottom: 20rpx;
}

.upload-text {
  font-size: 32rpx;
  color: #374151;
  margin-bottom: 10rpx;
}

.upload-hint {
  font-size: 24rpx;
  color: #9ca3af;
}

.preview-box {
  background: white;
  border-radius: 16rpx;
  padding: 20rpx;
  overflow: hidden;
}

.preview-image {
  width: 100%;
  min-height: 400rpx;
  max-height: 800rpx;
  border-radius: 12rpx;
  margin-bottom: 20rpx;
}

.preview-actions {
  display: flex;
  gap: 20rpx;
}

.action-btn {
  flex: 1;
}

.reselect {
  background-color: #f3f4f6;
  color: #374151;
}

.recognize {
  background-color: #0d9488;
}

/* 识别结果 */
.result-section {
  background: white;
  border-radius: 16rpx;
  padding: 30rpx;
  margin-bottom: 30rpx;
}

.section-title {
  font-size: 32rpx;
  font-weight: bold;
  color: #111827;
  margin-bottom: 20rpx;
}

.error-box {
  display: flex;
  align-items: center;
  padding: 20rpx;
  background-color: #fef2f2;
  border-radius: 12rpx;
  border: 2rpx solid #fecaca;
}

.error-icon {
  font-size: 40rpx;
  margin-right: 15rpx;
}

.error-text {
  flex: 1;
  font-size: 28rpx;
  color: #dc2626;
}

.success-box {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.raw-text-box {
  padding: 20rpx;
  background-color: #f9fafb;
  border-radius: 12rpx;
  border: 2rpx solid #e5e7eb;
}

.label {
  display: block;
  font-size: 26rpx;
  color: #6b7280;
  margin-bottom: 10rpx;
}

.raw-text {
  display: block;
  font-size: 28rpx;
  color: #111827;
  line-height: 1.6;
  margin-bottom: 10rpx;
}

.confidence,
.parse-confidence {
  display: block;
  font-size: 24rpx;
  color: #0d9488;
  text-align: right;
}

.bet-info-box {
  padding: 20rpx;
  background-color: #ecfdf5;
  border-radius: 12rpx;
  border: 2rpx solid #a7f3d0;
}

.bet-leg {
  padding: 15rpx;
  background: white;
  border-radius: 8rpx;
  margin-bottom: 15rpx;
}

.leg-header {
  font-size: 26rpx;
  font-weight: bold;
  color: #0d9488;
  margin-bottom: 10rpx;
  padding-bottom: 10rpx;
  border-bottom: 2rpx solid #e5e7eb;
}

.leg-row {
  display: flex;
  align-items: center;
  margin-bottom: 8rpx;
}

.leg-label {
  font-size: 26rpx;
  color: #6b7280;
  width: 140rpx;
  flex-shrink: 0;
}

.leg-value {
  flex: 1;
  font-size: 26rpx;
  color: #111827;
}

.bet-stake,
.bet-parlay {
  display: flex;
  align-items: center;
  padding: 15rpx;
  background: white;
  border-radius: 8rpx;
  margin-bottom: 10rpx;
}

.stake-label,
.parlay-label {
  font-size: 28rpx;
  color: #6b7280;
  width: 140rpx;
}

.stake-value {
  flex: 1;
  font-size: 32rpx;
  font-weight: bold;
  color: #dc2626;
}

.parlay-value {
  flex: 1;
  font-size: 28rpx;
  color: #0d9488;
}

.save-btn {
  margin-top: 20rpx;
  background-color: #0d9488;
  color: white;
  border-radius: 12rpx;
}

/* 使用说明 */
.tips-section {
  background: white;
  border-radius: 16rpx;
  padding: 30rpx;
}

.tip-item {
  font-size: 26rpx;
  color: #6b7280;
  line-height: 1.8;
  margin-bottom: 10rpx;
}
</style>
