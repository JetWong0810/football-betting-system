<template>
  <view class="chart-card">
    <view v-if="!dataset.length" class="empty">暂无玩法占比数据</view>
    <view v-else ref="chartRef" class="chart" />
  </view>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
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
  try {
  if (!chartRef.value) return
    if (!props.dataset.length) return
    
  chartInstance.value = echarts.init(chartRef.value)
  renderChart()
  } catch (error) {
    console.warn('Chart init error:', error)
  }
}

function renderChart () {
  try {
  if (!chartInstance.value) return
    if (!props.dataset.length) return
    
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
  } catch (error) {
    console.warn('Chart render error:', error)
  }
}

watch(() => props.dataset, () => {
  nextTick(() => {
    if (!chartInstance.value && props.dataset.length) {
      initChart()
    } else if (chartInstance.value) {
  renderChart()
    }
  })
}, { deep: true })

onMounted(() => {
  nextTick(() => {
    if (props.dataset.length) {
      initChart()
    }
  })
})

onBeforeUnmount(() => {
  if (chartInstance.value) {
    try {
      chartInstance.value.dispose()
      chartInstance.value = null
    } catch (error) {
      console.warn('Chart dispose error:', error)
    }
  }
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
