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
         http://www.jetwong.top
                    │
┌─────────────────────────────────────────────────┐
│         Frontend (guiyun 服务器)                 │
│         - UniApp H5 应用                         │
│         - Nginx 静态文件服务                      │
└─────────────────────────────────────────────────┘
                    │
                    ↓
      http://api.football.jetwong.top
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
├── README.md                    # 本文件
├── docs/                        # 文档目录
│   ├── deployment.md           # 部署文档
│   ├── architecture.md         # 架构说明
│   └── troubleshooting.md      # 故障排查
├── scraper-service/            # 抓取服务
│   ├── README.md
│   ├── requirements.txt
│   ├── main.py
│   └── ...
├── api-service/                # API 服务
│   ├── README.md
│   ├── requirements.txt
│   ├── main.py
│   └── ...
└── frontend/                   # 前端服务
    ├── README.md
    ├── package.json
    ├── src/
    └── ...
```

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd football-betting-system
```

### 2. 部署抓取服务（mysql-backup 服务器）

```bash
cd scraper-service
# 查看 README.md 了解详细部署步骤
```

### 3. 部署 API 服务（guiyun 服务器）

```bash
cd api-service
# 查看 README.md 了解详细部署步骤
```

### 4. 部署前端服务（guiyun 服务器）

```bash
cd frontend
# 查看 README.md 了解详细部署步骤
```

## 🌐 访问地址

- **前端应用**: http://www.jetwong.top
- **API 文档**: http://api.football.jetwong.top/docs
- **API 健康检查**: http://api.football.jetwong.top/api/health

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

## 📝 开发指南

### 环境要求

- Python 3.9+
- Node.js 16+
- MySQL 8.0+

### 本地开发

详见各子服务的 README.md：

- [抓取服务开发指南](./scraper-service/README.md)
- [API 服务开发指南](./api-service/README.md)
- [前端开发指南](./frontend/README.md)

## 📖 文档

- [部署文档](./docs/deployment.md) - 完整的部署流程
- [架构说明](./docs/architecture.md) - 系统架构设计
- [故障排查](./docs/troubleshooting.md) - 常见问题解决

## 🔒 安全建议

1. ✅ 修改数据库默认密码
2. ✅ 配置防火墙规则
3. ⚠️ 配置 HTTPS（推荐）
4. ⚠️ 定期备份数据库
5. ⚠️ 监控服务器资源

## 📞 联系方式

- 开发者: jetwong
- 项目地址: https://github.com/your-repo

## 📄 许可证

[MIT License](./LICENSE)
