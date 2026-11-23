/**
 * 单场 AI 聊天: 接口封装 + SSE 流式读取(H5 fetch)。
 */
import { BASE_URL, request } from '@/utils/http'

function authHeaders() {
  const token = uni.getStorageSync('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function fetchHistory(matchId) {
  return request({ url: `/api/predict/${encodeURIComponent(matchId)}/chat`, timeout: 20000 })
}

export function fetchContext(matchId) {
  return request({ url: `/api/predict/${encodeURIComponent(matchId)}/chat/context`, timeout: 20000 })
}

export function clearHistory(matchId) {
  return request({ url: `/api/predict/${encodeURIComponent(matchId)}/chat`, method: 'DELETE' })
}

/**
 * 发送一条消息并流式接收事件。
 * @param {string} matchId
 * @param {{message:string, images:Array, web:boolean}} payload
 * @param {(ev:Object)=>void} onEvent  事件: status/delta/sources/verdict/notice/done/error
 * @param {AbortSignal} signal
 */
export async function streamChat(matchId, payload, onEvent, signal, path) {
  const resp = await fetch(`${BASE_URL}${path || `/api/predict/${encodeURIComponent(matchId)}/chat`}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload || {}),
    signal,
  })
  if (!resp.ok) {
    let detail = ''
    try {
      const d = (await resp.json()).detail
      // 422 校验错误的 detail 是数组(如消息超长),不能直接当字符串
      detail = typeof d === 'string' ? d : (Array.isArray(d) ? '消息内容不符合要求(可能过长)' : '')
    } catch (e) { /* ignore */ }
    if (!detail && resp.status === 413) detail = '图片太大,请减少图片数量或换小一点的图'
    if (!detail && (resp.status === 502 || resp.status === 504)) detail = '服务响应超时,请稍后重试'
    const err = new Error(detail || `请求失败(${resp.status})`)
    err.statusCode = resp.status
    throw err
  }
  if (!resp.body) throw new Error('当前浏览器不支持流式响应')
  const reader = resp.body.getReader()
  const dec = new TextDecoder('utf-8')
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      try { onEvent(JSON.parse(line.slice(5).trim())) } catch (e) { /* 忽略坏帧 */ }
    }
  }
}

/** H5: 选图 -> 压缩(长边<=1280, JPEG 0.82) -> 返回 {media_type, data(base64), preview} */
export function compressImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('读取图片失败'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('图片解析失败'))
      img.onload = () => {
        const MAX = 1280
        const scale = Math.min(1, MAX / Math.max(img.width, img.height))
        const w = Math.round(img.width * scale)
        const h = Math.round(img.height * scale)
        const canvas = document.createElement('canvas')
        canvas.width = w
        canvas.height = h
        canvas.getContext('2d').drawImage(img, 0, 0, w, h)
        const url = canvas.toDataURL('image/jpeg', 0.82)
        resolve({ media_type: 'image/jpeg', data: url.split(',')[1], preview: url })
      }
      img.src = reader.result
    }
    reader.readAsDataURL(file)
  })
}
