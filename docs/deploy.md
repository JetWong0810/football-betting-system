# 部署指南

本项目所有服务通过 Docker 部署在内网服务器 (ssh mysql-backup)，通过 SSH 隧道经由外网 VPS 暴露到公网。

## 架构

```
用户浏览器 → https://fc.jetwong.top
       ↓
VPS (gouyun) nginx :443 → proxy_pass 127.0.0.1:5002
       ↓ SSH 反向隧道 (autossh, systemd: football-tunnel)
内网 (mysql-backup) :8088 nginx (football-frontend 容器)
       ├── /         → 静态文件 (Vue H5)
       ├── /api/     → football-api:7001
       └── /static/  → football-api:7001
                          ↓
                   football-mysql:3306 (对外 :3321)
                          ↑
                   football-scraper (每10分钟同步竞彩数据)
```

## 服务信息

| 服务 | 容器名 | 端口 |
|------|--------|------|
| MySQL 8.0 | football-mysql | 3321 |
| API (FastAPI) | football-api | 7001 |
| Scraper | football-scraper | 内部 |
| Frontend (Nginx) | football-frontend | 8088 |

## 访问地址

| 环境 | 地址 |
|------|------|
| 公网 | https://fc.jetwong.top |
| 内网前端 | http://mysql-backup:8088 |
| 内网 API | http://mysql-backup:7001/docs |
| 数据库 | mysql-backup:3321 (见 deploy/.env) |

## 一键部署

```bash
bash deploy/deploy-remote.sh
```

脚本会：打包源码 → rsync 到服务器 → docker-compose up -d --build → 验证。

## 单服务更新

```bash
# 前端
rsync -az --exclude='node_modules' --exclude='dist' frontend/ mysql-backup:/opt/football-betting-system/frontend/
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build frontend"

# API
rsync -az --exclude='__pycache__' --exclude='.env' api-service/ mysql-backup:/opt/football-betting-system/api-service/
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build api"

# Scraper
rsync -az --exclude='__pycache__' --exclude='.env' scraper-service/ mysql-backup:/opt/football-betting-system/scraper-service/
ssh mysql-backup "cd /opt/football-betting-system && docker-compose up -d --build scraper"
```

## 从 GitHub 更新

```bash
ssh mysql-backup "cd /opt/football-betting-system && git pull origin main && cd deploy && docker-compose up -d --build"
```

## 服务管理

```bash
# 状态
ssh mysql-backup "cd /opt/football-betting-system/deploy && docker-compose ps"

# 日志
ssh mysql-backup "docker logs football-api --tail 50"
ssh mysql-backup "docker logs football-scraper --tail 20"
ssh mysql-backup "cd /opt/football-betting-system/deploy && docker-compose logs -f"

# 重启
ssh mysql-backup "cd /opt/football-betting-system/deploy && docker-compose restart"

# 停止
ssh mysql-backup "cd /opt/football-betting-system/deploy && docker-compose down"
```

## SSH 隧道管理

```bash
# 状态
ssh mysql-backup "systemctl status football-tunnel"

# 重启（公网无法访问时）
ssh mysql-backup "systemctl restart football-tunnel"

# 验证（VPS 端）
ssh gouyun "ss -tlnp | grep 5002"
```

服务文件: `/etc/systemd/system/football-tunnel.service`

## 本地开发

```bash
# 一键启动（API + Frontend dev server，连接远程数据库）
./start-local.sh

# 停止
./start-local.sh --stop

# 状态
./start-local.sh --status
```

本地访问:
- 前端: http://localhost:5173 (Vite 热更新)
- API: http://localhost:7001
- API 文档: http://localhost:7001/docs

环境要求:
- Python 3.9+
- Node.js 14+
- 能访问内网 mysql-backup (数据库)

## 端口分配

选择原则：避开 mysql-backup 上已有服务端口 (3316-3320, 80, 8001, 8081, 8082)。

| 端口 | 服务 |
|------|------|
| 3321 | football-mysql |
| 7001 | football-api |
| 8088 | football-frontend |
| 5002 | SSH 隧道 (VPS 端) |

## 故障排查

### 公网无法访问
```bash
ssh mysql-backup "systemctl status football-tunnel"  # 隧道断了？
ssh gouyun "ss -tlnp | grep 5002"                    # VPS 端口在监听？
ssh mysql-backup "docker ps --filter 'name=football-'"  # 容器在运行？
```

### API 返回 500
```bash
ssh mysql-backup "docker logs football-api --tail 30"
ssh mysql-backup "docker exec football-mysql mysqladmin ping -u root -p\$MYSQL_ROOT_PASSWORD"
```

### 前端接口 404
确认 `frontend/src/utils/http.js` 中 H5 生产环境 `getBaseURL()` 返回空字符串（相对路径）。

### 数据不更新
```bash
ssh mysql-backup "docker logs football-scraper --tail 20"
```

## 关键文件

```
deploy/
├── docker-compose.yml          # 容器编排 (v2.4)
├── deploy-remote.sh            # 部署脚本
├── init-sql/01_schema.sql      # 数据库初始化
├── api-service/Dockerfile
├── scraper-service/Dockerfile
├── scraper-service/entrypoint.py
├── frontend/Dockerfile
└── frontend/nginx.conf

# 服务器上
/etc/systemd/system/football-tunnel.service  # 隧道服务 (mysql-backup)
/etc/nginx/sites-enabled/fc.jetwong.top      # VPS nginx
/etc/nginx/ssl/fc.jetwong.top_*.pem          # SSL 证书
```
