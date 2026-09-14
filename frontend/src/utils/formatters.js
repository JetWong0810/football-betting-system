export const formatCurrency = (value = 0, prefix = '¥') => {
  const num = Number(value || 0)
  return `${prefix}${num.toFixed(2)}`
}

export const formatPercent = (value = 0, digits = 1) => {
  return `${(Number(value) * 100).toFixed(digits)}%`
}

/** 500.com 亚盘原值(正=主让) → 系统标准(负=主让)，正数带 + */
export function formatAh500(raw) {
  if (raw === undefined || raw === null || raw === '' || raw === '-') return ''
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  const std = -n
  if (Object.is(std, -0) || std === 0) return '0'
  return std > 0 ? `+${std}` : `${std}`
}
