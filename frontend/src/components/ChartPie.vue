<template>
  <view class="chart-card">
    <view v-if="!dataset.length" class="empty">暂无玩法占比数据</view>
    <view v-else ref="chartRef" class="chart" />
  </view>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([PieChart, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  dataset: {
    type: Array,
    default: () => []
  }
})

const chartRef = ref(null)
const chartInstance = ref(null)

function initChart () {
  if (!chartRef.value) return
  chartInstance.value = echarts.init(chartRef.value)
  renderChart()
}

function renderChart () {
  if (!chartInstance.value) return
  chartInstance.value.setOption({
    tooltip: {
      trigger: 'item'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: '盈亏',
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        data: props.dataset
      }
    ]
  })
}

watch(() => props.dataset, () => {
  if (!chartInstance.value) return
  renderChart()
}, { deep: true })

onMounted(() => initChart())

onBeforeUnmount(() => {
  chartInstance.value?.dispose()
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.chart-card {
  @include card;
  min-height: 320rpx;
  padding: 20rpx;
}

.chart {
  width: 100%;
  height: 280rpx;
}

.empty {
  text-align: center;
  padding: 80rpx 0;
  color: #9ca3af;
  font-size: 26rpx;
}
</style>
