<script setup>
import { computed } from 'vue'
import { ratingLabel } from '@/utils/matchNote'

const props = defineProps({
  modelValue: { type: Number, default: null },
  readonly: { type: Boolean, default: false },
  showLabel: { type: Boolean, default: true },
  size: { type: String, default: 'md' },
})

const emit = defineEmits(['update:modelValue', 'change'])

const label = computed(() => ratingLabel(props.modelValue))

function starClass(n) {
  const v = Number(props.modelValue) || 0
  if (v >= n) return 'full'
  if (v >= n - 0.5) return 'half'
  return 'empty'
}

function pick(val) {
  if (props.readonly) return
  emit('update:modelValue', val)
  emit('change', val)
}
</script>

<template>
  <view class="sr" :class="[size, { readonly }]">
    <view
      v-for="n in 5"
      :key="n"
      class="sr-star"
      :class="starClass(n)"
    >
      <view
        v-if="!readonly"
        class="sr-hit left"
        @tap.stop="pick(n - 0.5)"
      />
      <view
        v-if="!readonly"
        class="sr-hit right"
        @tap.stop="pick(n)"
      />
    </view>
    <text v-if="showLabel && label" class="sr-lab">{{ label }}</text>
    <text v-else-if="showLabel && !readonly" class="sr-lab muted">未评分</text>
  </view>
</template>

<style lang="scss" scoped>
.sr {
  display: flex;
  align-items: center;
  gap: 4rpx;
  flex-shrink: 0;
}
.sr-star {
  position: relative;
  width: 32rpx;
  height: 32rpx;
  flex-shrink: 0;
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background: #e2e8f0;
    clip-path: polygon(
      50% 2%, 61% 35%, 98% 38%, 68% 58%, 79% 95%,
      50% 74%, 21% 95%, 32% 58%, 2% 38%, 39% 35%
    );
  }
  &.full::before { background: #d97706; }
  &.half::before {
    background: linear-gradient(90deg, #d97706 50%, #e2e8f0 50%);
  }
}
.sr-hit {
  position: absolute;
  top: -6rpx;
  bottom: -6rpx;
  width: 50%;
  z-index: 1;
  &.left { left: 0; }
  &.right { right: 0; }
}
.sr-lab {
  margin-left: 6rpx;
  font-size: 20rpx;
  font-weight: 600;
  color: #b45309;
  white-space: nowrap;
  &.muted { color: #94a3b8; font-weight: 500; }
}
.sr.sm .sr-star { width: 26rpx; height: 26rpx; }
.sr.sm .sr-lab { font-size: 20rpx; }
.sr.md .sr-star { width: 36rpx; height: 36rpx; }
.sr.lg .sr-star { width: 44rpx; height: 44rpx; }
.sr.lg .sr-lab { font-size: 24rpx; }
.readonly { pointer-events: none; }
</style>
