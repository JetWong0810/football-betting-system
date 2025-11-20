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
  // 如果有token，先验证token是否有效
  if (userStore.token) {
    const isValid = await userStore.verifyToken();
    if (!isValid) {
      // token无效，已由verifyToken清除，继续初始化
    }
  }
  
  await configStore.bootstrap();
  await betStore.bootstrap();
});

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
