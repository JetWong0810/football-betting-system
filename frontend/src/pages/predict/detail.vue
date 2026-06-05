<template>
  <view class="predict-detail">
    <!-- 比赛信息头 -->
    <view class="match-header">
      <view class="header-meta">
        <text class="league-badge" :style="{ backgroundColor: leagueColor }">{{ matchInfo.league }}</text>
        <text class="match-time">{{ matchInfo.time }}</text>
        <view v-if="matchInfo.isSingle" class="single-tag">
          <text>单关</text>
        </view>
      </view>
      <view class="header-teams">
        <text class="team home">{{ matchInfo.home }}</text>
        <view class="center-info">
          <text v-if="matchInfo.status === 'finished'" class="score">{{ matchInfo.homeScore }} - {{ matchInfo.awayScore }}</text>
          <text v-else class="vs-text">VS</text>
          <text class="handicap-tag" v-if="matchInfo.handicap">让 {{ matchInfo.handicap }}</text>
        </view>
        <text class="team away">{{ matchInfo.away }}</text>
      </view>
    </view>

    <!-- 预测结果卡片 -->
    <view class="result-card" :class="predictionClass" v-if="prediction.direction">
      <view class="result-main">
        <text class="result-arrow">{{ prediction.direction === 'upper' ? '⬆' : '⬇' }}</text>
        <text class="result-text">{{ prediction.direction === 'upper' ? '上盘' : '下盘' }}</text>
      </view>
      <view class="result-confidence">
        <text class="conf-value">{{ prediction.confidence }}%</text>
        <text class="conf-label">置信度</text>
      </view>
      <view v-if="matchInfo.status === 'finished'" class="result-verdict" :class="prediction.hit ? 'hit' : 'miss'">
        <text>{{ prediction.hit ? '✓ 命中' : '✗ 未中' }}</text>
      </view>
    </view>

    <!-- 因子分析 -->
    <view class="factors-section">
      <view class="section-header">
        <text class="section-title">因子分析</text>
        <text class="section-sub">综合{{ factors.length }}项指标</text>
      </view>

      <view class="factor-list">
        <view class="factor-card" v-for="(factor, idx) in factors" :key="idx">
          <view class="factor-header">
            <view class="factor-num">
              <text>{{ idx + 1 }}</text>
            </view>
            <text class="factor-name">{{ factor.name }}</text>
            <view class="factor-result">
              <text class="factor-direction" :class="factor.dirClass">{{ factor.dirLabel }}</text>
              <view class="factor-score">
                <view class="score-bar">
                  <view class="score-fill" :style="{ width: factor.score * 10 + '%' }"></view>
                </view>
                <text class="score-text">{{ factor.score }}/10</text>
              </view>
            </view>
          </view>
          <text class="factor-reason">{{ factor.reason }}</text>
        </view>
      </view>
    </view>

    <!-- 市场热度（手动选择） -->
    <view class="heat-section" v-if="!prediction.direction">
      <view class="section-header">
        <text class="section-title">市场热度</text>
        <text class="section-sub">请选择你观察到的市场倾向</text>
      </view>
      <view class="heat-options">
        <view
          class="heat-option"
          :class="{ active: marketHeat === 'upper' }"
          @tap="marketHeat = 'upper'"
        >
          <text class="heat-icon">🔥</text>
          <text>上盘热</text>
        </view>
        <view
          class="heat-option"
          :class="{ active: marketHeat === 'neutral' }"
          @tap="marketHeat = 'neutral'"
        >
          <text class="heat-icon">➖</text>
          <text>均衡</text>
        </view>
        <view
          class="heat-option"
          :class="{ active: marketHeat === 'lower' }"
          @tap="marketHeat = 'lower'"
        >
          <text class="heat-icon">🔥</text>
          <text>下盘热</text>
        </view>
      </view>
    </view>

    <!-- AI分析 -->
    <view class="ai-section" v-if="aiAnalysis">
      <view class="section-header">
        <view class="ai-badge">
          <text class="ai-icon">✦</text>
          <text>AI 分析</text>
        </view>
      </view>
      <view class="ai-content">
        <text>{{ aiAnalysis }}</text>
      </view>
    </view>

    <!-- 开始预测按钮 -->
    <view class="bottom-action" v-if="!prediction.direction">
      <button class="predict-btn" :disabled="predicting" @tap="startPredict">
        <text v-if="predicting">分析中...</text>
        <text v-else>开始预测</text>
      </button>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'

const matchId = ref('')
const matchInfo = ref({
  league: '',
  time: '',
  home: '',
  away: '',
  handicap: '',
  isSingle: false,
  status: '',
  homeScore: null,
  awayScore: null
})

const marketHeat = ref('neutral')
const prediction = ref({ direction: '', confidence: 0, hit: null })
const factors = ref([])
const aiAnalysis = ref('')
const predicting = ref(false)

const leagueColor = computed(() => {
  const colors = {
    '英超': '#3d195b', '西甲': '#ee8707', '德甲': '#d20515',
    '意甲': '#008fd7', '法甲': '#dae025', '欧冠': '#2b2d42',
  }
  return colors[matchInfo.value.league] || '#6b7280'
})

const predictionClass = computed(() => {
  if (!prediction.value.direction) return ''
  return prediction.value.direction === 'upper' ? 'upper' : 'lower'
})

function loadMatchInfo() {
  matchInfo.value = {
    league: '英超',
    time: '2026-06-05 20:00',
    home: '曼城',
    away: '阿森纳',
    handicap: -0.5,
    isSingle: true,
    status: 'not_started',
    homeScore: null,
    awayScore: null
  }
}

function startPredict() {
  predicting.value = true
  setTimeout(() => {
    prediction.value = {
      direction: 'upper',
      confidence: 72,
      hit: null
    }
    factors.value = [
      { name: '赔率结构', score: 8, reason: '主胜赔1.65，客胜赔4.20，主队处于强势定位，strength_gap=2.55', dirLabel: '上盘', dirClass: 'upper' },
      { name: '赔率变动', score: 6, reason: '主胜赔由1.72降至1.65，客胜由4.00升至4.20，趋势利好主队但降幅不大', dirLabel: '上盘', dirClass: 'upper' },
      { name: '近期状态', score: 7, reason: '曼城近10场7胜2平1负，场均净胜1.2球；阿森纳近10场6胜2平2负，场均净胜0.8球', dirLabel: '上盘', dirClass: 'upper' },
      { name: '交锋历史', score: 5, reason: '近6次交锋曼城3胜1平2负，主场优势不明显，近2次交锋各胜1场', dirLabel: '中性', dirClass: 'neutral' },
      { name: '市场热度', score: 7, reason: '上盘热度较高，结合逆向思维需警惕，但本场基本面支撑上盘', dirLabel: '上盘', dirClass: 'upper' },
      { name: '大小球趋势', score: 6, reason: '大球盘口由2.5降至2.25，大球水位上升，预示进球可能偏少，利好让球上盘', dirLabel: '上盘', dirClass: 'upper' },
    ]
    aiAnalysis.value = '综合分析：曼城主场让半球面对阿森纳，赔率结构显示主队处于明确强势定位，初盘至终盘主胜赔持续走低，市场对曼城信心充足。近期状态曼城略优，主场发挥稳定。交锋历史略显中性，但综合赔率结构和状态因子，上盘方向较为明确。大小球盘口走低暗示比赛可能趋向低分，进一步支撑让球上盘。建议方向：上盘（曼城-0.5），置信度中高。需注意阿森纳客场抗压能力较强，不宜过度加注。'
    predicting.value = false
  }, 1500)
}

onLoad((options) => {
  matchId.value = options?.matchId || 'mock'
  loadMatchInfo()
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.predict-detail {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f8f5 0%, #f0fdf9 60%, #fff 100%);
  padding: 24rpx;
  padding-bottom: 160rpx;
}

// 比赛信息头
.match-header {
  @include card;
  padding: 28rpx;
  margin-bottom: 24rpx;

  .header-meta {
    display: flex;
    align-items: center;
    gap: 12rpx;
    margin-bottom: 20rpx;

    .league-badge {
      font-size: 20rpx;
      color: #fff;
      padding: 4rpx 12rpx;
      border-radius: 4rpx;
    }
    .match-time {
      font-size: 24rpx;
      color: #6b7280;
    }
    .single-tag {
      margin-left: auto;
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.3);
      border-radius: 4rpx;
      padding: 2rpx 10rpx;
      text { font-size: 20rpx; color: $frbt-negative; }
    }
  }

  .header-teams {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 20rpx;

    .team {
      flex: 1;
      font-size: 32rpx;
      font-weight: 700;
      color: #1f2937;

      &.home { text-align: right; }
      &.away { text-align: left; }
    }

    .center-info {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6rpx;
      min-width: 120rpx;

      .vs-text {
        font-size: 26rpx;
        color: #9ca3af;
      }
      .score {
        font-size: 36rpx;
        font-weight: 700;
        color: $frbt-primary;
      }
      .handicap-tag {
        font-size: 20rpx;
        color: $frbt-primary;
        background: rgba(13, 148, 136, 0.08);
        padding: 2rpx 10rpx;
        border-radius: 4rpx;
      }
    }
  }
}

// 预测结果卡片
.result-card {
  border-radius: 16rpx;
  padding: 32rpx;
  margin-bottom: 24rpx;
  display: flex;
  align-items: center;
  gap: 24rpx;
  position: relative;
  overflow: hidden;

  &.upper {
    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
    border: 1px solid rgba(239, 68, 68, 0.2);
  }
  &.lower {
    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
    border: 1px solid rgba(16, 185, 129, 0.2);
  }

  .result-main {
    display: flex;
    align-items: center;
    gap: 12rpx;

    .result-arrow {
      font-size: 40rpx;
    }
    .result-text {
      font-size: 36rpx;
      font-weight: 700;
      color: #1f2937;
    }
  }

  .result-confidence {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-left: auto;

    .conf-value {
      font-size: 40rpx;
      font-weight: 700;
      color: #1f2937;
    }
    .conf-label {
      font-size: 20rpx;
      color: #6b7280;
    }
  }

  .result-verdict {
    position: absolute;
    top: 16rpx;
    right: 16rpx;
    padding: 4rpx 16rpx;
    border-radius: 20rpx;
    font-size: 22rpx;
    font-weight: 600;

    &.hit {
      background: rgba(16, 185, 129, 0.15);
      color: $frbt-positive;
    }
    &.miss {
      background: rgba(239, 68, 68, 0.15);
      color: $frbt-negative;
    }
  }
}

// 因子分析
.factors-section {
  margin-bottom: 24rpx;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16rpx;
  padding: 0 4rpx;

  .section-title {
    font-size: 28rpx;
    font-weight: 600;
    color: #1f2937;
  }
  .section-sub {
    font-size: 22rpx;
    color: #9ca3af;
  }
}

.factor-list {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.factor-card {
  @include card;
  padding: 20rpx 24rpx;

  .factor-header {
    display: flex;
    align-items: center;
    gap: 12rpx;
    margin-bottom: 10rpx;

    .factor-num {
      width: 36rpx;
      height: 36rpx;
      border-radius: 50%;
      background: $frbt-primary;
      display: flex;
      align-items: center;
      justify-content: center;
      text { font-size: 20rpx; color: #fff; font-weight: 600; }
    }

    .factor-name {
      font-size: 26rpx;
      font-weight: 600;
      color: #374151;
    }

    .factor-result {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 12rpx;

      .factor-direction {
        font-size: 22rpx;
        font-weight: 600;
        padding: 2rpx 10rpx;
        border-radius: 4rpx;

        &.upper {
          color: $frbt-negative;
          background: rgba(239, 68, 68, 0.08);
        }
        &.lower {
          color: $frbt-positive;
          background: rgba(16, 185, 129, 0.08);
        }
        &.neutral {
          color: #6b7280;
          background: rgba(107, 114, 128, 0.08);
        }
      }

      .factor-score {
        display: flex;
        align-items: center;
        gap: 8rpx;

        .score-bar {
          width: 60rpx;
          height: 8rpx;
          background: #e5e7eb;
          border-radius: 4rpx;
          overflow: hidden;

          .score-fill {
            height: 100%;
            background: $frbt-primary;
            border-radius: 4rpx;
            transition: width 0.3s;
          }
        }
        .score-text {
          font-size: 20rpx;
          color: #6b7280;
          min-width: 60rpx;
        }
      }
    }
  }

  .factor-reason {
    font-size: 24rpx;
    color: #6b7280;
    line-height: 1.5;
    padding-left: 48rpx;
  }
}

// 市场热度选择
.heat-section {
  margin-bottom: 24rpx;
}

.heat-options {
  display: flex;
  gap: 16rpx;

  .heat-option {
    flex: 1;
    @include card;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24rpx 16rpx;
    gap: 8rpx;
    border: 2px solid transparent;
    transition: all 0.2s;

    &.active {
      border-color: $frbt-primary;
      background: rgba(13, 148, 136, 0.04);
    }

    .heat-icon {
      font-size: 32rpx;
    }
    text {
      font-size: 24rpx;
      color: #374151;
    }
  }
}

// AI分析
.ai-section {
  margin-bottom: 24rpx;

  .ai-badge {
    display: flex;
    align-items: center;
    gap: 8rpx;

    .ai-icon {
      font-size: 28rpx;
      color: $frbt-primary;
    }
    text {
      font-size: 28rpx;
      font-weight: 600;
      color: #1f2937;
    }
  }

  .ai-content {
    @include card;
    padding: 24rpx;
    margin-top: 12rpx;
    background: linear-gradient(135deg, #f0fdfa 0%, #fff 100%);
    border: 1px solid rgba(13, 148, 136, 0.15);

    text {
      font-size: 26rpx;
      color: #374151;
      line-height: 1.7;
    }
  }
}

// 底部按钮
.bottom-action {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 24rpx 32rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
  background: #fff;
  box-shadow: 0 -4rpx 12rpx rgba(0, 0, 0, 0.05);

  .predict-btn {
    width: 100%;
    height: 88rpx;
    background: linear-gradient(135deg, $frbt-primary 0%, $frbt-secondary 100%);
    color: #fff;
    border: none;
    border-radius: 44rpx;
    font-size: 32rpx;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 8rpx 24rpx rgba(13, 148, 136, 0.35);

    &[disabled] {
      opacity: 0.6;
    }
  }
}
</style>
