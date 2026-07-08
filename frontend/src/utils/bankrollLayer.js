/**
 * 资金分层模块:本金 / 盈利金 分离管理
 *
 * 核心思路:
 * - principal(本金)= startingCapital,锁定不随盈亏增长,需要保护
 * - profitPool(盈利金)= 累计已实现盈利 - 已提取盈利;本质是"市场的钱",可承担更高风险
 * - effectiveBankroll(有效资金)= principal + profitPool × profitAggressiveRatio
 *   盈利金只按一部分计入有效资金,抑制"盈利滚进本金放大仓位"的雪球效应
 *
 * 所有仓位计算(信心档金额、凯利参考)都用 effectiveBankroll,而非总 bankroll。
 * bankroll(总资金,展示用)仍 = startingCapital + totalProfit - bettingStake。
 */

/**
 * 计算资金分层
 * @param {object} opts
 * @param {number} opts.startingCapital 初始本金
 * @param {number} opts.totalProfit 累计已结算盈亏
 * @param {number} [opts.realizedWithdraw=0] 已提取落袋的盈利
 * @param {number} [opts.profitAggressiveRatio=0.5] 盈利金计入有效资金的比例
 * @returns {{principal:number, profitPool:number, effectiveBankroll:number}}
 */
export function computeBankrollLayer({
  startingCapital,
  totalProfit,
  realizedWithdraw = 0,
  profitAggressiveRatio = 0.5
}) {
  const principal = Math.max(Number(startingCapital) || 0, 0)
  const profitPool = Math.max(0, Number(totalProfit) - Number(realizedWithdraw))
  const ratio = Math.min(Math.max(Number(profitAggressiveRatio) || 0, 0), 1)
  const effectiveBankroll = principal + profitPool * ratio
  return { principal, profitPool, effectiveBankroll }
}

/**
 * 出金阀:盈利金达到本金阈值时,提示提取盈利的一部分落袋
 * @param {object} opts
 * @param {number} opts.profitPool 当前盈利金
 * @param {number} opts.principal 本金
 * @param {number} [opts.threshold=0.3] 触发阈值(盈利金/本金)
 * @param {number} [opts.ratio=0.5] 触发后建议提取盈利金的比例
 * @returns {{trigger:boolean, amount:number}}
 */
export function suggestWithdraw({
  profitPool,
  principal,
  threshold = 0.3,
  ratio = 0.5
}) {
  if (principal <= 0) return { trigger: false, amount: 0 }
  const trigger = profitPool / principal >= Number(threshold)
  const amount = trigger ? Math.round(Number(profitPool) * Number(ratio)) : 0
  return { trigger, amount }
}
