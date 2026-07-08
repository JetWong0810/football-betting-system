# 足球竞彩投注追踪系统

足球竞彩数据抓取、分析和投注管理系统。

## 系统架构

```
用户 → https://fc.jetwong.top
       ↓
Cloudflare 边缘 → cloudflared 出站隧道 → 内网服务器 (mysql-backup)
       ↓
┌─────────────────────────────────────────────────────┐
│  Docker Compose (football-net)                      │
│                                                     │
│  frontend (:8088)  → nginx 静态 + /api/ 代理        │
│  api (:7001)       → FastAPI 后端                   │
│  scraper           → 每10分钟抓取竞彩数据            │
│  mysql (:3321)     → MySQL 8.0 数据库               │
└─────────────────────────────────────────────────────┘
```

## 快速开始

### 本地开发

```bash
# 一键启动 API + 前端开发服务器
./start-local.sh

# 访问
# 前端: http://localhost:5173
# API:  http://localhost:7001/docs
```

### 部署到服务器

```bash
bash deploy/deploy-remote.sh
```

详见 [部署文档](./docs/deploy.md)。

## 技术栈

| 层 | 技术 |
|------|------|
| 前端 | UniApp (Vue 3) + Vite + Pinia |
| 后端 | FastAPI + PyMySQL |
| 数据库 | MySQL 8.0 |
| 数据源 | 中国体育彩票 Sporttery API |
| 部署 | Docker Compose + Cloudflare Tunnel |

## 目录结构

```
├── api-service/          # FastAPI 后端
├── scraper-service/      # 数据抓取服务
├── frontend/             # UniApp H5/小程序前端
├── deploy/               # Docker 部署文件
│   ├── docker-compose.yml
│   ├── deploy-remote.sh
│   └── ...
├── docs/                 # 文档
│   ├── deploy.md              # 部署指南
│   ├── cloudflare-tunnel.md   # Cloudflare Tunnel 公网接入
│   └── ocr-feature.md         # OCR 功能说明
└── start-local.sh        # 本地开发启动脚本
```

## 文档

- [部署指南](./docs/deploy.md) — 服务器部署、管理、故障排查
- [Cloudflare Tunnel](./docs/cloudflare-tunnel.md) — 公网接入（替代旧 VPS 穿透方案）
- [OCR 功能](./docs/ocr-feature.md) — 投注截图识别功能说明
