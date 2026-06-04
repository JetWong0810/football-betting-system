# 快速部署指南

本项目所有服务通过 Docker 部署在内网服务器 (mysql-backup / 10.130.130.139)，通过 SSH 隧道经由外网 VPS 暴露到公网。

## 前置条件

1. 本地已配置 SSH 免密登录：`ssh mysql-backup` 和 `ssh gouyun`
2. 目标服务器已安装 Docker 和 docker-compose
3. SSH 隧道服务已启动（首次部署时自动配置）

## 一键部署

```bash
# 从项目根目录执行，自动打包、同步、构建、启动所有服务
bash deploy/deploy-remote.sh
```

部署脚本会：
1. 打包 api-service、scraper-service、frontend 源码
2. rsync 到 mysql-backup:/opt/football-betting-system/
3. 执行 `docker-compose up -d --build`
4. 验证所有容器运行状态

## 访问地址

| 环境 | 地址 |
|------|------|
| 公网前端 | https://fc.jetwong.top |
| 公网 API | https://fc.jetwong.top/api/health |
| 内网前端 | http://10.130.130.139:8088 |
| 内网 API | http://10.130.130.139:7001/docs |
| 数据库 | 10.130.130.139:3321 (root/football_betting_2024) |

## 只更新某个服务

```bash
# 只重新构建前端（代码修改后）
rsync -az --exclude='node_modules' --exclude='dist' frontend/ mysql-backup:/opt/football-betting-system/frontend/
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build frontend"

# 只重新构建 API
rsync -az --exclude='__pycache__' --exclude='.env' api-service/ mysql-backup:/opt/football-betting-system/api-service/
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build api"

# 只重新构建 Scraper
rsync -az --exclude='__pycache__' --exclude='.env' scraper-service/ mysql-backup:/opt/football-betting-system/scraper-service/
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build scraper"
```

## 服务管理

```bash
# 查看容器状态
ssh mysql-backup "cd /opt/football-betting-system && docker-compose ps"

# 查看日志
ssh mysql-backup "cd /opt/football-betting-system && docker-compose logs -f"
ssh mysql-backup "docker logs football-api --tail 50"
ssh mysql-backup "docker logs football-scraper --tail 20"

# 重启所有服务
ssh mysql-backup "cd /opt/football-betting-system && docker-compose restart"

# 停止所有服务
ssh mysql-backup "cd /opt/football-betting-system && docker-compose down"

# 重启并重新构建（代码更新后）
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build"
```

## SSH 隧道管理

公网访问依赖 SSH 反向隧道（mysql-backup → VPS），由 systemd 管理：

```bash
# 查看隧道状态
ssh mysql-backup "systemctl status football-tunnel"

# 重启隧道（如果公网访问断了）
ssh mysql-backup "systemctl restart football-tunnel"

# 验证隧道（在 VPS 端检查）
ssh gouyun "ss -tlnp | grep 5002"
```

## 本地开发

```bash
# 启动本地前后端（连接远程数据库）
./start-local.sh

# 停止
./start-local.sh --stop

# 本地访问
# 前端: http://localhost:5173
# API:  http://localhost:7001
# Docs: http://localhost:7001/docs
```

## 故障排查

### 公网无法访问

```bash
# Step 1: 检查隧道
ssh mysql-backup "systemctl status football-tunnel"

# Step 2: 检查 VPS 端口
ssh gouyun "ss -tlnp | grep 5002"

# Step 3: 检查容器
ssh mysql-backup "docker ps --filter 'name=football-'"

# Step 4: 重启隧道
ssh mysql-backup "systemctl restart football-tunnel"
```

### API 返回 500

```bash
ssh mysql-backup "docker logs football-api --tail 30"
# 通常是数据库连接问题，检查 MySQL 容器是否健康
ssh mysql-backup "docker exec football-mysql mysqladmin ping -u root -pfootball_betting_2024"
```

### 前端接口 404

确认前端代码中 `http.js` 的 `getBaseURL()` 在 H5 生产环境返回空字符串（使用相对路径 `/api/xxx`），而非硬编码域名。

### 数据不更新

```bash
ssh mysql-backup "docker logs football-scraper --tail 20"
# 正常应看到 "同步完成 - 比赛数: X, 赔率数: Y"
# 如果报错，可能是外网 API 不可达
```

## 架构图

```
用户浏览器
    ↓ HTTPS
fc.jetwong.top (DNS → VPS 38.147.187.103)
    ↓
VPS nginx :443 → proxy_pass 127.0.0.1:5002
    ↓ SSH 反向隧道 (autossh systemd)
内网 10.130.130.139:8088 (football-frontend 容器)
    ├── /         → 静态文件 (Vue H5)
    ├── /api/     → football-api:7001
    └── /static/  → football-api:7001
                          ↓
                   football-mysql:3306 (对外 :3321)
                          ↑
                   football-scraper (每10分钟同步竞彩数据)
```

## 端口分配

| 端口 | 服务 | 说明 |
|------|------|------|
| 3321 | football-mysql | 避开已有 3316-3320 |
| 7001 | football-api | FastAPI |
| 8088 | football-frontend | Nginx + 前端静态文件 |
| 5002 | SSH 隧道 (VPS端) | autossh 反向端口 |

## 关键文件

```
deploy/
├── docker-compose.yml      # 容器编排 (v2.4)
├── deploy-remote.sh        # 一键部署脚本
├── init-sql/01_schema.sql  # 数据库初始化
├── api-service/Dockerfile
├── scraper-service/Dockerfile
├── scraper-service/entrypoint.py  # 循环运行包装
├── frontend/Dockerfile     # Node 构建 + nginx 静态服务
└── frontend/nginx.conf     # API 代理 + SPA fallback

# 隧道服务 (mysql-backup)
/etc/systemd/system/football-tunnel.service

# VPS nginx
/etc/nginx/sites-enabled/fc.jetwong.top
/etc/nginx/ssl/fc.jetwong.top_chain.pem
/etc/nginx/ssl/fc.jetwong.top_key.key
```
