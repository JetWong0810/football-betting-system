/**
 * 历史同赔弹窗统计: 胜平负 + 亚盘盘路
 * 口径与后端 _calc_stats 一致: 半上归上盘、半下归下盘(各计1), 走水单列
 */

function pct(n, total) {
  if (!total) return 0
  return Math.round((n / total) * 1000) / 10
}

export function calcSimilarStats(matches) {
  const list = Array.isArray(matches) ? matches : []
  const total = list.length

  let win = 0
  let draw = 0
  let loss = 0
  let upper = 0
  let lower = 0
  let push = 0
  let halfUp = 0
  let halfDown = 0
  let ahTotal = 0

  for (const m of list) {
    const r = m?.result
    if (r === '主胜') win += 1
    else if (r === '平局') draw += 1
    else if (r === '客胜') loss += 1

    const ah = m?.ahResult
    if (!ah || ah === '-') continue
    ahTotal += 1
    if (ah === '上盘') {
      upper += 1
    } else if (ah === '半上') {
      upper += 1
      halfUp += 1
    } else if (ah === '下盘') {
      lower += 1
    } else if (ah === '半下') {
      lower += 1
      halfDown += 1
    } else if (ah === '走水') {
      push += 1
    } else {
      ahTotal -= 1
    }
  }

  return {
    total,
    win,
    draw,
    loss,
    winPct: pct(win, total),
    drawPct: pct(draw, total),
    lossPct: pct(loss, total),
    ahTotal,
    upper,
    lower,
    push,
    halfUp,
    halfDown,
    upperPct: pct(upper, ahTotal),
    lowerPct: pct(lower, ahTotal),
    pushPct: pct(push, ahTotal),
  }
}
