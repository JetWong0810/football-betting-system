<script setup>
import { onLaunch, onShow } from "@dcloudio/uni-app";
import { useBetStore } from "@/stores/betStore";
import { useConfigStore } from "@/stores/configStore";
import { useUserStore } from "@/stores/userStore";
import { useAuthGuard, AUTH_PAGES, isAuthRequired, isWeChatMiniProgram } from "@/utils/auth";

const betStore = useBetStore();
const configStore = useConfigStore();
const userStore = useUserStore();

onLaunch(async () => {
  // #ifdef MP-WEIXIN
  // 在微信小程序环境，先尝试自动登录
  await tryAutoLogin();
  // #endif
  
  // #ifndef MP-WEIXIN
  // 非微信小程序环境，只验证已有token
  if (userStore.token) {
    const isValid = await userStore.verifyToken();
    if (!isValid) {
      // token无效，已由verifyToken清除，继续初始化
    }
  }
  // #endif
  
  await configStore.bootstrap();
  await betStore.bootstrap();
});

// 尝试自动登录（仅微信小程序）
async function tryAutoLogin() {
  // #ifdef MP-WEIXIN
  try {
    // 如果有token，先验证
    if (userStore.token) {
      const isValid = await userStore.verifyToken();
      if (isValid) {
        // token有效，无需重新登录
        console.log("Token 验证成功，自动登录");
        userStore.autoLoginChecked = true;
        return;
      }
    }
    
    // 尝试静默登录
    await userStore.wechatSilentLogin();
    console.log("静默登录成功");
  } catch (error) {
    // 用户未注册或其他错误，需要手动登录
    if (error.code === "USER_NOT_REGISTERED") {
      console.log("用户未注册，需要手动授权");
    } else {
      console.error("自动登录失败:", error);
    }
  } finally {
    // 标记自动登录检查已完成
    userStore.autoLoginChecked = true;
  }
  // #endif
}

onShow(() => {
  betStore.recalculateSnapshots();
});

// 全局路由守卫
uni.addInterceptor('navigateTo', {
  invoke(args) {
    const url = args.url.split('?')[0];
    // 检查是否需要登录
    if (AUTH_PAGES.includes(url)) {
      // 访问登录页面时，如果已登录则跳转到首页
      if (userStore.isLoggedIn) {
        uni.switchTab({
          url: '/pages/home/home'
        });
        return false;
      }
    } else {
      // 检查是否需要登录
      if (isAuthRequired(url) && !userStore.isLoggedIn) {
        // 需要登录但未登录，跳转到登录页
        if (isWeChatMiniProgram()) {
          uni.redirectTo({
            url: '/pages/auth/wechat-login'
          });
        } else {
          uni.redirectTo({
            url: '/pages/auth/login'
          });
        }
        return false;
      }
    }
    return true;
  }
});

uni.addInterceptor('switchTab', {
  invoke(args) {
    const url = args.url;
    
    // 检查是否需要登录
    if (isAuthRequired(url) && !userStore.isLoggedIn) {
      // 需要登录但未登录，跳转到登录页
      if (isWeChatMiniProgram()) {
        uni.redirectTo({
          url: '/pages/auth/wechat-login'
        });
      } else {
        uni.redirectTo({
          url: '/pages/auth/login'
        });
      }
      return false;
    }
    return true;
  }
});
</script>

<style lang="scss">
@import "./uni.scss";

page {
  background-color: $frbt-bg;
  font-family: "Source Sans Pro", "Helvetica Neue", Arial, sans-serif;
  color: $frbt-text;
  padding-bottom: 0;
}
</style>
