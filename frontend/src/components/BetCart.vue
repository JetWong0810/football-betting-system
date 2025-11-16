<template>
  <view v-if="betCart.hasSelections" class="bet-cart-wrapper">
    <!-- 浮动按钮 -->
    <view class="float-button" @tap="showCart = !showCart">
      <view class="badge" v-if="betCart.count > 0">{{ betCart.count }}</view>
      <text class="icon">🛒</text>
      <text class="label">投注车</text>
    </view>

    <!-- 底部弹窗 -->
    <view class="cart-modal" :class="{ show: showCart }">
      <view class="mask" @tap="showCart = false"></view>
      
      <view class="cart-content">
        <!-- 头部 -->
        <view class="cart-header">
          <view class="title">
            <text>投注车</text>
            <text class="count-badge">{{ betCart.count }}</text>
          </view>
          <button class="clear-btn" @tap="handleClear">清空</button>
        </view>

        <!-- 选项列表 -->
        <scroll-view class="selections-list" scroll-y>
          <view 
            v-for="item in betCart.selections" 
            :key="item.key" 
            class="selection-item"
          >
            <view class="item-row">
              <view class="item-info">
                <text class="teams">{{ item.homeTeam }} VS {{ item.awayTeam }}</text>
                <view class="details">
                  <text class="play">{{ item.playName }}<text v-if="item.handicap" class="handicap">({{ formatHandicap(item.handicap) }})</text></text>
                </view>
              </view>
              <text class="remove-btn" @tap="handleRemove(item.key)">×</text>
            </view>
            <view class="item-bet">
              <view class="selection">{{ item.selectionLabel }}</view>
              <text class="odds">@ {{ item.odds }}</text>
            </view>
          </view>
        </scroll-view>

        <!-- 串关选择 -->
        <view class="parlay-selector" v-if="betCart.isParlayMode">
          <view class="selector-label">过关方式</view>
          <scroll-view class="parlay-options" scroll-x>
            <view 
              v-for="option in parlayOptions" 
              :key="option.value"
              class="parlay-option"
              :class="{ active: betCart.parlayType === option.value }"
              @tap="() => betCart.setParlayType(option.value)"
            >
              {{ option.label }}
            </view>
          </scroll-view>
        </view>

        <!-- 投注信息条 -->
        <view class="mode-bar">
          <text class="mode-text">{{ betCart.parlayTypeLabel }}</text>
          <text class="mode-odds">{{ parlayDescription }}</text>
        </view>

        <!-- 投注信息 -->
        <view class="bet-summary">
          <!-- 金额和倍数 -->
          <view class="compact-row">
            <view class="amount-group">
              <text class="label">金额</text>
              <text class="value">{{ betCart.totalStake }}元</text>
              <text class="formula">{{ amountFormula }}</text>
            </view>
            <view class="divider"></view>
            <view class="multiple-group">
              <text class="label">倍数</text>
              <view class="stepper">
                <button class="btn" @tap="decreaseMultiple">-</button>
                <text class="num">{{ betCart.multiple }}</text>
                <button class="btn" @tap="increaseMultiple">+</button>
              </view>
            </view>
          </view>

          <!-- 预计奖金 -->
          <view class="winning-row">
            <text class="label">预计最高奖金</text>
            <text class="value">{{ betCart.maxWinning }}元</text>
          </view>
        </view>

        <!-- 底部按钮 -->
        <view class="cart-footer">
          <view v-if="betCart.cannotBetReason" class="error-tip">
            <text class="error-icon">⚠️</text>
            <text class="error-text">{{ betCart.cannotBetReason }}</text>
          </view>
          <view class="footer-buttons three-buttons">
            <button class="cancel-btn" @tap="showCart = false">取消</button>
            <button 
              class="save-btn" 
              :class="{ disabled: !betCart.canBet }"
              @tap="() => handleSaveWithStatus('saved')"
            >
              保存
            </button>
            <button 
              class="bet-btn" 
              :class="{ disabled: !betCart.canBet }"
              @tap="() => handleSaveWithStatus('betting')"
            >
              投注
            </button>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useBetCartStore } from '@/stores/betCartStore'
import { useBetStore } from '@/stores/betStore'

const betCart = useBetCartStore()
const betStore = useBetStore()

const showCart = ref(false)

// 串关选项
const parlayOptions = computed(() => {
  const count = betCart.count
  if (count < 2) return []
  
  const options = []
  for (let i = 2; i <= count; i++) {
    options.push({
      value: `${i}_1`,
      label: `${i}串1`
    })
  }
  return options
})

// 串关描述
const parlayDescription = computed(() => {
  if (betCart.isSingleMode) {
    return `赔率 ${formatOdds(betCart.totalOdds)}`
  }
  
  const [m] = betCart.parlayType.split('_')
  const parlayCount = betCart.parlayCount
  
  if (parlayCount > 1) {
    return `共${parlayCount}注 总赔率 ${formatOdds(betCart.totalOdds)}`
  }
  return `总赔率 ${formatOdds(betCart.totalOdds)}`
})

// 金额计算公式显示
const amountFormula = computed(() => {
  const count = betCart.parlayCount
  const multiple = betCart.multiple
  return `(${count}注 × ${multiple}倍 × 2元)`
})

// 增加倍数
function increaseMultiple() {
  if (betCart.multiple < 999) {
    betCart.multiple += 1
  }
}

// 减少倍数
function decreaseMultiple() {
  if (betCart.multiple > 1) {
    betCart.multiple -= 1
  }
}

function formatHandicap(value) {
  if (!value && value !== 0) return ''
  return value > 0 ? `+${value}` : value
}

function formatOdds(value) {
  if (!value) return '0.00'
  return Number(value).toFixed(2)
}

function handleClear() {
  uni.showModal({
    title: '确认清空',
    content: '确定要清空投注车吗？',
    success: (res) => {
      if (res.confirm) {
        betCart.clearCart()
        showCart.value = false
      }
    }
  })
}

function handleRemove(key) {
  betCart.removeSelection(key)
}

function handleSaveWithStatus(status) {
  if (!betCart.canBet) {
    uni.showToast({ title: betCart.cannotBetReason || '请完善投注信息', icon: 'none', duration: 2000 })
    return
  }

  const record = betCart.toBetRecord()
  if (!record) {
    uni.showToast({ title: '投注数据无效', icon: 'none' })
    return
  }

  // 添加状态
  record.status = status

  try {
    betStore.addBet(record)
    const successMsg = status === 'betting' ? '投注成功' : '保存成功'
    uni.showToast({ title: successMsg, icon: 'success' })
    betCart.clearCart()
    showCart.value = false
    
    // 延迟跳转到记录页面
    setTimeout(() => {
      uni.switchTab({ url: '/pages/record/record' })
    }, 1000)
  } catch (error) {
    uni.showToast({ title: error.message || '操作失败', icon: 'none' })
    console.error('保存投注失败:', error)
  }
}
</script>

<style lang="scss" scoped>
.bet-cart-wrapper {
  position: relative;
  z-index: 999;
}

/* 浮动按钮 */
.float-button {
  position: fixed;
  right: 28rpx;
  bottom: 110rpx;
  width: 110rpx;
  height: 110rpx;
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6rpx 20rpx rgba(13, 148, 136, 0.35);
  z-index: 1000;

  .badge {
    position: absolute;
    top: 6rpx;
    right: 6rpx;
    background: #ff7875;
    color: #fff;
    border-radius: 50%;
    width: 32rpx;
    height: 32rpx;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18rpx;
    font-weight: 600;
  }

  .icon {
    font-size: 44rpx;
    margin-bottom: 2rpx;
  }

  .label {
    font-size: 18rpx;
    color: #fff;
    font-weight: 500;
  }
}

/* 弹窗遮罩 */
.cart-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  display: none;

  &.show {
    display: block;
  }
}

.mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
}

/* 弹窗内容 */
.cart-content {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  max-height: 75vh;
  display: flex;
  flex-direction: column;
  animation: slideUp 0.3s ease;
  box-sizing: border-box;
  overflow: hidden;
}

@keyframes slideUp {
  from {
    transform: translateY(100%);
  }
  to {
    transform: translateY(0);
  }
}

/* 头部 */
.cart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 24rpx 16rpx;
  border-bottom: 1px solid #e5e7eb;

  .title {
    display: flex;
    align-items: center;
    gap: 8rpx;
    font-size: 28rpx;
    font-weight: 500;
    color: #111;
    flex: 1;
  }

  .count-badge {
    background: #0d9488;
    color: #fff;
    padding: 2rpx 10rpx;
    border-radius: 12rpx;
    font-size: 20rpx;
    font-weight: 500;
  }

  .clear-btn {
    padding: 0 20rpx;
    height: 48rpx;
    line-height: 48rpx;
    font-size: 24rpx;
    color: #999;
    background: transparent;
    border: 1px solid #e5e7eb;
    border-radius: 8rpx;
    margin-left: auto;

    &:active {
      color: #666;
      border-color: #d1d5db;
      background: #f9fafb;
    }
  }
}

/* 选项列表 */
.selections-list {
  flex: 1;
  max-height: 340rpx;
  overflow-y: auto;
  padding: 12rpx 24rpx;
  box-sizing: border-box;
}

.selection-item {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 12rpx;
  padding: 12rpx 16rpx;
  margin-bottom: 10rpx;
  box-sizing: border-box;
  width: 100%;

  &:last-child {
    margin-bottom: 0;
  }

  .item-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 8rpx;
    width: 100%;

    .item-info {
      flex: 1;
      min-width: 0;
      overflow: hidden;

      .teams {
        font-size: 26rpx;
        font-weight: 500;
        color: #111;
        display: block;
        margin-bottom: 6rpx;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .details {
        display: flex;
        align-items: center;
        gap: 8rpx;

        .play {
          font-size: 22rpx;
          color: #999;

          .handicap {
            color: #0d9488;
            font-weight: 500;
          }
        }
      }
    }

    .remove-btn {
      width: 36rpx;
      height: 36rpx;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 36rpx;
      color: #d1d5db;
      line-height: 1;
      margin-left: 8rpx;
      transition: color 0.2s;

      &:active {
        color: #999;
      }
    }
  }

  .item-bet {
    display: flex;
    align-items: center;
    gap: 10rpx;
    width: 100%;

    .selection {
      background: #0d9488;
      color: #fff;
      font-size: 22rpx;
      font-weight: 500;
      padding: 4rpx 12rpx;
      border-radius: 6rpx;
      white-space: nowrap;
    }

    .odds {
      font-size: 24rpx;
      color: #0d9488;
      font-weight: 600;
      white-space: nowrap;
    }
  }
}

/* 串关选择器 */
.parlay-selector {
  padding: 10rpx 20rpx;
  background: #f9fafb;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 12rpx;

  .selector-label {
    font-size: 22rpx;
    color: #666;
    flex-shrink: 0;
  }

  .parlay-options {
    flex: 1;
    display: flex;
    white-space: nowrap;
    overflow-x: auto;

    .parlay-option {
      display: inline-block;
      padding: 6rpx 16rpx;
      margin-right: 10rpx;
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 8rpx;
      font-size: 22rpx;
      color: #666;
      transition: all 0.2s;
      flex-shrink: 0;

      &.active {
        background: #0d9488;
        border-color: #0d9488;
        color: #fff;
        font-weight: 500;
      }

      &:last-child {
        margin-right: 0;
      }
    }
  }
}

/* 投注信息条 */
.mode-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10rpx 20rpx;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;

  .mode-text {
    font-size: 24rpx;
    font-weight: 500;
    color: #0d9488;
  }

  .mode-odds {
    font-size: 20rpx;
    color: #999;
    font-weight: 400;
  }
}

/* 投注信息 */
.bet-summary {
  padding: 12rpx 20rpx;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 12rpx;

  .compact-row {
    display: flex;
    align-items: center;
    padding: 10rpx 12rpx;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 10rpx;
    gap: 12rpx;

    .amount-group {
      flex: 1;
      display: flex;
      align-items: center;
      gap: 8rpx;

      .label {
        font-size: 22rpx;
        color: #666;
        font-weight: 400;
      }

      .value {
        font-size: 26rpx;
        font-weight: 600;
        color: #111;
      }

      .formula {
        font-size: 18rpx;
        color: #999;
        font-weight: 400;
      }
    }

    .divider {
      width: 1px;
      height: 32rpx;
      background: #e5e7eb;
    }

    .multiple-group {
      display: flex;
      align-items: center;
      gap: 8rpx;

      .label {
        font-size: 22rpx;
        color: #666;
        font-weight: 400;
      }

      .stepper {
        display: flex;
        align-items: center;
        background: #fff;
        border-radius: 8rpx;
        overflow: hidden;

        .btn {
          width: 48rpx;
          height: 48rpx;
          display: flex;
          align-items: center;
          justify-content: center;
          background: transparent;
          border: none;
          font-size: 26rpx;
          color: #0d9488;
          font-weight: 500;
          margin: 0;
          padding: 0;
          line-height: 1;

          &:active {
            background: rgba(13, 148, 136, 0.1);
          }
        }

        .num {
          min-width: 56rpx;
          text-align: center;
          font-size: 24rpx;
          font-weight: 500;
          color: #111;
        }
      }
    }
  }

  .winning-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10rpx 12rpx;
    background: rgba(13, 148, 136, 0.06);
    border: 1px solid rgba(13, 148, 136, 0.15);
    border-radius: 10rpx;

    .label {
      font-size: 22rpx;
      color: #666;
      font-weight: 400;
    }

    .value {
      font-size: 28rpx;
      font-weight: 600;
      color: #0d9488;
    }
  }
}

/* 底部按钮 */
.cart-footer {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  padding: 12rpx 20rpx;
  padding-bottom: calc(12rpx + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1px solid #e5e7eb;

  .error-tip {
    display: flex;
    align-items: center;
    gap: 8rpx;
    padding: 8rpx 12rpx;
    background: #fef3c7;
    border: 1px solid #fde68a;
    border-radius: 8rpx;

    .error-icon {
      font-size: 20rpx;
    }

    .error-text {
      flex: 1;
      font-size: 20rpx;
      color: #d97706;
      font-weight: 400;
    }
  }

  .footer-buttons {
    display: flex;
    gap: 12rpx;

    button {
      flex: 1;
      height: 72rpx;
      border-radius: 10rpx;
      font-size: 26rpx;
      font-weight: 500;
      border: none;
      transition: all 0.2s;
    }
    
    &.three-buttons {
      .cancel-btn {
        flex: 0.8;
      }
    }

    .cancel-btn {
      background: #f5f5f5;
      color: #666;

      &:active {
        background: #e5e5e5;
      }
    }

    .save-btn {
      background: #94a3b8;
      color: #fff;

      &:active {
        background: #64748b;
      }

      &.disabled {
        background: #d1d5db;
        color: #9ca3af;
      }
    }
    
    .bet-btn {
      background: #0d9488;
      color: #fff;
      box-shadow: 0 2rpx 8rpx rgba(13, 148, 136, 0.3);

      &:active {
        background: #0b8074;
      }

      &.disabled {
        background: #d1d5db;
        color: #9ca3af;
        box-shadow: none;
      }
    }
  }
}
</style>

