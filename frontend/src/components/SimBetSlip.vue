<template>
  <view class="sim-slip-root" v-if="store.hasLegs || showPanel">
    <!-- 底栏 -->
    <view v-if="store.hasLegs" class="slip-bar" @tap="showPanel = true">
      <view class="bar-left">
        <text class="bar-count">已选 {{ store.count }}</text>
        <text class="bar-parlay">{{ store.parlayLabel }}</text>
      </view>
      <view class="bar-mid">
        <text class="bar-lab">安全分 {{ store.combinedSafety ?? '-' }}</text>
        <text class="bar-score">建议 ¥{{ advisedAmount }}</text>
      </view>
      <text class="bar-act">查看</text>
    </view>

    <!-- 串关单面板 -->
    <view v-if="showPanel" class="slip-layer">
      <view class="slip-mask" @tap="showPanel = false"></view>
      <view class="slip-panel" :class="{ show: showPanel }">
        <view class="panel-hd">
          <text class="panel-title">模拟串关单</text>
          <text class="panel-clear" @tap="onClear">清空</text>
        </view>

        <scroll-view class="panel-list" scroll-y>
          <view v-for="leg in store.legs" :key="leg.matchId" class="leg-card">
            <view class="leg-top">
              <text class="leg-pick">{{ leg.pickLabel }}</text>
              <text class="leg-score">{{ leg.safetyScore }}</text>
            </view>
            <text class="leg-teams">{{ leg.homeTeam }} vs {{ leg.awayTeam }}</text>
            <view class="leg-meta">
              <text class="leg-league">{{ leg.league || '-' }}</text>
              <text class="leg-src">{{ srcLabel(leg) }}</text>
              <text class="leg-del" @tap="store.removeLeg(leg.matchId)">删除</text>
            </view>
            <text v-if="offsetHint(leg)" class="leg-hint">{{ offsetHint(leg) }}</text>
          </view>
        </scroll-view>

        <view class="panel-sum" v-if="store.hasLegs">
          <text class="sum-parlay">{{ store.parlayLabel }}</text>
          <text class="sum-score">安全分 {{ store.combinedSafety }}</text>
          <text v-if="store.weakLeg && store.count > 1" class="sum-weak">
            最弱 {{ store.weakLeg.homeTeam }} {{ store.weakLeg.safetyScore }}
          </text>
        </view>

        <!-- 推荐金额: 安全分→建议档, 金额=有效资金×信心档比例; 不进真单 -->
        <view class="panel-stake" v-if="store.hasLegs">
          <view class="stake-hd">
            <text class="stake-title">推荐投注金额</text>
            <text class="stake-bank">有效资金 ¥{{ fmtMoney(betStore.effectiveBankroll) }}</text>
          </view>
          <text class="stake-reason">{{ tierAdvice.reason }}</text>
          <view class="tier-row">
            <view
              v-for="t in tierOptions"
              :key="t.key"
              class="tier-pill"
              :class="{ active: selectedTier === t.key, advised: tierAdvice.tier === t.key }"
              @tap="selectedTier = t.key"
            >
              <text class="tier-lab">{{ t.label }}</text>
              <text class="tier-amt">¥{{ tieredStakes[t.key].amount }}</text>
            </view>
          </view>
          <text class="stake-note">仅建议,不写入投注记录 · 可点选改档</text>
        </view>

        <view class="panel-actions">
          <text class="btn-ghost" @tap="showPanel = false">继续选</text>
          <text class="btn-main" @tap="onConfirm">保存评估</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useSimBetStore } from '@/stores/simBetStore'
import { useBetStore } from '@/stores/betStore'
import { useConfigStore } from '@/stores/configStore'
import { legOffsetHint, suggestTierFromSafety } from '@/utils/simBet'
import { calcTieredStakes } from '@/utils/strategyEngine'

const store = useSimBetStore()
const betStore = useBetStore()
const configStore = useConfigStore()
const showPanel = ref(false)
const selectedTier = ref('mid')

const tierOptions = [
  { key: 'low', label: '低' },
  { key: 'mid', label: '中' },
  { key: 'high', label: '高' },
]

const customConfig = computed(() => ({
  fixedRatio: configStore.fixedRatio,
  kellyFactor: configStore.kellyFactor,
  stopLossLimit: configStore.stopLossLimit,
  maxDrawdown: configStore.maxDrawdown,
  minConfidence: configStore.minConfidence,
}))

const tieredStakes = computed(() =>
  calcTieredStakes({
    effectiveBankroll: betStore.effectiveBankroll,
    riskLevel: configStore.riskTolerance,
    customConfig: customConfig.value,
  })
)

const tierAdvice = computed(() =>
  suggestTierFromSafety({
    combinedSafety: store.combinedSafety,
    legs: store.legs,
  })
)

const advisedAmount = computed(() => {
  const t = selectedTier.value || tierAdvice.value.tier
  return tieredStakes.value[t]?.amount ?? 0
})

watch(
  () => [store.combinedSafety, store.count, tierAdvice.value.tier],
  () => {
    selectedTier.value = tierAdvice.value.tier
  },
  { immediate: true }
)

function srcLabel(leg) {
  if (leg.scoreSource === 'history') return `同赔${leg.sample || 0}场`
  if (leg.scoreSource === 'heuristic') return '启发式'
  return ''
}

function offsetHint(leg) {
  return legOffsetHint(leg)
}

function fmtMoney(n) {
  const v = Math.round(Number(n) || 0)
  return v.toLocaleString('zh-CN')
}

function onClear() {
  store.clearLegs()
  showPanel.value = false
}

function onConfirm() {
  const slip = store.confirmSlip({
    suggestedTier: selectedTier.value,
    suggestedStake: advisedAmount.value,
    tierReason: tierAdvice.value.reason,
  })
  showPanel.value = false
  if (slip) {
    uni.showToast({
      title: `已保存 · 建议¥${advisedAmount.value}`,
      icon: 'none',
    })
  }
}

defineExpose({ open: () => { showPanel.value = true } })
</script>

<style lang="scss" scoped>
.sim-slip-root { position: relative; z-index: 250; }
.slip-bar {
  position: fixed; left: 24rpx; right: 24rpx; bottom: calc(24rpx + env(safe-area-inset-bottom));
  background: #0f172a; color: #fff;
  border-radius: 6rpx;
  padding: 20rpx 24rpx;
  display: flex; align-items: center; gap: 16rpx;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.25);
  .bar-left { display: flex; flex-direction: column; gap: 2rpx; }
  .bar-count { font-size: 26rpx; font-weight: 600; }
  .bar-parlay { font-size: 20rpx; color: #94a3b8; }
  .bar-mid { flex: 1; text-align: center; }
  .bar-lab { font-size: 20rpx; color: #94a3b8; display: block; }
  .bar-score { font-size: 32rpx; font-weight: 700; font-variant-numeric: tabular-nums; }
  .bar-act { font-size: 24rpx; color: #5eead4; }
}
.slip-layer { position: fixed; inset: 0; z-index: 260; }
.slip-mask { position: absolute; inset: 0; background: rgba(15, 23, 42, 0.45); }
.slip-panel {
  position: absolute; left: 0; right: 0; bottom: 0;
  max-height: 78vh;
  background: #fff;
  border-radius: 12rpx 12rpx 0 0;
  display: flex; flex-direction: column;
  padding-bottom: env(safe-area-inset-bottom);
}
.panel-hd {
  display: flex; justify-content: space-between; align-items: center;
  padding: 28rpx 36rpx 16rpx;
  .panel-title { font-size: 30rpx; font-weight: 600; color: #0f172a; }
  .panel-clear { font-size: 24rpx; color: #94a3b8; padding: 8rpx 4rpx 8rpx 16rpx; }
}
.panel-list { max-height: 32vh; padding: 8rpx 28rpx; box-sizing: border-box; }
.leg-card {
  background: #f8fafc; border-radius: 6rpx; padding: 20rpx 24rpx; margin-bottom: 12rpx;
  box-sizing: border-box;
  .leg-top { display: flex; justify-content: space-between; align-items: baseline; gap: 16rpx; }
  .leg-pick { font-size: 28rpx; font-weight: 600; color: #0f172a; flex: 1; min-width: 0; }
  .leg-score {
    font-size: 32rpx; font-weight: 700; color: #0d9488;
    font-variant-numeric: tabular-nums; flex-shrink: 0; padding-right: 4rpx;
  }
  .leg-teams { font-size: 22rpx; color: #64748b; margin-top: 6rpx; display: block; }
  .leg-meta {
    display: flex; align-items: center; gap: 12rpx; margin-top: 8rpx;
    .leg-league, .leg-src { font-size: 20rpx; color: #94a3b8; }
    .leg-del {
      margin-left: auto; font-size: 22rpx; color: #dc2626;
      padding: 4rpx 4rpx 4rpx 12rpx; flex-shrink: 0;
    }
  }
  .leg-hint {
    display: block; margin-top: 8rpx;
    font-size: 20rpx; color: #64748b;
  }
}
.panel-sum {
  padding: 16rpx 36rpx 8rpx;
  border-top: 1rpx solid #e2e8f0;
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 12rpx;
  .sum-parlay { font-size: 26rpx; font-weight: 600; color: #0f172a; }
  .sum-score { font-size: 26rpx; color: #0d9488; font-weight: 600; }
  .sum-weak { font-size: 20rpx; color: #94a3b8; width: 100%; }
}
.panel-stake {
  padding: 12rpx 36rpx 8rpx;
  .stake-hd {
    display: flex; justify-content: space-between; align-items: baseline; gap: 12rpx;
  }
  .stake-title { font-size: 26rpx; font-weight: 600; color: #0f172a; }
  .stake-bank { font-size: 20rpx; color: #94a3b8; }
  .stake-reason {
    display: block; margin-top: 8rpx;
    font-size: 22rpx; color: #64748b; line-height: 1.4;
  }
  .tier-row {
    display: flex; gap: 12rpx; margin-top: 14rpx;
  }
  .tier-pill {
    flex: 1;
    text-align: center;
    padding: 14rpx 8rpx;
    border-radius: 6rpx;
    border: 2rpx solid #e2e8f0;
    background: #f8fafc;
    &.advised { border-color: rgba(#0d9488, 0.35); }
    &.active {
      border-color: #0d9488;
      background: #f0fdfa;
    }
    .tier-lab { display: block; font-size: 20rpx; color: #64748b; }
    .tier-amt {
      display: block; margin-top: 4rpx;
      font-size: 28rpx; font-weight: 700; color: #0f172a;
      font-variant-numeric: tabular-nums;
    }
    &.active .tier-amt { color: #0d9488; }
  }
  .stake-note {
    display: block; margin-top: 10rpx;
    font-size: 20rpx; color: #94a3b8;
  }
}
.panel-actions {
  display: flex; gap: 16rpx; padding: 16rpx 36rpx 28rpx;
  .btn-ghost, .btn-main {
    flex: 1; text-align: center; padding: 20rpx 0;
    border-radius: 6rpx; font-size: 28rpx;
  }
  .btn-ghost { background: #f1f5f9; color: #475569; }
  .btn-main { background: #0d9488; color: #fff; font-weight: 600; }
}
</style>
