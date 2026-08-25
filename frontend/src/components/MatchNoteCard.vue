<script setup>
import { computed, ref } from 'vue'
import StarRating from '@/components/StarRating.vue'
import { hasNote, noteLines, structureChips, structureHasValue, liveObjectiveChips } from '@/utils/matchNote'

const props = defineProps({
  note: { type: Object, default: null },
  isSingle: { type: Boolean, default: false },
  jcMove: { type: String, default: null },
})

const emit = defineEmits(['edit', 'rate'])

const expanded = ref(false)
const chips = computed(() => [
  ...liveObjectiveChips(props.isSingle, props.jcMove),
  ...structureChips(props.note?.structure),
])
const extra = computed(() => {
  const fromStruct = String(props.note?.structure?.extra || '').trim()
  if (fromStruct) return fromStruct
  if (structureHasValue(props.note?.structure)) return ''
  return noteLines(props.note?.content)
})
const filled = computed(() => hasNote(props.note))
const overflow = computed(() => extra.value.split('\n').length > 4 || extra.value.length > 90)
const shownExtra = computed(() => {
  if (!extra.value || expanded.value || !overflow.value) return extra.value
  const lines = extra.value.split('\n')
  if (lines.length > 4) return lines.slice(0, 4).join('\n')
  return extra.value.slice(0, 90)
})

function onRate(val) {
  emit('rate', val)
}
</script>

<template>
  <view class="note-card" :class="{ filled }">
    <view class="note-head">
      <text class="note-lab" @tap.stop="$emit('edit')">个人分析</text>
      <StarRating
        size="sm"
        :model-value="note?.rating || null"
        :side="note?.structure?.ratingSide || null"
        :show-label="!!(note?.rating || note?.structure?.ratingSide)"
        @change="onRate"
      />
      <text class="note-go" @tap.stop="$emit('edit')">{{ filled ? '编辑' : '填写' }} ›</text>
    </view>
    <view v-if="chips.length" class="note-chips" @tap.stop="$emit('edit')">
      <text
        v-for="(c, i) in chips"
        :key="i"
        class="note-chip"
        :class="c.tone"
      >{{ c.text }}</text>
    </view>
    <text
      v-if="shownExtra"
      class="note-body"
      @tap.stop="$emit('edit')"
    >{{ shownExtra }}</text>
    <text
      v-else-if="!chips.length"
      class="note-ph"
      @tap.stop="$emit('edit')"
    >先选倾向再打分</text>
    <text
      v-if="overflow"
      class="note-more"
      @tap.stop="expanded = !expanded"
    >{{ expanded ? '收起' : '展开全文' }}</text>
  </view>
</template>

<style lang="scss" scoped>
.note-card {
  margin-top: 10rpx;
  padding: 12rpx 12rpx 10rpx;
  background: #f8fafc;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
  &.filled {
    background: #fffbeb;
    border-color: #fde68a;
  }
}
.note-head {
  display: flex;
  align-items: center;
  gap: 10rpx;
}
.note-lab {
  font-size: 20rpx;
  font-weight: 600;
  color: #475569;
  flex-shrink: 0;
}
.note-go {
  margin-left: auto;
  font-size: 20rpx;
  color: #64748b;
  flex-shrink: 0;
}
.note-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6rpx;
  margin-top: 8rpx;
}
.note-chip {
  font-size: 20rpx;
  line-height: 1.3;
  padding: 4rpx 10rpx;
  border-radius: 6rpx;
  color: #475569;
  background: #f1f5f9;
  &.upper { color: #dc2626; background: #fef2f2; }
  &.lower { color: #059669; background: #ecfdf5; }
  &.single { color: #0f766e; background: #f0fdfa; }
  &.warn { color: #b45309; background: #fffbeb; }
}
.note-body {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  line-height: 1.55;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}
.note-ph {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #94a3b8;
}
.note-more {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: #b45309;
}
</style>
