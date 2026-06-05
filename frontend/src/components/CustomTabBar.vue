<template>
  <view class="custom-tabbar">
    <view
      class="tab-item"
      v-for="(tab, idx) in tabs"
      :key="tab.path"
      :class="{ active: current === tab.id, center: tab.isCenter }"
      @tap="switchTab(tab)"
    >
      <view v-if="tab.isCenter" class="center-btn">
        <image class="center-icon" :src="current === tab.id ? tab.activeIcon : tab.icon" mode="aspectFit" />
      </view>
      <template v-else>
        <image class="tab-icon" :src="current === tab.id ? tab.activeIcon : tab.icon" mode="aspectFit" />
      </template>
      <text class="tab-text" :class="{ 'center-text': tab.isCenter }">{{ tab.text }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const tabs = [
  { id: 'home', path: '/pages/home/home', icon: '/static/tabbar/home.png', activeIcon: '/static/tabbar/home-active.png', text: '首页' },
  { id: 'matches', path: '/pages/matches/list', icon: '/static/tabbar/matches.png', activeIcon: '/static/tabbar/matches-active.png', text: '赛事' },
  { id: 'predict', path: '/pages/predict/predict', icon: '/static/tabbar/predict.png', activeIcon: '/static/tabbar/predict-active.png', text: '预测', isCenter: true },
  { id: 'record', path: '/pages/record/record', icon: '/static/tabbar/strategy.png', activeIcon: '/static/tabbar/strategy-active.png', text: '记录' },
  { id: 'profile', path: '/pages/profile/profile', icon: '/static/tabbar/settings.png', activeIcon: '/static/tabbar/settings-active.png', text: '我的' },
]

const current = ref('home')

function switchTab(tab) {
  current.value = tab.id
  uni.switchTab({ url: tab.path })
}

function onTabActive(id) {
  current.value = id
}

onMounted(() => {
  uni.$on('tab-active', onTabActive)
})

onUnmounted(() => {
  uni.$off('tab-active', onTabActive)
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.custom-tabbar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(100rpx + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: #fff;
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  box-shadow: 0 -2rpx 12rpx rgba(0, 0, 0, 0.06);
  z-index: 999;
}

.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100rpx;
  position: relative;

  .tab-icon {
    width: 44rpx;
    height: 44rpx;
    margin-bottom: 4rpx;
  }

  .tab-text {
    font-size: 20rpx;
    color: #9ca3af;
  }

  &.active .tab-text {
    color: $frbt-primary;
  }

  &.center {
    justify-content: flex-start;
    margin-top: -30rpx;
  }
}

.center-btn {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, $frbt-primary 0%, $frbt-secondary 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8rpx 20rpx rgba(13, 148, 136, 0.4);
  margin-bottom: 4rpx;

  .center-icon {
    width: 48rpx;
    height: 48rpx;
    filter: brightness(10);
  }
}

.center-text {
  color: $frbt-primary !important;
  font-weight: 600;
}
</style>
