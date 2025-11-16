# 项目结构

## 📁 完整目录树

```
football-betting-system/
├── README.md                           # 项目主文档
├── .gitignore                          # Git 忽略配置
├── PROJECT_STRUCTURE.md                # 本文件
│
├── docs/                               # 文档目录
│   ├── deployment.md                  # 部署指南
│   ├── architecture.md                # 架构说明
│   └── troubleshooting.md             # 故障排查
│
├── scraper-service/                    # 抓取服务
│   ├── README.md                      # 服务说明
│   ├── main.py                        # 主程序入口
│   ├── database.py                    # 数据库操作
│   ├── repository.py                  # 数据仓库层
│   ├── settings.py                    # 配置管理
│   ├── requirements.txt               # Python 依赖
│   ├── schema_mysql.sql               # 数据库表结构
│   └── scraper/                       # 抓取模块
│       └── sporttery_service.py       # 竞彩API抓取
│
├── api-service/                        # API 服务
│   ├── README.md                      # 服务说明
│   ├── main.py                        # FastAPI 应用
│   ├── database.py                    # 数据库操作
│   ├── repository.py                  # 数据仓库层
│   ├── settings.py                    # 配置管理
│   ├── tasks.py                       # 后台任务
│   ├── requirements.txt               # Python 依赖
│   └── schema_mysql.sql               # 数据库表结构
│
└── frontend/                           # 前端服务
    ├── README.md                      # 服务说明
    ├── package.json                   # NPM 配置
    ├── vite.config.js                 # Vite 配置
    ├── index.html                     # HTML 入口
    ├── src/                           # 源代码
    │   ├── main.js                    # 应用入口
    │   ├── App.vue                    # 根组件
    │   ├── pages.json                 # 页面配置
    │   ├── manifest.json              # 应用配置
    │   ├── uni.scss                   # 全局样式
    │   ├── components/                # 组件目录
    │   │   ├── BetForm.vue
    │   │   ├── BetCart.vue
    │   │   ├── ChartPie.vue
    │   │   ├── ChartProfit.vue
    │   │   ├── StatCard.vue
    │   │   ├── FixedRatioCalc.vue
    │   │   ├── KellyCalc.vue
    │   │   └── StopLossAlert.vue
    │   ├── pages/                     # 页面目录
    │   │   ├── home/                  # 首页
    │   │   ├── matches/               # 比赛页面
    │   │   ├── analysis/              # 分析页面
    │   │   ├── record/                # 记录页面
    │   │   ├── strategy/              # 策略页面
    │   │   └── settings/              # 设置页面
    │   ├── stores/                    # 状态管理
    │   │   └── matchStore.js
    │   ├── utils/                     # 工具函数
    │   │   ├── http.js
    │   │   └── formatters.js
    │   └── static/                    # 静态资源
    │       └── tabbar/                # 底部导航图标
    └── dist/                          # 构建产物（生产环境）
```

## 📝 文件说明

### 根目录文件

- `README.md` - 项目主文档，包含项目概述、架构图、快速开始等
- `.gitignore` - Git 版本控制忽略配置
- `PROJECT_STRUCTURE.md` - 项目结构详细说明

### 文档目录 (docs/)

- `deployment.md` - 完整的部署指南，涵盖所有服务
- `architecture.md` - 系统架构设计文档
- `troubleshooting.md` - 常见问题和故障排查

### 抓取服务 (scraper-service/)

**核心文件**:
- `main.py` - 独立运行的数据抓取脚本，定时任务入口
- `database.py` - 数据库连接和初始化
- `repository.py` - 数据持久化操作
- `settings.py` - 配置加载（从 .env）
- `scraper/sporttery_service.py` - 竞彩 API 数据抓取和解析

**配置文件**:
- `requirements.txt` - Python 依赖列表
- `schema_mysql.sql` - MySQL 数据库表结构
- `.env` - 环境变量配置（需创建，参考 .env.example）

**部署位置**: mysql-backup 服务器的 Docker 容器中

### API 服务 (api-service/)

**核心文件**:
- `main.py` - FastAPI 应用，定义所有 API 接口
- `database.py` - 数据库连接管理
- `repository.py` - 数据查询封装
- `settings.py` - 配置管理
- `tasks.py` - 后台任务（已禁用）

**配置文件**:
- `requirements.txt` - Python 依赖列表
- `schema_mysql.sql` - 数据库表结构
- `.env` - 环境变量配置

**部署位置**: guiyun 服务器，通过 Systemd 管理

### 前端服务 (frontend/)

**入口文件**:
- `index.html` - HTML 入口
- `src/main.js` - JavaScript 入口
- `src/App.vue` - Vue 根组件

**配置文件**:
- `package.json` - NPM 依赖和脚本
- `vite.config.js` - Vite 构建配置
- `src/pages.json` - UniApp 页面路由配置
- `src/manifest.json` - UniApp 应用配置

**源代码**:
- `src/components/` - 可复用组件
- `src/pages/` - 页面组件
- `src/stores/` - Pinia 状态管理
- `src/utils/` - 工具函数
- `src/static/` - 静态资源

**构建产物**:
- `dist/` - 构建后的静态文件

**部署位置**: guiyun 服务器，通过 Nginx 提供静态文件服务

## 🔗 服务关系

```
Frontend (Nginx) → API Service (FastAPI) → MySQL Database
                                              ↑
                                              │
                              Scraper Service (Python)
```

## 🚀 快速导航

### 想要部署系统？
👉 查看 [`docs/deployment.md`](docs/deployment.md)

### 想要了解架构？
👉 查看 [`docs/architecture.md`](docs/architecture.md)

### 遇到问题？
👉 查看 [`docs/troubleshooting.md`](docs/troubleshooting.md)

### 开发前端？
👉 查看 [`frontend/README.md`](frontend/README.md)

### 开发 API？
👉 查看 [`api-service/README.md`](api-service/README.md)

### 修改抓取逻辑？
👉 查看 [`scraper-service/README.md`](scraper-service/README.md)

## 📊 代码统计

### Python 代码

- 抓取服务: ~500 行
- API 服务: ~600 行
- 共享模块: ~400 行

### 前端代码

- Vue 组件: ~2000 行
- JavaScript: ~500 行
- 样式文件: ~800 行

### 文档

- 总计: ~3000 行

## 🛠️ 技术栈总览

| 服务 | 语言/框架 | 主要依赖 |
|------|-----------|----------|
| 抓取服务 | Python 3.9 | httpx, pymysql |
| API 服务 | Python 3.12 | FastAPI, uvicorn, pymysql |
| 前端服务 | JavaScript | UniApp, Vue 3, Vite |
| 数据库 | MySQL 8.0 | - |
| Web 服务器 | Nginx 1.24 | - |

## 📦 依赖管理

### Python 依赖

所有 Python 服务使用 `requirements.txt`:

```
fastapi==0.121.2
uvicorn[standard]==0.38.0
httpx==0.28.1
pymysql==1.1.2
python-dotenv==1.2.1
apscheduler==3.11.1
cryptography==46.0.3
```

### Node.js 依赖

前端使用 `package.json` 管理，主要依赖：

- @dcloudio/uni-app
- vue (3.x)
- pinia
- vite

## 🔧 开发工具推荐

- **Python IDE**: PyCharm, VS Code
- **前端IDE**: VS Code, WebStorm
- **数据库工具**: DBeaver, MySQL Workbench
- **API 测试**: Postman, curl
- **版本控制**: Git

## 📞 相关链接

- [项目主页](README.md)
- [部署指南](docs/deployment.md)
- [架构文档](docs/architecture.md)
- [故障排查](docs/troubleshooting.md)
