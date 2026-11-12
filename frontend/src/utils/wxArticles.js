import { request } from '@/utils/http'

export const listArticles = (params) => request({ url: '/api/wx/articles', data: params })
export const getArticle = (id) => request({ url: `/api/wx/articles/${id}` })
export const getAccounts = () => request({ url: '/api/wx/accounts' })
export const getMatchCounts = (ids) => request({ url: '/api/wx/match-counts', data: { ids: ids.join(',') } })
export const getCandidates = (id) => request({ url: `/api/wx/articles/${id}/candidates` })
export const linkMatch = (id, matchId) =>
  request({ url: `/api/wx/articles/${id}/link`, method: 'POST', data: { match_id: matchId } })
export const unlinkMatch = (id, matchId) =>
  request({ url: `/api/wx/articles/${id}/link/${encodeURIComponent(matchId)}`, method: 'DELETE' })
export const reprocess = (id) => request({ url: `/api/wx/articles/${id}/reprocess`, method: 'POST' })

const MARKET = { spf: '胜平负', rqspf: '让球胜平负', ah: '亚盘', ou: '大小球', score: '比分', dc: '双选', other: '其他' }
const SEL = {
  home: '主胜', draw: '平', away: '客胜', home_draw: '主胜或平(主不败)', away_draw: '客胜或平(客不败)',
  over: '大球', under: '小球',
}
export function pickText(p) {
  const m = MARKET[p.market] || p.market
  const s = SEL[p.selection] || p.selection
  return `${m}${p.line ? ' ' + p.line : ''} · ${s}`
}
export const VERIFY = {
  confirmed: { text: '已证实', cls: 'ok' },
  contradicted: { text: '被反驳', cls: 'bad' },
  unverified: { text: '未验证', cls: 'pend' },
}
export function impactText(c) {
  if (!c.impactDir || c.impactLevel === 'none') return ''
  const d = { upper: '利上盘', lower: '利下盘', neutral: '影响不明显' }[c.impactDir]
  const l = { high: '强', medium: '中', low: '弱' }[c.impactLevel] || ''
  return c.impactDir === 'neutral' ? d : `${d}${l ? ' · ' + l : ''}`
}
