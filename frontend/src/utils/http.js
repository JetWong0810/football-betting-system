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

// 是否正在处理401错误，避免重复跳转
let isHandling401 = false;

/**
 * 处理401错误，清除token并跳转到登录页
 */
function handle401Error() {
  if (isHandling401) {
    return;
  }
  isHandling401 = true;

  // 清除本地存储的token和用户信息
  uni.removeStorageSync('token');
  uni.removeStorageSync('user');

  // 清除userStore中的状态
  try {
    // 使用动态import避免循环依赖
    import('@/stores/userStore').then(({ useUserStore }) => {
      const userStore = useUserStore();
      userStore.token = '';
      userStore.user = null;
    }).catch((e) => {
      console.error('清除用户状态失败:', e);
    });
  } catch (e) {
    console.error('清除用户状态失败:', e);
  }

  // 获取当前页面路径
  const pages = getCurrentPages();
  const currentPage = pages[pages.length - 1];
  const currentPath = '/' + (currentPage?.route || '');

  // 排除登录相关页面，避免重复跳转
  const authPages = ['/pages/auth/login', '/pages/auth/register', '/pages/auth/wechat-login'];
  if (authPages.includes(currentPath)) {
    isHandling401 = false;
    return;
  }

  // 根据环境跳转到不同的登录页面
  // #ifdef MP-WEIXIN
  uni.redirectTo({
    url: '/pages/auth/wechat-login',
    fail: () => {
      isHandling401 = false;
    },
    complete: () => {
      setTimeout(() => {
        isHandling401 = false;
      }, 1000);
    }
  });
  // #endif

  // #ifndef MP-WEIXIN
  uni.redirectTo({
    url: '/pages/auth/login',
    fail: () => {
      isHandling401 = false;
    },
    complete: () => {
      setTimeout(() => {
        isHandling401 = false;
      }, 1000);
    }
  });
  // #endif
}

export function request(options) {
  return new Promise((resolve, reject) => {
    // 自动添加BASE_URL前缀
    let url = options.url;
    if (url && !url.startsWith("http")) {
      url = BASE_URL + url;
    }

    // 自动添加认证token（如果存在且未手动指定）
    const headers = options.header || options.headers || {};
    if (!headers['Authorization'] && !headers['authorization']) {
      const token = uni.getStorageSync('token');
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    uni.request({
      timeout: options.timeout || 15000,
      ...options,
      url,
      header: headers,
      success: (res) => {
        const status = res.statusCode || 0;
        if (status >= 200 && status < 300) {
          resolve(res.data);
        } else if (status === 401) {
          // 401错误：token无效或过期
          handle401Error();
          const message = res.data?.detail || "登录已过期，请重新登录";
          reject({
            statusCode: status,
            data: res.data,
            message,
          });
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
