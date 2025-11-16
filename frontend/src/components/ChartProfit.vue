<template>
  <view class="chart-card">
    <view v-if="!series.length" class="empty">暂无盈亏数据</view>
    <view v-else ref="chartRef" class="chart" />
  </view>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  series: {
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
  const dates = props.series.map(item => item.date)
  const balance = props.series.map(item => item.balance)
  const profit = props.series.map(item => item.profit)

  chartInstance.value.setOption({
    textStyle: {
      color: '#1c1c1c'
    },
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['余额', '当日盈亏']
    },
    grid: {
      left: '5%',
      right: '5%',
      bottom: '10%',
      top: '15%'
    },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '余额',
        type: 'line',
        smooth: true,
        data: balance,
        lineStyle: {
          color: '#0d9488',
          width: 3
        },
        itemStyle: {
          color: '#0d9488'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(13, 148, 136, 0.3)' },
              { offset: 1, color: 'rgba(13, 148, 136, 0.05)' }
            ]
          }
        }
      },
      {
        name: '当日盈亏',
        type: 'bar',
        data: profit,
        itemStyle: {
          color: params => params.value >= 0 ? '#10b981' : '#ef4444'
        }
      }
    ]
  })
}

watch(() => props.series, () => {
  if (!chartInstance.value) return
  renderChart()
}, { deep: true })

onMounted(() => {
  initChart()
})

onBeforeUnmount(() => {
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.chart-card {
  @include card;
  min-height: 360rpx;
  padding: 20rpx;
}

.chart {
  width: 100%;
  height: 320rpx;
}

.empty {
  text-align: center;
  padding: 100rpx 0;
  color: #9ca3af;
  font-size: 26rpx;
}
</style>
