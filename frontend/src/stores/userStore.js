import { defineStore } from "pinia";
import { request } from "@/utils/http";
import { useConfigStore } from "@/stores/configStore";
import { useBetStore } from "@/stores/betStore";

async function afterLoginSideEffects() {
  const configStore = useConfigStore();
  const betStore = useBetStore();
  await configStore.loadFromServer();
  await betStore.refreshBets();
}

export const useUserStore = defineStore("user", {
  state: () => ({
    token: uni.getStorageSync("token") || "",
    user: uni.getStorageSync("user") || null,
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
  },

  actions: {
    // 注册
    async register(data) {
      try {
        const res = await request({
          url: "/api/auth/register",
          method: "POST",
          data,
        });

        this.token = res.token;
        this.user = res.user;

        // 保存到本地存储
        uni.setStorageSync("token", res.token);
        uni.setStorageSync("user", res.user);

        // 注册后加载用户配置（会创建默认配置）和投注记录
        await afterLoginSideEffects();

        return res;
      } catch (error) {
        throw error;
      }
    },

    // 登录
    async login(data) {
      try {
        const res = await request({
          url: "/api/auth/login",
          method: "POST",
          data,
        });

        this.token = res.token;
        this.user = res.user;

        // 保存到本地存储
        uni.setStorageSync("token", res.token);
        uni.setStorageSync("user", res.user);

        // 登录后加载用户配置和投注记录
        await afterLoginSideEffects();

        return res;
      } catch (error) {
        throw error;
      }
    },

    // 微信登录
    async wechatLogin(data) {
      try {
        const res = await request({
          url: "/api/auth/wechat-login",
          method: "POST",
          data,
        });

        this.token = res.token;
        this.user = res.user;

        // 保存到本地存储
        uni.setStorageSync("token", res.token);
        uni.setStorageSync("user", res.user);

        // 登录后加载用户配置和投注记录
        await afterLoginSideEffects();

        return res;
      } catch (error) {
        throw error;
      }
    },

    // 微信小程序静默登录（仅用于已注册用户的自动登录）
    async wechatSilentLogin() {
      // #ifndef MP-WEIXIN
      throw new Error("仅支持在微信小程序环境中使用微信登录");
      // #endif

      // #ifdef MP-WEIXIN
      // 获取微信登录 code
      const loginRes = await new Promise((resolve, reject) => {
        uni.login({
          provider: "weixin",
          timeout: 10000,
          success: (res) => {
            if (res.code) {
              resolve(res);
            } else {
              reject(new Error(res.errMsg || "获取登录凭证失败"));
            }
          },
          fail: (err) => {
            reject(new Error(err?.errMsg || "获取登录凭证失败"));
          },
        });
      });

      try {
        const res = await request({
          url: "/api/auth/wechat-silent-login",
          method: "POST",
          data: {
            code: loginRes.code,
          },
        });

        this.token = res.token;
        this.user = res.user;

        // 保存到本地存储
        uni.setStorageSync("token", res.token);
        uni.setStorageSync("user", res.user);

        // 登录后加载用户配置和投注记录
        await afterLoginSideEffects();

        return res;
      } catch (error) {
        // 404 表示用户未注册
        if (error.statusCode === 404) {
          throw { code: "USER_NOT_REGISTERED", message: "用户未注册", originalError: error };
        }
        throw error;
      }
      // #endif
    },

    // 微信小程序一键登录（调用 uni.login 获取 code）
    async loginWithWeChatMiniProgram(options = {}) {
      // #ifndef MP-WEIXIN
      throw new Error("仅支持在微信小程序环境中使用微信登录");
      // #endif

      // #ifdef MP-WEIXIN
      const { requireProfile = true, providedNickname = "", avatarBase64 = null, avatarFileExt = "png" } = options;

      // 先同步触发 API，确保仍处于用户点击上下文
      const loginPromise = new Promise((resolve, reject) => {
        uni.login({
          provider: "weixin",
          onlyAuthorize: true,
          timeout: 10000,
          success: (res) => {
            if (res.code) {
              resolve(res);
            } else {
              reject(new Error(res.errMsg || "获取登录凭证失败"));
            }
          },
          fail: (err) => {
            reject(new Error(err?.errMsg || "获取登录凭证失败"));
          },
        });
      });

      const profilePromise = requireProfile
        ? new Promise((resolve, reject) => {
            uni.getUserProfile({
              desc: "用于完善会员资料",
              lang: "zh_CN",
              success: resolve,
              fail: reject,
            });
          })
        : Promise.resolve(null);

      const [loginRes, profile] = await Promise.all([loginPromise, profilePromise]);

      const payload = {
        code: loginRes.code,
      };

      if (profile) {
        const { rawData, signature, encryptedData, iv, userInfo } = profile;
        if (rawData) {
          payload.rawData = rawData;
          payload.raw_data = rawData;
        }
        if (signature) {
          payload.signature = signature;
        }
        if (encryptedData) {
          payload.encryptedData = encryptedData;
          payload.encrypted_data = encryptedData;
        }
        if (iv) {
          payload.iv = iv;
        }
        if (userInfo) {
          payload.userInfo = userInfo;
          payload.user_info = userInfo;
        }
      }

      if (providedNickname) {
        payload.providedNickname = providedNickname;
      }
      if (avatarBase64) {
        payload.avatarBase64 = avatarBase64;
        if (avatarFileExt) {
          payload.avatarFileExt = avatarFileExt;
        }
      }

      return this.wechatLogin(payload);
      // #endif
    },

    // 退出登录
    async logout() {
      this.token = "";
      this.user = null;

      // 清除本地存储
      uni.removeStorageSync("token");
      uni.removeStorageSync("user");

      // 清空用户相关的store数据
      // 清空投注记录
      const betStore = useBetStore();
      betStore.clearBets();

      const configStore = useConfigStore();
      configStore.loadFromLocal();
    },

    // 获取用户信息
    async fetchUserProfile() {
      if (!this.token) {
        return;
      }

      try {
        const res = await request({
          url: "/api/user/profile",
          method: "GET",
          header: {
            Authorization: `Bearer ${this.token}`,
          },
        });

        this.user = res;
        uni.setStorageSync("user", res);

        return res;
      } catch (error) {
        // Token失效，清除登录状态
        if (error.statusCode === 401) {
          this.logout();
        }
        throw error;
      }
    },

    // 更新用户资料
    async updateProfile(data) {
      try {
        await request({
          url: "/api/user/profile",
          method: "PUT",
          data,
          header: {
            Authorization: `Bearer ${this.token}`,
          },
        });

        // 重新获取用户信息
        await this.fetchUserProfile();
      } catch (error) {
        throw error;
      }
    },

    // 获取用户配置
    async fetchUserConfig() {
      if (!this.token) {
        return null;
      }

      try {
        const res = await request({
          url: "/api/user/config",
          method: "GET",
          header: {
            Authorization: `Bearer ${this.token}`,
          },
        });
        return res;
      } catch (error) {
        throw error;
      }
    },

    // 更新用户配置
    async updateConfig(data) {
      try {
        await request({
          url: "/api/user/config",
          method: "PUT",
          data,
          header: {
            Authorization: `Bearer ${this.token}`,
          },
        });
      } catch (error) {
        throw error;
      }
    },

    // 验证token是否有效
    async verifyToken() {
      if (!this.token) {
        return false;
      }

      try {
        const res = await request({
          url: "/api/auth/verify",
          method: "GET",
        });

        // 如果验证成功，更新用户信息
        if (res && res.user) {
          this.user = res.user;
          uni.setStorageSync("user", res.user);
        }

        return true;
      } catch (error) {
        // token无效，清除登录状态
        if (error.statusCode === 401) {
          this.logout();
        }
        return false;
      }
    },
  },
});
