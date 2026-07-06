import { request } from '@/utils/http'

// 置信度校准：把模型的规则置信度（35-92）映射为更接近真实命中率的概率
// 数据来源：/api/review-stats 按置信度分桶的历史命中率
// 样本不足时对原始置信度打折扣（已知未校准、偏乐观），样本充足时按桶命中率加权

const CACHE_KEY = 'frbt-calibration'
const TTL = 3600 * 1000 // 1 小时

let memCache = null

/**
 * 拉取并缓存校准数据（命中率分桶）。
 * 优先用内存缓存，其次本地存储，最后发请求。
 */
export async function loadCalibration() {
  if (memCache && Date.now() - memCache.fetchedAt < TTL) return memCache
  try {
    const stored = uni.getStorageSync(CACHE_KEY)
    if (stored && Date.now() - stored.fetchedAt < TTL) {
      memCache = stored
      return stored
    }
  } catch (e) {
    // storage 读取失败，忽略
  }

  try {
    const data = await request({
      url: '/api/review-stats?days=9999&predict_type=all',
      method: 'GET'
    })
    const cal = { fetchedAt: Date.now(), data }
    memCache = cal
    try {
      uni.setStorageSync(CACHE_KEY, cal)
    } catch (e) {
      // storage 写入失败，忽略
    }
    return cal
  } catch (e) {
    // 拉取失败：返回已有缓存或空，调用方会走"无校准数据"分支
    return memCache || { data: null }
  }
}

function findBand(confidence, bands) {
  if (!bands || !Array.isArray(bands)) return null
  return bands.find((b) => {
    if (b.band === '60+') return confidence >= 60
    if (b.band === '50-59') return confidence >= 50 && confidence < 60
    if (b.band === '40-49') return confidence >= 40 && confidence < 50
    if (b.band === '35-39') return confidence >= 35 && confidence < 40
    return false
  })
}

/**
 * 把模型置信度校准为概率。
 * @param {number} confidence 35-92 的规则置信度
 * @param {{data?: object}} calibration loadCalibration() 的返回
 * @returns {number} 0-1 的校准概率
 */
export function calibrateProbability(confidence, calibration) {
  const raw = Math.min(Math.max(confidence / 100, 0), 1)
  const UNCERTAIN_DISCOUNT = 0.85 // 无足够样本时，对原始置信度打85折

  if (!calibration || !calibration.data) {
    return Math.min(raw * UNCERTAIN_DISCOUNT, 0.95)
  }

  const band = findBand(confidence, calibration.data.byConfidence)
  // 样本不足（<5场）或无命中率：保守折扣
  if (!band || !band.total || band.total < 5 || band.hitRate == null) {
    return Math.min(raw * UNCERTAIN_DISCOUNT, 0.95)
  }

  // 样本越多越信任历史命中率：20场以上完全用历史，否则按比例混合
  const w = Math.min(1, band.total / 20)
  const calibrated = w * band.hitRate + (1 - w) * raw
  return Math.min(Math.max(calibrated, 0), 0.95)
}
