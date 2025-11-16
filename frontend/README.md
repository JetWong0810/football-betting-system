# 前端服务 (Frontend)

足球竞彩前端应用，基于 UniApp 框架开发的 H5 应用。

## 📋 功能

- 比赛列表展示
- 比赛详情查看
- 各类赔率展示（胜平负、让球、比分等）
- 投注记录管理
- 投注策略分析
- 数据统计图表

## 🏗️ 架构

```
┌──────────────────┐
│   浏览器          │
└────────┬─────────┘
         │
         ↓
┌──────────────────┐
│ Nginx (80/443)   │
│  静态文件服务     │
└────────┬─────────┘
         │
         │ API 请求
         ↓
┌──────────────────┐
│ API Service      │
│  (7001)          │
└──────────────────┘
```

## 📦 技术栈

- **框架**: UniApp (Vue 3)
- **构建工具**: Vite
- **状态管理**: Pinia
- **UI 组件**: uni-ui
- **HTTP 客户端**: uni.request
- **样式**: Sass/SCSS

## 🚀 部署指南

### 1. 本地开发环境

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev:h5

# 浏览器访问 http://localhost:5173
```

### 2. 本地构建

由于 guiyun 服务器配置较低（1核1G），建议在本地构建：

```bash
# 构建 H5 生产版本
npm run build:h5

# 构建产物位于 dist/build/h5/
```

### 3. 部署到服务器

**方式一：使用 rsync（推荐）**

```bash
# 从本地上传到 guiyun 服务器
cd /path/to/football-betting-system/frontend
rsync -avz dist/build/h5/ guiyun:/opt/football-betting-system/frontend/dist/
```

**方式二：在服务器上构建**

如果服务器配置足够：

```bash
# 在 guiyun 服务器上
cd /opt/football-betting-system/frontend
npm install
npm run build:h5
```

### 4. 配置 Nginx

创建配置文件 `/etc/nginx/sites-available/www.jetwong.top`:

```nginx
server {
    listen 80;
    server_name www.jetwong.top jetwong.top;

    access_log /var/log/nginx/www.jetwong.top.access.log;
    error_log /var/log/nginx/www.jetwong.top.error.log;

    # 前端静态文件
    root /opt/football-betting-system/frontend/dist;
    index index.html;

    # H5 应用路由
    location / {
        try_files $uri $uri/ @fallback;
    }

    location @fallback {
        rewrite ^.*$ /index.html break;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/x-javascript application/xml+rss application/json;
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/www.jetwong.top /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 📝 配置说明

### 环境变量

创建 `.env.production` 文件：

```env
# 生产环境 API 地址
VITE_API_BASE_URL=http://api.football.jetwong.top
```

### API 配置

编辑 `src/utils/http.js`：

```javascript
const getBaseURL = () => {
  // H5 环境使用环境变量或默认值
  return import.meta.env.VITE_API_BASE_URL || 'http://api.football.jetwong.top'
}
```

## 🔧 开发指南

### 项目结构

```
frontend/
├── src/
│   ├── components/          # 组件
│   │   ├── BetForm.vue     # 投注表单
│   │   ├── ChartPie.vue    # 饼图
│   │   └── ...
│   ├── pages/              # 页面
│   │   ├── home/           # 首页
│   │   ├── matches/        # 比赛页面
│   │   ├── analysis/       # 分析页面
│   │   ├── record/         # 记录页面
│   │   └── settings/       # 设置页面
│   ├── stores/             # 状态管理
│   │   └── matchStore.js   # 比赛数据状态
│   ├── utils/              # 工具函数
│   │   ├── http.js         # HTTP 请求封装
│   │   └── formatters.js   # 格式化函数
│   ├── static/             # 静态资源
│   ├── App.vue             # 根组件
│   ├── main.js             # 入口文件
│   ├── pages.json          # 页面配置
│   └── manifest.json       # 应用配置
├── dist/                   # 构建产物
├── package.json
├── vite.config.js
└── README.md
```

### 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/pages/home/home` | 首页 | 数据统计概览 |
| `/pages/matches/list` | 比赛列表 | 当前在售比赛 |
| `/pages/matches/plays` | 比赛详情 | 赔率详情 |
| `/pages/record/record` | 投注记录 | 历史记录 |
| `/pages/analysis/analysis` | 数据分析 | 投注分析 |
| `/pages/strategy/strategy` | 投注策略 | 策略计算 |
| `/pages/settings/settings` | 设置 | 应用设置 |

### 添加新页面

1. 在 `src/pages/` 创建新目录和 `.vue` 文件
2. 在 `src/pages.json` 中注册路由
3. 如果是 tabBar 页面，在 `tabBar` 配置中添加

### 状态管理

使用 Pinia 进行状态管理：

```javascript
// stores/matchStore.js
import { defineStore } from 'pinia'

export const useMatchStore = defineStore('match', {
  state: () => ({
    matches: [],
    loading: false
  }),
  actions: {
    async fetchMatches() {
      // 获取比赛数据
    }
  }
})
```

### API 调用

```javascript
import { request } from '@/utils/http'

// 获取比赛列表
const matches = await request({
  url: '/api/matches',
  method: 'GET',
  data: {
    page: 1,
    page_size: 20
  }
})
```

## 🔄 更新部署流程

当前端代码有更新时：

```bash
# 1. 本地拉取最新代码
cd /path/to/football-betting-system
git pull

# 2. 进入前端目录
cd frontend

# 3. 安装依赖（如果有变化）
npm install

# 4. 本地构建
npm run build:h5

# 5. 上传到服务器
rsync -avz dist/build/h5/ guiyun:/opt/football-betting-system/frontend/dist/

# 6. 无需重启，静态文件直接生效
```

## 🐛 故障排查

### 问题 1：页面无法访问

检查：
```bash
# Nginx 状态
sudo systemctl status nginx

# Nginx 配置
sudo nginx -t

# 文件权限
ls -la /opt/football-betting-system/frontend/dist/
```

### 问题 2：API 请求失败

检查：
```bash
# 浏览器控制台查看错误信息
# F12 -> Network

# 检查 API 服务状态
curl http://api.football.jetwong.top/api/health

# 检查 CORS 配置
```

常见原因：
- API 服务未启动
- API 地址配置错误
- CORS 配置问题
- 网络连接问题

### 问题 3：构建失败

```bash
# 清理缓存
rm -rf node_modules
rm package-lock.json
npm install

# 检查 Node 版本
node -v  # 建议 16+

# 查看详细错误
npm run build:h5 --verbose
```

## 📊 性能优化

### 1. 图片优化

- 使用 WebP 格式
- 压缩图片大小
- 使用 CDN

### 2. 代码分割

Vite 自动进行代码分割，无需额外配置

### 3. 缓存策略

Nginx 已配置静态资源缓存 30 天

### 4. 压缩

Nginx 已启用 Gzip 压缩

## 🧪 测试

### 单元测试

```bash
npm run test:unit
```

### E2E 测试

```bash
npm run test:e2e
```

### 构建测试

```bash
# 本地预览构建结果
npm run build:h5
npm run preview
```

## 📱 多端支持

虽然当前只部署 H5 版本，但 UniApp 支持多端：

```bash
# H5
npm run build:h5

# 微信小程序
npm run build:mp-weixin

# APP
npm run build:app

# 其他平台
npm run build:mp-alipay
npm run build:mp-baidu
```

## 🔒 安全建议

1. **HTTPS**
```bash
sudo certbot --nginx -d www.jetwong.top -d jetwong.top
```

2. **CSP 头**
在 Nginx 中添加：
```nginx
add_header Content-Security-Policy "default-src 'self' http://api.football.jetwong.top";
```

3. **防止点击劫持**
```nginx
add_header X-Frame-Options "SAMEORIGIN";
```

## 📞 相关文档

- [API 服务文档](../api-service/README.md)
- [抓取服务文档](../scraper-service/README.md)
- [UniApp 官方文档](https://uniapp.dcloud.net.cn/)
- [Vite 文档](https://vitejs.dev/)

