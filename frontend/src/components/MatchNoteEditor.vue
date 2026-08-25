<script setup>
import { computed, reactive, ref, watch } from 'vue'
import StarRating from '@/components/StarRating.vue'
import NoteChipRow from '@/components/NoteChipRow.vue'
import {
  applyHints,
  cloneStructure,
  emptyStructure,
  formatNoteContent,
  hasFactorCounts,
  factorVerdict,
  isShallowHc,
  similarLabel,
  similarTone,
  hasTendency,
  singleFitLabel,
  bothSingleFitAligned,
  jcMoveLabel,
  jcMoveTone,
  factorDirTone,
  factorDirLabel,
  OTHER_HEAT_OPTS,
  RATING_SIDE_OPTS,
  structureHasValue,
} from '@/utils/matchNote'

const props = defineProps({
  visible: { type: Boolean, default: false },
  homeName: { type: String, default: '' },
  awayName: { type: String, default: '' },
  content: { type: String, default: '' },
  rating: { type: Number, default: null },
  structure: { type: Object, default: null },
  hints: { type: Object, default: () => ({}) },
  hasSaved: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  maxLen: { type: Number, default: 5000 },
})

const emit = defineEmits(['close', 'save', 'clear'])

const draft = reactive(emptyStructure())
const draftRating = ref(null)

const shallow = computed(() => isShallowHc(props.hints?.hc))
const simHint = computed(() => {
  if (shallow.value === false) return '深盘·看盘路 · 打开详情回写'
  if (shallow.value === true) return '浅盘·看不败 · 打开详情回写'
  return '打开同赔详情后自动回写'
})
const fitHint = computed(() => {
  if (!props.hints?.isSingle) return '仅单关场回写'
  if (shallow.value === false) return '深盘·单关看上/下盘'
  if (shallow.value === true) return '浅盘·单关看主/客不败'
  return '点同赔/同赛事回写单关样本'
})
const factorReady = computed(() => hasFactorCounts(draft))
const factorTag = computed(() => factorVerdict(draft))
const factorItems = computed(() => (
  Array.isArray(draft.factorItems) ? draft.factorItems.filter((f) => f && f.name) : []
))
const similarFitText = computed(() => (
  hasTendency(draft.similarSingle)
    ? singleFitLabel('similar', draft.similarSingle, draft.similarSingleHit, draft.similarSingleTotal)
    : ''
))
const eventFitText = computed(() => (
  hasTendency(draft.sameEventSingle)
    ? singleFitLabel('sameEvent', draft.sameEventSingle, draft.sameEventSingleHit, draft.sameEventSingleTotal)
    : ''
))
const similarFitNone = computed(() => draft.similarSingle === 'none')
const eventFitNone = computed(() => draft.sameEventSingle === 'none')
const fitReady = computed(() => !!(
  similarFitText.value || eventFitText.value || similarFitNone.value || eventFitNone.value
))
const bothFit = computed(() => bothSingleFitAligned(draft))
const liveSingle = computed(() => !!props.hints?.isSingle)
const liveJcMove = computed(() => props.hints?.jcMove || null)
const liveJcText = computed(() => jcMoveLabel(liveJcMove.value))
const sideHint = computed(() => {
  if (shallow.value === false) return '深盘可看上/下，也可看主/客'
  if (shallow.value === true) return '浅盘可看主/客，也可看上/下'
  return '点选你看好的一边'
})

function pickSide(id) {
  draft.ratingSide = draft.ratingSide === id ? null : id
}

function clearConclusion() {
  draftRating.value = null
  draft.ratingSide = null
}

watch(
  () => props.visible,
  (open) => {
    if (!open) return
    draftRating.value = props.rating || null
    const next = applyHints(props.structure, {
      ...props.hints,
      legacyContent: structureHasValue(props.structure) ? '' : props.content,
    })
    Object.assign(draft, emptyStructure(), cloneStructure(next))
  },
)

function close() {
  if (props.saving) return
  emit('close')
}

function save() {
  if (props.saving) return
  const structure = cloneStructure(draft)
  delete structure.heat
  structure.single = liveSingle.value ? 'yes' : null
  structure.jcMove = liveJcMove.value
  emit('save', {
    content: formatNoteContent(structure),
    rating: draftRating.value,
    structure,
  })
}
</script>

<template>
  <view v-if="visible" class="app-mask note-mask" @tap="close" />
  <view v-if="visible" class="app-modal note-modal show" @tap.stop>
    <view class="note-header">
      <view class="note-title-wrap">
        <text class="note-title">个人分析</text>
        <text v-if="homeName || awayName" class="note-teams">{{ homeName }} vs {{ awayName }}</text>
      </view>
      <text class="note-close" @tap="close">关闭</text>
    </view>
    <view class="note-conclude">
      <view class="note-side">
        <text class="note-rate-lab">倾向</text>
        <view class="note-side-ops">
          <text
            v-for="op in RATING_SIDE_OPTS"
            :key="op.id"
            class="note-side-chip"
            :class="[op.tone, { on: draft.ratingSide === op.id }]"
            @tap.stop="pickSide(op.id)"
          >{{ op.text }}</text>
        </view>
      </view>
      <text class="note-side-hint">{{ sideHint }}</text>
      <view class="note-rate">
        <text class="note-rate-lab">把握</text>
        <StarRating v-model="draftRating" :side="draft.ratingSide" size="lg" />
        <text
          v-if="draftRating || draft.ratingSide"
          class="note-rate-clear"
          @tap="clearConclusion"
        >清除</text>
      </view>
    </view>
    <view class="note-scroll">
      <view v-if="liveSingle" class="factor-sum">
        <view class="factor-head">
          <text class="factor-lab">单关</text>
          <text class="factor-hint">竞彩胜平负单固</text>
        </view>
        <text class="fn single">单关</text>
      </view>
      <view class="factor-sum">
        <view class="factor-head">
          <text class="factor-lab">预测因子</text>
          <text class="factor-hint">含交锋，共8项</text>
        </view>
        <view v-if="factorReady" class="factor-nums">
          <text class="fn upper">上盘 {{ draft.factorUpper || 0 }}</text>
          <text class="fn lower">下盘 {{ draft.factorLower || 0 }}</text>
          <text class="fn mute">中性 {{ draft.factorNeutral || 0 }}</text>
          <text v-if="factorTag" class="fn" :class="factorTag.tone">{{ factorTag.text }}</text>
        </view>
        <view v-if="factorItems.length" class="factor-list">
          <view v-for="f in factorItems" :key="f.name" class="factor-row">
            <text class="factor-name">{{ f.name }}</text>
            <text class="fn sm" :class="factorDirTone(f.direction)">{{ factorDirLabel(f.name, f.direction) }}</text>
            <text class="factor-score">{{ f.score != null ? f.score : '-' }}</text>
          </view>
        </view>
        <text v-if="!factorReady" class="factor-empty">点「预」出结果后自动回写</text>
      </view>
      <view class="factor-sum">
        <view class="factor-head">
          <text class="factor-lab">同赔</text>
          <text class="factor-hint">{{ simHint }} · ≥3场且>70%</text>
        </view>
        <text v-if="hasTendency(draft.similar)" class="fn" :class="similarTone(draft.similar)">{{ similarLabel(draft.similar, draft.similarPct) }}</text>
        <text v-else-if="draft.similar === 'none'" class="fn mute">无倾向</text>
        <text v-else class="factor-empty">打开同赔详情后自动回写</text>
      </view>
      <view class="factor-sum">
        <view class="factor-head">
          <text class="factor-lab">同赛事</text>
          <text class="factor-hint">点同赛事出结果 · ≥2场且>70%</text>
        </view>
        <text v-if="hasTendency(draft.sameEvent)" class="fn" :class="similarTone(draft.sameEvent)">{{ similarLabel(draft.sameEvent, draft.sameEventPct) }}</text>
        <text v-else-if="draft.sameEvent === 'none'" class="fn mute">无倾向</text>
        <text v-else class="factor-empty">点同赛事出结果后自动回写</text>
      </view>
      <view class="factor-sum">
        <view class="factor-head">
          <text class="factor-lab">单关匹配</text>
          <text class="factor-hint">{{ fitHint }}</text>
        </view>
        <view v-if="fitReady" class="factor-nums">
          <text v-if="similarFitText" class="fn" :class="similarTone(draft.similarSingle)">{{ similarFitText }}</text>
          <text v-else-if="similarFitNone" class="fn mute">同赔单关无倾向</text>
          <text v-if="eventFitText" class="fn" :class="similarTone(draft.sameEventSingle)">{{ eventFitText }}</text>
          <text v-else-if="eventFitNone" class="fn mute">同赛事单关无倾向</text>
          <text v-if="bothFit" class="fn warn">两边同向</text>
        </view>
        <text v-else class="factor-empty">{{ hints?.isSingle ? '点同赔/同赛事，回写单关样本分数' : '非单关场不回写' }}</text>
      </view>
      <view class="factor-sum">
        <view class="factor-head">
          <text class="factor-lab">竞彩</text>
          <text class="factor-hint">让球方水位 · 随赔率更新</text>
        </view>
        <text v-if="liveJcText" class="fn" :class="jcMoveTone(liveJcMove)">{{ liveJcText }}</text>
        <text v-else class="fn mute">无初终盘</text>
      </view>
      <NoteChipRow v-model="draft.otherHeat" label="个人热度分析" :options="OTHER_HEAT_OPTS" />
      <view class="note-extra">
        <text class="note-extra-lab">补充</text>
        <textarea
          class="note-input"
          v-model="draft.extra"
          :maxlength="maxLen"
          placeholder="矛盾点、放弃原因等，可空"
          :disabled="saving"
          :show-confirm-bar="false"
          :adjust-position="true"
          :cursor-spacing="20"
        />
      </view>
    </view>
    <view class="note-footer">
      <text class="note-count">先选倾向，再打把握</text>
      <view class="note-actions">
        <text
          v-if="hasSaved"
          class="note-btn danger"
          :class="{ disabled: saving }"
          @tap="!saving && $emit('clear')"
        >清空</text>
        <text
          class="note-btn primary"
          :class="{ disabled: saving }"
          @tap="save"
        >{{ saving ? '保存中' : '保存' }}</text>
      </view>
    </view>
  </view>
</template>

<style lang="scss" scoped>
.note-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  z-index: 220;
}
.note-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  right: auto;
  width: min(398px, calc(100vw - 32px));
  max-height: min(88vh, 740px);
  background: #fff;
  border-radius: 12rpx;
  z-index: 221;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 16rpx 48rpx rgba(15, 23, 42, 0.18);
  transform: translate(-50%, -50%);
}
.note-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16rpx;
  padding: 20rpx 24rpx 8rpx;
  flex-shrink: 0;
}
.note-title-wrap { min-width: 0; flex: 1; }
.note-title { display: block; font-size: 28rpx; font-weight: 600; color: #1e293b; }
.note-teams {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.note-close { font-size: 24rpx; color: #0d9488; padding: 4rpx; flex-shrink: 0; }
.note-conclude {
  padding: 4rpx 24rpx 12rpx;
  border-bottom: 1rpx solid #f1f5f9;
  flex-shrink: 0;
}
.note-side {
  display: flex;
  align-items: center;
  gap: 12rpx;
}
.note-side-ops { display: flex; flex-wrap: wrap; gap: 8rpx; min-width: 0; }
.note-side-chip {
  font-size: 22rpx;
  line-height: 1.3;
  padding: 8rpx 14rpx;
  border-radius: 6rpx;
  color: #475569;
  background: #f1f5f9;
  border: 1rpx solid #e2e8f0;
  &.on {
    font-weight: 600;
    &.upper { color: #fff; background: #dc2626; border-color: #dc2626; }
    &.lower { color: #fff; background: #059669; border-color: #059669; }
  }
}
.note-side-hint {
  display: block;
  margin: 6rpx 0 8rpx 60rpx;
  font-size: 20rpx;
  color: #94a3b8;
}
.note-rate {
  display: flex;
  align-items: center;
  gap: 12rpx;
}
.note-rate-lab {
  font-size: 22rpx;
  font-weight: 600;
  color: #475569;
  flex-shrink: 0;
  min-width: 48rpx;
}
.note-rate-clear {
  margin-left: auto;
  font-size: 20rpx;
  color: #94a3b8;
}
.note-scroll {
  flex: 1;
  min-height: 0;
  max-height: 56vh;
  padding: 12rpx 24rpx 8rpx;
  box-sizing: border-box;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.factor-sum { margin-bottom: 14rpx; }
.factor-head {
  display: flex;
  align-items: baseline;
  gap: 8rpx;
  margin-bottom: 8rpx;
}
.factor-lab { font-size: 22rpx; font-weight: 600; color: #334155; }
.factor-hint { font-size: 20rpx; color: #94a3b8; }
.factor-nums { display: flex; flex-wrap: wrap; gap: 8rpx; }
.fn {
  font-size: 22rpx;
  line-height: 1.3;
  padding: 8rpx 14rpx;
  border-radius: 6rpx;
  font-weight: 600;
  &.upper { color: #dc2626; background: #fef2f2; }
  &.lower { color: #059669; background: #ecfdf5; }
  &.single { color: #0f766e; background: #f0fdfa; }
  &.mute { color: #64748b; background: #f1f5f9; }
  &.warn { color: #b45309; background: #fffbeb; }
  &.sm { font-size: 20rpx; padding: 4rpx 10rpx; }
}
.factor-list {
  margin-top: 8rpx;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}
.factor-row {
  display: flex;
  align-items: center;
  gap: 8rpx;
}
.factor-name {
  flex: 1;
  min-width: 0;
  font-size: 22rpx;
  color: #475569;
}
.factor-score {
  width: 48rpx;
  flex-shrink: 0;
  text-align: right;
  font-size: 22rpx;
  font-weight: 600;
  color: #334155;
  font-variant-numeric: tabular-nums;
}
.factor-empty { font-size: 22rpx; color: #94a3b8; }
.note-extra { margin: 6rpx 0 12rpx; }
.note-extra-lab {
  display: block;
  font-size: 22rpx;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8rpx;
}
.note-input {
  display: block;
  width: 100%;
  height: 140rpx;
  min-height: 140rpx;
  padding: 12rpx;
  font-size: 24rpx;
  line-height: 1.5;
  color: #1e293b;
  background: #f8fafc;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
  box-sizing: border-box;
}
.note-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12rpx 24rpx 18rpx;
  gap: 16rpx;
  flex-shrink: 0;
  border-top: 1rpx solid #f1f5f9;
}
.note-count { font-size: 20rpx; color: #94a3b8; }
.note-actions { display: flex; gap: 12rpx; }
.note-btn {
  font-size: 24rpx;
  border-radius: 6rpx;
  padding: 10rpx 22rpx;
  line-height: 1.3;
  &.primary { color: #fff; background: #2563eb; }
  &.danger { color: #dc2626; background: #fef2f2; border: 1rpx solid #fecaca; }
  &.disabled { opacity: 0.5; }
}
</style>
