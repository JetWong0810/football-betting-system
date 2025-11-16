<template>
  <scroll-view class="page" scroll-y>
    <view class="section">
      <text class="section-title">盈亏趋势</text>
      <ChartProfit :series="statStore.trendSeries" />
    </view>

    <view class="section">
      <text class="section-title">玩法盈亏占比</text>
      <ChartPie :dataset="statStore.pieDataset" />
    </view>

    <view class="section">
      <text class="section-title">周度盈亏</text>
      <view v-if="!weekList.length" class="empty">暂无数据</view>
      <view v-else class="weekly">
        <view v-for="row in weekList" :key="row.week" class="weekly-row">
          <view class="week">{{ row.week }}</view>
          <view class="meta">投入 {{ formatCurrency(row.stake) }}</view>
          <view class="meta" :class="{ win: row.profit >= 0, lose: row.profit < 0 }">
            盈亏 {{ formatCurrency(row.profit) }}
          </view>
        </view>
      </view>
    </view>
  </scroll-view>
</template>

<script setup>
import { computed } from 'vue'
import ChartPie from '@/components/ChartPie.vue'
import ChartProfit from '@/components/ChartProfit.vue'
import { useStatStore } from '@/stores/statStore'
import { formatCurrency } from '@/utils/formatters'

const statStore = useStatStore()

const weekList = computed(() => {
  return Object.entries(statStore.periodStats)
    .map(([week, payload]) => ({ week, ...payload }))
    .sort((a, b) => a.week.localeCompare(b.week))
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.page {
  padding: 24rpx;
  box-sizing: border-box;
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f8f5 0%, #f2fbf9 100%);
}

.section {
  margin-bottom: 32rpx;
}

.section-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #0d9488;
  margin-bottom: 16rpx;
}

.weekly {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.weekly-row {
  @include card;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16rpx 20rpx;
}

.week {
  font-size: 26rpx;
  font-weight: 600;
  color: #111827;
}

.meta {
  font-size: 24rpx;
  color: #6b7280;
}

.meta.win { 
  color: $frbt-positive;
  font-weight: 500;
}

.meta.lose { 
  color: $frbt-negative;
  font-weight: 500;
}

.empty {
  text-align: center;
  padding: 60rpx 0;
  color: #9ca3af;
  font-size: 26rpx;
}
</style>
