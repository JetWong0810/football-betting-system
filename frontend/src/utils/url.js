/**
 * URL 工具函数 - 兼容小程序环境
 * 小程序环境不支持 URLSearchParams，需要手动构建查询字符串
 */

/**
 * 构建查询字符串
 * @param {Object|Array} params - 参数对象或键值对数组
 * @returns {string} 查询字符串（不包含 ?）
 * 
 * @example
 * buildQueryString({ page: 1, size: 20 }) // "page=1&size=20"
 * buildQueryString([['page', '1'], ['size', '20']]) // "page=1&size=20"
 */
export function buildQueryString(params) {
  if (!params) return '';
  
  const pairs = [];
  
  if (Array.isArray(params)) {
    // 如果是数组格式 [['key', 'value'], ...]
    params.forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
      }
    });
  } else if (typeof params === 'object') {
    // 如果是对象格式 { key: value, ... }
    Object.keys(params).forEach((key) => {
      const value = params[key];
      if (value !== null && value !== undefined) {
        pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
      }
    });
  }
  
  return pairs.join('&');
}

/**
 * URLSearchParams 的简单替代实现
 * 提供基本的 append 和 toString 方法
 */
export class URLSearchParamsPolyfill {
  constructor(init) {
    this.params = [];
    
    if (init) {
      if (typeof init === 'string') {
        // 解析查询字符串
        init.split('&').forEach((pair) => {
          const [key, value] = pair.split('=');
          if (key) {
            this.params.push([decodeURIComponent(key), value ? decodeURIComponent(value) : '']);
          }
        });
      } else if (Array.isArray(init)) {
        // 数组格式
        this.params = init.map(([key, value]) => [String(key), String(value)]);
      } else if (typeof init === 'object') {
        // 对象格式
        Object.keys(init).forEach((key) => {
          this.params.push([String(key), String(init[key])]);
        });
      }
    }
  }
  
  append(name, value) {
    this.params.push([String(name), String(value)]);
  }
  
  toString() {
    return this.params
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
      .join('&');
  }
  
  get(name) {
    const pair = this.params.find(([key]) => key === name);
    return pair ? pair[1] : null;
  }
  
  getAll(name) {
    return this.params
      .filter(([key]) => key === name)
      .map(([, value]) => value);
  }
  
  has(name) {
    return this.params.some(([key]) => key === name);
  }
  
  delete(name) {
    this.params = this.params.filter(([key]) => key !== name);
  }
  
  set(name, value) {
    this.delete(name);
    this.append(name, value);
  }
}

/**
 * 获取 URLSearchParams 的兼容实现
 * 在小程序环境中使用 polyfill，在浏览器环境中使用原生 API
 */
export function getURLSearchParams(init) {
  // 检查是否支持原生 URLSearchParams
  if (typeof URLSearchParams !== 'undefined') {
    return new URLSearchParams(init);
  }
  // 使用 polyfill
  return new URLSearchParamsPolyfill(init);
}

