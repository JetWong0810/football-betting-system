# 足球竞彩投注追踪系统

一个完整的足球竞彩数据抓取、分析和投注管理系统，采用分布式架构部署。

## 📋 项目概述

本项目由三个独立的子服务组成，分别部署在不同的服务器上：

1. **抓取服务 (Scraper Service)** - 部署在 `mysql-backup` 服务器
2. **后端 API 服务 (API Service)** - 部署在 `guiyun` 服务器
3. **前端服务 (Frontend)** - 部署在 `guiyun` 服务器

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────┐
│              用户浏览器                           │
└─────────────────────────────────────────────────┘
                    │
                    ↓
        https://www.jetwong.top
                    │
┌─────────────────────────────────────────────────┐
│         Frontend (guiyun 服务器)                 │
│         - UniApp H5 应用                         │
│         - Nginx 静态文件服务                      │
└─────────────────────────────────────────────────┘
                    │
                    ↓
      https://api.football.jetwong.top
                    │
┌─────────────────────────────────────────────────┐
│       API Service (guiyun 服务器)                │
│       - FastAPI 应用                             │
│       - MySQL 数据库                             │
│       - 端口: 7001                               │
└─────────────────────────────────────────────────┘
                    ↑
                    │ 每 10 分钟同步数据
                    │
┌─────────────────────────────────────────────────┐
│    Scraper Service (mysql-backup 服务器)         │
│    - 数据抓取脚本                                 │
│    - Docker 容器 (py39-dev)                      │
│    - 定时任务 (crontab)                          │
└─────────────────────────────────────────────────┘
                    │
                    ↓
         外部竞彩 API (中国体育彩票)
```

## 📁 目录结构

```
football-betting-system/
├── README.md                    # 项目主文档
├── QUICK_DEPLOY.md              # 快速部署指南
├── deploy.sh                    # 一键部署脚本
├── scraper-service/             # 抓取服务
│   ├── README.md               # 服务说明
│   ├── main.py                 # 主程序
│   ├── database.py             # 数据库操作
│   ├── repository.py           # 数据仓库
│   ├── scraper/                # 抓取模块
│   └── requirements.txt        # Python 依赖
├── api-service/                # API 服务
│   ├── README.md               # 服务说明
│   ├── main.py                 # FastAPI 应用
│   ├── database.py             # 数据库操作
│   ├── repository.py           # 数据仓库
│   ├── auth.py                 # 认证模块
│   └── requirements.txt        # Python 依赖
└── frontend/                   # 前端服务
    ├── README.md               # 服务说明
    ├── package.json            # NPM 配置
    ├── src/                    # 源代码
    │   ├── pages/              # 页面组件
    │   ├── components/         # 可复用组件
    │   ├── stores/             # 状态管理
    │   └── utils/              # 工具函数
    └── dist/                   # 构建产物
```

## 🚀 快速开始

### 方式一：一键部署（推荐）

使用一键部署脚本快速部署所有服务：

```bash
git clone <repository-url>
cd football-betting-system

# 完整部署（所有服务）
./deploy.sh

# 或单独部署某个服务
./deploy.sh --api-only        # 只部署 API 服务
./deploy.sh --scraper-only    # 只部署抓取服务
./deploy.sh --frontend-only   # 只部署前端服务
```

详细说明请查看：[快速部署指南](./QUICK_DEPLOY.md)

### 方式二：手动部署

#### 1. 克隆项目

```bash
git clone <repository-url>
cd football-betting-system
```

#### 2. 部署抓取服务（mysql-backup 服务器）

```bash
cd scraper-service
# 查看 README.md 了解详细部署步骤
```

#### 3. 部署 API 服务（guiyun 服务器）

```bash
cd api-service
# 查看 README.md 了解详细部署步骤
```

#### 4. 部署前端服务（guiyun 服务器）

```bash
cd frontend
# 查看 README.md 了解详细部署步骤
```

## 🌐 访问地址

- **前端应用**: https://www.jetwong.top
- **API 文档**: https://api.football.jetwong.top/docs
- **API 健康检查**: https://api.football.jetwong.top/api/health

## 📊 服务器配置

### guiyun 服务器 (103.140.229.232)

- **操作系统**: Ubuntu 24.04 LTS
- **Python**: 3.12.3
- **MySQL**: 8.0.43
- **Nginx**: 1.24.0
- **Node.js**: 22.15.0
- **服务**:
  - API Service (端口 7001)
  - Frontend (Nginx 80/443)
  - MySQL Database

### mysql-backup 服务器 (120.133.42.145)

- **操作系统**: CentOS/RHEL (旧版本)
- **Docker**: py39-dev 容器
- **Python**: 3.9 (在容器中)
- **服务**:
  - Scraper Service (定时任务)

## 🔧 技术栈

### 后端

- **框架**: FastAPI 0.121.2
- **ASGI 服务器**: Uvicorn 0.38.0
- **数据库**: MySQL 8.0.43
- **数据库驱动**: PyMySQL 1.1.2
- **HTTP 客户端**: httpx 0.28.1
- **任务调度**: APScheduler 3.11.1

### 前端

- **框架**: UniApp (Vue 3)
- **构建工具**: Vite
- **状态管理**: Pinia
- **UI 组件**: uni-ui

### 基础设施

- **反向代理**: Nginx
- **进程管理**: Systemd
- **容器化**: Docker
- **定时任务**: Crontab

## 💻 本地运行指南

### 环境要求

- Python 3.9+
- Node.js 16+
- MySQL 8.0+

### 快速启动（3 步）

#### 1. 数据库准备

```bash
# 启动 MySQL 服务
# macOS: brew services start mysql
# Linux: sudo systemctl start mysql

# 创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS football_betting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 导入表结构
mysql -u root -p football_betting < api-service/schema_mysql.sql
```

#### 2. 启动 API 服务

```bash
cd api-service

# 安装依赖
pip3 install -r requirements.txt

# 配置数据库连接（修改为你的 MySQL 密码）
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=football_betting

# 启动服务
python3 main.py
```

访问 http://localhost:7001/docs 查看 API 文档

#### 3. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev:h5
```

访问 http://localhost:5173

### 可选：本地运行抓取服务

```bash
cd scraper-service

# 安装依赖
pip3 install -r requirements.txt

# 配置环境变量（连接本地数据库）
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=football_betting

# 手动执行一次抓取
python3 main.py
```

### 📝 开发指南

详见各子服务的 README.md：

- [抓取服务开发指南](./scraper-service/README.md)
- [API 服务开发指南](./api-service/README.md)
- [前端开发指南](./frontend/README.md)

## 📖 文档

- [快速部署指南](./QUICK_DEPLOY.md) - 一键部署说明
- 各服务详细说明请查看对应目录下的 README.md

## 🔒 安全建议

1. ✅ 修改数据库默认密码
2. ✅ 配置防火墙规则
3. ⚠️ 配置 HTTPS（推荐）
4. ⚠️ 定期备份数据库
5. ⚠️ 监控服务器资源

## 📞 联系方式

- 开发者: jetwong
- 项目地址: https://github.com/JetWong0810/football-betting-system
