import { request } from '@/utils/http'

const TTL_MS = 120000
const mem = new Map()

export function prefetchIntel(id) {
  if (!id) return Promise.resolve(null)
  const hit = mem.get(id)
  if (hit?.data && Date.now() - hit.ts < TTL_MS) return Promise.resolve(hit.data)
  if (hit?.promise) return hit.promise
  const p = request({
    url: `/api/predict/${encodeURIComponent(id)}/intel`,
    method: 'GET',
    timeout: 60000,
  })
    .then((data) => {
      mem.set(id, { ts: Date.now(), data, promise: null })
      return data
    })
    .catch((e) => {
      mem.delete(id)
      throw e
    })
  mem.set(id, { ts: 0, data: null, promise: p })
  return p
}
