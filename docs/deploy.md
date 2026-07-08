# 部署指南

本项目所有服务通过 Docker 部署在内网服务器 (ssh mysql-backup)，通过 Cloudflare Tunnel 暴露到公网（无需 VPS、无需公网 IP、无需在路由器开入站端口）。

## 架构

```
用户浏览器 → https://fc.jetwong.top
       ↓
Cloudflare 边缘 (Anycast, 自动 HTTPS, Universal SSL)
       ↓ cloudflared 出站长连接 (systemd: cloudflared.service, 无入站端口)
内网 (mysql-backup) cloudflared → http://localhost:8088
       ↓
football-frontend 容器 (nginx)
       ├── /         → 静态文件 (Vue H5)
       ├── /api/     → football-api:7001
       └── /static/  → football-api:7001
                          ↓
                   football-mysql:3306 (对外 :3321)
                          ↑
                   football-scraper (每10分钟同步竞彩数据)
```

> Cloudflare Tunnel 的详细配置/维护/排查见 [cloudflare-tunnel.md](./cloudflare-tunnel.md)。

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

## Cloudflare Tunnel 管理

```bash
# 隧道服务状态
ssh mysql-backup "systemctl status cloudflared"

# 重启隧道（公网无法访问时）
ssh mysql-backup "systemctl restart cloudflared"

# 隧道实时日志
ssh mysql-backup "journalctl -u cloudflared -f --no-pager"

# 内网目标是否在服务
ssh mysql-backup "curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8088/"
```

服务文件: `/etc/systemd/system/cloudflared.service`、配置 `/etc/cloudflared/config.yml`。完整管理操作见 [cloudflare-tunnel.md](./cloudflare-tunnel.md)。

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
| -    | cloudflared（出站连接，无监听端口） |

## 故障排查

### 公网无法访问
```bash
ssh mysql-backup "systemctl status cloudflared"               # 隧道服务在跑？
ssh mysql-backup "journalctl -u cloudflared -n 50 --no-pager" # 隧道有报错？
ssh mysql-backup "curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8088/"  # 内网目标正常？
ssh mysql-backup "docker ps --filter 'name=football-'"        # 容器在运行？
```
若 `cloudflared` 在跑、内网 8088 返回 200 但公网仍不通，多为 Cloudflare 边缘证书问题，见 [cloudflare-tunnel.md](./cloudflare-tunnel.md) 的「问题排查」一节。

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
/etc/systemd/system/cloudflared.service       # Cloudflare Tunnel 服务
/etc/cloudflared/config.yml                    # 隧道 ingress 配置（service 用）
/root/.cloudflared/config.yml                  # 隧道 ingress 配置（CLI 默认读，两者保持一致）
/root/.cloudflared/<tunnel-id>.json            # 隧道凭证（机密）
/root/.cloudflared/cert.pem                    # 账号级 origin 证书
```
