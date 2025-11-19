// 根据环境配置API基础URL
const getBaseURL = () => {
  // #ifdef H5
  // H5 环境：优先使用环境变量，本地开发默认走 Vite 代理避免跨域
  const envBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (envBaseUrl) {
    return envBaseUrl;
  }
  if (import.meta.env.DEV) {
    return "/api";
  }
  return "https://api.football.jetwong.top";
  // #endif

  // #ifdef MP-WEIXIN
  // 微信小程序环境：使用生产环境API域名
  return "https://api.football.jetwong.top";
  // #endif

  // #ifndef H5 || MP-WEIXIN
  // 其他环境使用生产环境域名
  return "https://api.football.jetwong.top";
  // #endif
};

export const BASE_URL = getBaseURL();

export function request(options) {
  return new Promise((resolve, reject) => {
    // 自动添加BASE_URL前缀
    let url = options.url;
    if (url && !url.startsWith("http")) {
      url = BASE_URL + url;
    }

    uni.request({
      timeout: options.timeout || 15000,
      ...options,
      url,
      success: (res) => {
        const status = res.statusCode || 0;
        if (status >= 200 && status < 300) {
          resolve(res.data);
        } else {
          const message = res.data?.detail || res.errMsg || `请求失败(${status})`;
          reject({
            statusCode: status,
            data: res.data,
            message,
          });
        }
      },
      fail: (err) => {
        const message = err?.errMsg || "网络异常";
        reject({
          statusCode: 0,
          data: null,
          message,
        });
      },
    });
  });
}
