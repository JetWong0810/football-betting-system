<template>
  <view class="chart-card">
    <view v-if="!bands.length" class="empty">暂无预测数据</view>
    <view v-else ref="chartRef" class="chart" />
  </view>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  bands: {
    type: Array,
    default: () => []
  }
})

const chartRef = ref(null)
const chartInstance = ref(null)

function initChart () {
  try {
    if (!chartRef.value) return
    if (!props.bands.length) return
    chartInstance.value = echarts.init(chartRef.value)
    renderChart()
  } catch (error) {
    console.warn('Chart init error:', error)
  }
}

function renderChart () {
  try {
    if (!chartInstance.value) return
    if (!props.bands.length) return

    const labels = props.bands.map(b => b.band)
    const rates = props.bands.map(b => b.hitRate == null ? 0 : Math.round(b.hitRate * 100))
    const totals = props.bands.map(b => b.total)

    chartInstance.value.setOption({
      textStyle: { color: '#1c1c1c' },
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const idx = params[0].dataIndex
          const b = props.bands[idx]
          return `${b.band}<br/>命中率 ${rates[idx]}%<br/>样本 ${b.total}场（命中${b.hit}）`
        }
      },
      grid: { left: '8%', right: '5%', bottom: '12%', top: '15%' },
      xAxis: { type: 'category', data: labels },
      yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
      series: [
        {
          type: 'bar',
          data: rates,
          barWidth: '50%',
          itemStyle: {
            color: (params) => {
              const r = rates[params.dataIndex]
              if (r >= 60) return '#0d9488'
              if (r >= 50) return '#f59e0b'
              return '#ef4444'
            },
            borderRadius: [6, 6, 0, 0]
          },
          label: {
            show: true,
            position: 'top',
            formatter: (p) => totals[p.dataIndex] ? `${p.value}%` : '',
            fontSize: 18,
            color: '#6b7280'
          }
        }
      ]
    })
  } catch (error) {
    console.warn('Chart render error:', error)
  }
}

watch(() => props.bands, () => {
  nextTick(() => {
    if (!chartInstance.value && props.bands.length) {
      initChart()
    } else if (chartInstance.value) {
      renderChart()
    }
  })
}, { deep: true })

onMounted(() => {
  nextTick(() => {
    if (props.bands.length) {
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
