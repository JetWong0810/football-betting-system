<script setup>
const props = defineProps({
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  modelValue: { type: [String, Number], default: null },
})

const emit = defineEmits(['update:modelValue'])

function pick(id) {
  emit('update:modelValue', props.modelValue === id ? null : id)
}
</script>

<template>
  <view class="cr">
    <view v-if="label || hint" class="cr-head">
      <text v-if="label" class="cr-lab">{{ label }}</text>
      <text v-if="hint" class="cr-hint">{{ hint }}</text>
    </view>
    <view class="cr-ops">
      <text
        v-for="op in options"
        :key="op.id"
        class="cr-chip"
        :class="[op.tone, { on: modelValue === op.id }]"
        @tap.stop="pick(op.id)"
      >{{ op.text }}</text>
    </view>
  </view>
</template>

<style lang="scss" scoped>
.cr { margin-bottom: 14rpx; }
.cr-head {
  display: flex;
  align-items: baseline;
  gap: 8rpx;
  margin-bottom: 8rpx;
}
.cr-lab {
  font-size: 22rpx;
  font-weight: 600;
  color: #334155;
}
.cr-hint { font-size: 20rpx; color: #94a3b8; }
.cr-ops { display: flex; flex-wrap: wrap; gap: 8rpx; }
.cr-chip {
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
    &.single { color: #fff; background: #0d9488; border-color: #0d9488; }
    &.warn { color: #fff; background: #d97706; border-color: #d97706; }
    &.mute { color: #334155; background: #e2e8f0; border-color: #cbd5e1; }
  }
}
</style>
