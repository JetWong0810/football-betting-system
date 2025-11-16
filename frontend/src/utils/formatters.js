export const formatCurrency = (value = 0, prefix = '¥') => {
  const num = Number(value || 0)
  return `${prefix}${num.toFixed(2)}`
}

export const formatPercent = (value = 0, digits = 1) => {
  return `${(Number(value) * 100).toFixed(digits)}%`
}
