# API 服务 (API Service)

足球竞彩后端 API 服务，提供 RESTful API 接口供前端调用。

## 📋 功能

- RESTful API 接口
- 比赛列表查询（支持分页、筛选）
- 比赛详情查询
- 各类赔率数据查询
- 健康检查接口
- API 文档（Swagger/OpenAPI）

## 🏗️ 架构

```
┌──────────────────┐
│   Nginx (80)     │
│   反向代理        │
└────────┬─────────┘
         │
         ↓
┌──────────────────┐
│ FastAPI (7001)   │
│  API 服务        │
└────────┬─────────┘
         │
         ↓
┌──────────────────┐
│ MySQL (3306)     │
│  本地数据库       │
└──────────────────┘
```

## 📦 依赖

- Python 3.12+
- FastAPI - Web 框架
- Uvicorn - ASGI 服务器
- PyMySQL - MySQL 驱动
- python-dotenv - 环境变量管理

## 🚀 部署指南

### 1. 环境准备

在 guiyun 服务器上：

```bash
# 进入项目目录
cd /opt/football-betting-system/api-service

# 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env
```

关键配置（系统默认使用 MySQL，无需额外配置 DB_TYPE）：

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=football_betting_2024
MYSQL_DATABASE=football_betting
```

### 4. 初始化数据库

```bash
# 创建数据库
mysql -u root -p'football_betting_2024' -e "CREATE DATABASE IF NOT EXISTS football_betting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 导入表结构
mysql -u root -p'football_betting_2024' football_betting < schema_mysql.sql
```

### 5. 测试运行

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行 API 服务
uvicorn main:app --host 0.0.0.0 --port 7001
```

访问 http://103.140.229.232:7001/docs 查看 API 文档

### 6. 配置 Systemd 服务

创建服务文件 `/etc/systemd/system/football-betting-api.service`:

```ini
[Unit]
Description=Football Betting API Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/football-betting-system/api-service
Environment="PATH=/opt/football-betting-system/api-service/venv/bin"
ExecStart=/opt/football-betting-system/api-service/venv/bin/uvicorn main:app --host 0.0.0.0 --port 7001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable football-betting-api
sudo systemctl start football-betting-api
sudo systemctl status football-betting-api
```

### 7. 配置 Nginx 反向代理

创建配置文件 `/etc/nginx/sites-available/api.football.jetwong.top`:

```nginx
server {
    listen 80;
    server_name api.football.jetwong.top;

    access_log /var/log/nginx/api.football.access.log;
    error_log /var/log/nginx/api.football.error.log;

    location / {
        proxy_pass http://127.0.0.1:7001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/api.football.jetwong.top /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 📝 API 接口

### 健康检查

```bash
GET /api/health
```

响应：

```json
{
  "status": "ok",
  "sync": {
    "last_synced_at": "2025-11-16T07:40:37.066771",
    "total_matches": 7,
    "total_odds": 324
  }
}
```

### 获取比赛列表

```bash
GET /api/matches?page=1&page_size=20&date=2024-01-01&league=英超
```

参数：

- `page`: 页码（默认 1）
- `page_size`: 每页数量（默认 20，最大 50）
- `date`: 比赛日期，格式 YYYY-MM-DD（可选）
- `league`: 联赛名称（可选）

### 获取比赛详情

```bash
GET /api/matches/{match_id}
```

### 获取比赛赔率

```bash
GET /api/matches/{match_id}/plays
```

### API 文档

访问 `/docs` 查看完整的 Swagger UI 文档

## 🔧 服务管理

### 查看服务状态

```bash
sudo systemctl status football-betting-api
```

### 启动/停止/重启服务

```bash
sudo systemctl start football-betting-api
sudo systemctl stop football-betting-api
sudo systemctl restart football-betting-api
```

### 查看日志

```bash
# 查看服务日志
sudo journalctl -u football-betting-api -f

# 查看最近 100 条日志
sudo journalctl -u football-betting-api -n 100

# 查看今天的日志
sudo journalctl -u football-betting-api --since today
```

### Nginx 日志

```bash
# 访问日志
sudo tail -f /var/log/nginx/api.football.access.log

# 错误日志
sudo tail -f /var/log/nginx/api.football.error.log
```

## 🔍 测试接口

```bash
# 健康检查
curl http://api.football.jetwong.top/api/health

# 获取比赛列表
curl http://api.football.jetwong.top/api/matches

# 获取比赛详情
curl http://api.football.jetwong.top/api/matches/123456

# 获取赔率
curl http://api.football.jetwong.top/api/matches/123456/plays
```

## 🐛 故障排查

### 问题 1：服务无法启动

查看日志：

```bash
sudo journalctl -u football-betting-api -n 50
```

常见原因：

- 端口 7001 被占用
- Python 虚拟环境路径错误
- 数据库连接失败
- 环境变量配置错误

### 问题 2：502 Bad Gateway

检查：

```bash
# API 服务是否运行
sudo systemctl status football-betting-api

# 本地端口是否监听
curl http://localhost:7001/api/health

# Nginx 配置
sudo nginx -t
```

### 问题 3：数据库连接失败

检查：

```bash
# MySQL 服务状态
sudo systemctl status mysql

# 测试数据库连接
mysql -u root -p'football_betting_2024' -e "SELECT 1;"

# 检查 .env 文件配置
cat .env
```

## 🔄 更新部署

当代码有更新时：

```bash
# 1. 拉取最新代码
cd /opt/football-betting-system
git pull

# 2. 更新依赖（如果有变化）
cd api-service
source venv/bin/activate
pip install -r requirements.txt

# 3. 重启服务
sudo systemctl restart football-betting-api

# 4. 验证
curl http://api.football.jetwong.top/api/health
```

## 📊 性能优化

### 数据库优化

1. **添加索引**

```sql
CREATE INDEX idx_match_date ON matches(match_date);
CREATE INDEX idx_match_status ON matches(match_status);
CREATE INDEX idx_league_name ON matches(league_name);
```

2. **定期清理旧数据**

```sql
DELETE FROM matches WHERE match_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY);
```

### API 优化

1. **启用响应压缩**（已在 Nginx 中配置）
2. **添加缓存层**（Redis）
3. **优化查询语句**
4. **添加请求限流**

## 🔒 安全建议

1. **修改数据库密码**

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY '更强的密码';
FLUSH PRIVILEGES;
```

2. **限制数据库访问**

```sql
-- 创建专用用户
CREATE USER 'api_user'@'localhost' IDENTIFIED BY '强密码';
GRANT SELECT ON football_betting.* TO 'api_user'@'localhost';
```

3. **配置防火墙**

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

4. **配置 HTTPS**

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.football.jetwong.top
```

## 📞 相关文档

- [抓取服务文档](../scraper-service/README.md)
- [前端服务文档](../frontend/README.md)
- [部署文档](../docs/deployment.md)
