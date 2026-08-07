<template>
  <view v-if="data && data.isJapanLeague" class="jp-intel" :class="{ compact }">
    <view class="jp-head">
      <text class="jp-title">日本情报</text>
      <text v-if="data.lineupSource" class="jp-src">{{ data.lineupSource }}</text>
      <text class="jp-tag">参考</text>
    </view>

    <view v-if="weatherLine" class="jp-weather">
      <text class="jp-wx-lab">天气</text>
      <text class="jp-wx-val">{{ weatherLine }}</text>
      <text v-if="data.venue" class="jp-venue">{{ data.venue }}</text>
    </view>

    <view v-if="(data.attackNotes || []).length" class="jp-attack">
      <text class="jp-atk-lab">进攻点</text>
      <text
        v-for="(a, i) in data.attackNotes.slice(0, compact ? 3 : 6)"
        :key="i"
        class="jp-atk-chip"
      >{{ a.clubShort || sideLabel(a.side) }} {{ shortName(a.name) }} {{ a.goals }}球</text>
    </view>

    <view v-if="data.note && !(data.lineups || []).length" class="jp-note">
      <text>{{ data.note }}</text>
    </view>

    <view v-if="(data.lineups || []).length" class="jp-xi">
      <view
        v-for="lu in data.lineups"
        :key="lu.side"
        class="jp-xi-col"
      >
        <text class="jp-xi-club">{{ lu.clubShort || sideLabel(lu.side) }} 首发</text>
        <view
          v-for="(p, pi) in visiblePlayers(lu)"
          :key="pi"
          class="jp-pl"
        >
          <text class="jp-pos">{{ p.pos || '' }}</text>
          <text class="jp-num">{{ p.num || '' }}</text>
          <text class="jp-name">{{ shortName(p.name) }}</text>
          <text v-if="p.goals != null" class="jp-g">{{ p.goals }}球</text>
        </view>
        <text
          v-if="!expanded && (lu.players || []).length > 11"
          class="jp-more"
          @tap="$emit('toggle')"
        >更多</text>
      </view>
    </view>

    <view
      v-if="(data.lineups || []).length && hasBench"
      class="jp-toggle"
      @tap="expanded = !expanded"
    >
      <text>{{ expanded ? '收起替补' : '展开替补' }}</text>
    </view>

    <view v-if="expanded" class="jp-xi bench">
      <view
        v-for="lu in data.lineups"
        :key="'b-' + lu.side"
        class="jp-xi-col"
      >
        <text class="jp-xi-club">{{ lu.clubShort || sideLabel(lu.side) }} 替补</text>
        <view
          v-for="(p, pi) in (lu.bench || [])"
          :key="pi"
          class="jp-pl"
        >
          <text class="jp-pos">{{ p.pos || '' }}</text>
          <text class="jp-num">{{ p.num || '' }}</text>
          <text class="jp-name">{{ shortName(p.name) }}</text>
          <text v-if="p.goals != null" class="jp-g">{{ p.goals }}球</text>
        </view>
        <text v-if="!(lu.bench || []).length" class="jp-empty">-</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
  compact: { type: Boolean, default: false },
})

defineEmits(['toggle'])

const expanded = ref(false)

const weatherLine = computed(() => {
  const w = props.data?.weather
  if (!w) return ''
  const parts = []
  if (w.weatherText) parts.push(w.weatherText)
  if (w.tempC != null) parts.push(`${w.tempC}°C`)
  if (w.precipProb != null) parts.push(`降水${w.precipProb}%`)
  if (w.windMs != null) parts.push(`风${w.windMs}m/s`)
  if (w.humidity != null) parts.push(`湿${w.humidity}%`)
  return parts.join(' · ')
})

const hasBench = computed(() =>
  (props.data?.lineups || []).some((lu) => (lu.bench || []).length > 0)
)

function sideLabel(side) {
  return side === 'home' ? '主' : side === 'away' ? '客' : side
}

function shortName(name) {
  if (!name) return '-'
  const s = String(name).replace(/\s+/g, ' ').trim()
  // 中文译名略长于片假名，放宽截断
  return s.length > 12 ? s.slice(0, 12) + '…' : s
}

function visiblePlayers(lu) {
  const list = lu.players || []
  if (props.compact) return list.slice(0, 6)
  return list
}
</script>

<style lang="scss" scoped>
.jp-intel {
  margin: 16rpx 24rpx;
  padding: 16rpx 18rpx;
  background: #f8fafb;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
}
.jp-intel.compact {
  margin: 8rpx 0 0;
  padding: 12rpx 14rpx;
}
.jp-head {
  display: flex;
  align-items: center;
  gap: 10rpx;
  margin-bottom: 10rpx;
}
.jp-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #0f766e;
}
.jp-src {
  font-size: 20rpx;
  color: #64748b;
}
.jp-tag {
  margin-left: auto;
  font-size: 18rpx;
  color: #0f766e;
  background: #ccfbf1;
  border-radius: 6rpx;
  padding: 2rpx 8rpx;
}
.jp-weather {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8rpx 12rpx;
  margin-bottom: 10rpx;
  font-size: 22rpx;
}
.jp-wx-lab, .jp-atk-lab {
  color: #64748b;
}
.jp-wx-val { color: #1e293b; }
.jp-venue { color: #94a3b8; font-size: 20rpx; }
.jp-attack {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8rpx;
  margin-bottom: 10rpx;
}
.jp-atk-chip {
  font-size: 20rpx;
  color: #9a3412;
  background: #fff7ed;
  border: 1rpx solid #fed7aa;
  border-radius: 6rpx;
  padding: 2rpx 8rpx;
}
.jp-note {
  font-size: 22rpx;
  color: #64748b;
  padding: 6rpx 0;
}
.jp-xi {
  display: flex;
  gap: 12rpx;
}
.jp-xi-col {
  flex: 1;
  min-width: 0;
  background: #fff;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
  padding: 10rpx;
}
.jp-xi-club {
  display: block;
  font-size: 20rpx;
  font-weight: 600;
  color: #334155;
  margin-bottom: 6rpx;
}
.jp-pl {
  display: flex;
  align-items: baseline;
  gap: 6rpx;
  font-size: 20rpx;
  line-height: 1.45;
  font-variant-numeric: tabular-nums;
}
.jp-pos { color: #94a3b8; width: 28rpx; flex-shrink: 0; }
.jp-num { color: #64748b; width: 28rpx; flex-shrink: 0; }
.jp-name { color: #1e293b; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jp-g { color: #c2410c; flex-shrink: 0; }
.jp-toggle {
  margin-top: 10rpx;
  text-align: center;
  font-size: 22rpx;
  color: #0f766e;
  padding: 6rpx;
}
.jp-empty { font-size: 20rpx; color: #94a3b8; }
.jp-xi.bench { margin-top: 8rpx; }
</style>
