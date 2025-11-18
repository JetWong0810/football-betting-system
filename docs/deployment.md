# 部署文档

完整的系统部署指南，涵盖所有三个服务的部署流程。

## 📋 部署概览

本系统采用分布式架构，需要在两台服务器上部署：

- **guiyun** (103.140.229.232) - API 服务 + 前端服务 + MySQL 数据库
- **mysql-backup** (120.133.42.145) - 数据抓取服务

## 🔄 部署流程

### 第一步：准备服务器环境

#### guiyun 服务器

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install -y python3-pip python3-venv mysql-server mysql-client nginx git

# 安装 Node.js (使用 nvm)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 22
nvm use 22
```

#### mysql-backup 服务器

```bash
# 确保 Docker 已安装并运行
docker ps

# 检查 py39-dev 容器
docker exec -it py39-dev bash
python3 --version  # 应该是 Python 3.9
```

### 第二步：配置 MySQL 数据库（guiyun）

#### 1. 设置 MySQL root 密码

```bash
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'football_betting_2024'; FLUSH PRIVILEGES;"
```

#### 2. 创建数据库

```bash
mysql -u root -p'football_betting_2024' -e "CREATE DATABASE IF NOT EXISTS football_betting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

#### 3. 配置远程访问

编辑 `/etc/mysql/mysql.conf.d/mysqld.cnf`:

```ini
[mysqld]
bind-address = 0.0.0.0
```

重启 MySQL:

```bash
sudo systemctl restart mysql
```

#### 4. 创建远程用户

```bash
mysql -u root -p'football_betting_2024' << EOF
CREATE USER 'football_sync'@'120.133.42.145' IDENTIFIED BY 'sync_pass_2024_secure';
GRANT SELECT, INSERT, UPDATE ON football_betting.* TO 'football_sync'@'120.133.42.145';
FLUSH PRIVILEGES;
EOF
```

#### 5. 开放防火墙端口

在云服务器控制台添加安全组规则：
- 类型: 自定义 TCP
- 端口: 3306
- 来源: 120.133.42.145/32

### 第三步：部署 API 服务（guiyun）

#### 1. 克隆项目

```bash
cd /opt
git clone <repository-url> football-betting-system
cd football-betting-system/api-service
```

#### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. 配置环境变量

```bash
cat > .env << 'EOF'
# MySQL 数据库配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=football_betting_2024
MYSQL_DATABASE=football_betting

# API 配置
SYNC_INTERVAL_SECONDS=600
HTTP_TIMEOUT=20
EOF
```

#### 5. 初始化数据库

```bash
mysql -u root -p'football_betting_2024' football_betting < schema_mysql.sql
```

#### 6. 测试运行

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 7001
```

访问 http://103.140.229.232:7001/docs 验证

#### 7. 配置 Systemd 服务

```bash
sudo bash -c 'cat > /etc/systemd/system/football-betting-api.service << EOF
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
EOF'

sudo systemctl daemon-reload
sudo systemctl enable football-betting-api
sudo systemctl start football-betting-api
sudo systemctl status football-betting-api
```

#### 8. 配置 Nginx 反向代理

```bash
sudo bash -c 'cat > /etc/nginx/sites-available/api.football.jetwong.top << EOF
server {
    listen 80;
    server_name api.football.jetwong.top;

    access_log /var/log/nginx/api.football.access.log;
    error_log /var/log/nginx/api.football.error.log;

    location / {
        proxy_pass http://127.0.0.1:7001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF'

sudo ln -s /etc/nginx/sites-available/api.football.jetwong.top /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 第四步：部署抓取服务（mysql-backup）

#### 1. 上传代码到服务器

```bash
# 从本地上传
cd /path/to/football-betting-system
rsync -avz scraper-service/ mysql-backup:/opt/football-betting-system/scraper-service/
```

#### 2. 进入 Docker 容器

```bash
ssh mysql-backup
docker exec -it py39-dev bash
```

#### 3. 安装依赖

```bash
cd /workspace
# 将代码复制到容器挂载目录
# 或者在宿主机上：
# docker cp /opt/football-betting-system/scraper-service py39-dev:/workspace/

cd /workspace/scraper-service
pip3 install -r requirements.txt
```

#### 4. 配置环境变量

```bash
cat > .env << 'EOF'
# MySQL 数据库配置（连接到 guiyun 服务器）
MYSQL_HOST=103.140.229.232
MYSQL_PORT=3306
MYSQL_USER=football_sync
MYSQL_PASSWORD=sync_pass_2024_secure
MYSQL_DATABASE=football_betting

# API 配置
HTTP_TIMEOUT=20

# 竞彩 API
SPORTTERY_API_URL=https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
EOF
```

#### 5. 测试运行

```bash
python3 main.py
```

#### 6. 配置定时任务

在宿主机（mysql-backup）上配置 crontab：

```bash
crontab -e

# 添加以下行（每 10 分钟执行一次）
*/10 * * * * docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py" >> /var/log/football_scraper.log 2>&1
```

### 第五步：部署前端服务（guiyun）

#### 1. 本地构建（推荐）

由于 guiyun 服务器配置较低，建议在本地构建：

```bash
cd /path/to/football-betting-system/frontend

# 安装依赖
npm install

# 构建
npm run build:h5
```

#### 2. 上传到服务器

```bash
rsync -avz dist/build/h5/ guiyun:/opt/football-betting-system/frontend/dist/
```

#### 3. 配置 Nginx

```bash
ssh guiyun

sudo bash -c 'cat > /etc/nginx/sites-available/www.jetwong.top << EOF
server {
    listen 80;
    server_name www.jetwong.top jetwong.top;

    access_log /var/log/nginx/www.jetwong.top.access.log;
    error_log /var/log/nginx/www.jetwong.top.error.log;

    root /opt/football-betting-system/frontend/dist;
    index index.html;

    location / {
        try_files \$uri \$uri/ @fallback;
    }

    location @fallback {
        rewrite ^.*$ /index.html break;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json;
}
EOF'

sudo ln -s /etc/nginx/sites-available/www.jetwong.top /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 第六步：验证部署

#### 1. 测试 API 服务

```bash
curl http://api.football.jetwong.top/api/health
```

预期响应：
```json
{
  "status": "ok",
  "sync": {
    "last_synced_at": "...",
    "total_matches": 7,
    "total_odds": 324
  }
}
```

#### 2. 测试前端服务

浏览器访问：http://www.jetwong.top

#### 3. 检查抓取服务

```bash
ssh mysql-backup
tail -f /var/log/football_scraper.log
```

## 🔐 安全加固（可选但推荐）

### 1. 配置 HTTPS

```bash
# 安装 certbot
sudo apt install certbot python3-certbot-nginx -y

# 为 API 配置 SSL
sudo certbot --nginx -d api.football.jetwong.top

# 为前端配置 SSL
sudo certbot --nginx -d www.jetwong.top -d jetwong.top

# 自动续期
sudo systemctl enable certbot.timer
```

### 2. 配置防火墙

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3. 定期备份数据库

```bash
# 创建备份脚本
sudo bash -c 'cat > /opt/backup_db.sh << EOF
#!/bin/bash
DATE=\$(date +%Y%m%d_%H%M%S)
mkdir -p /opt/backups
mysqldump -u root -pfootball_betting_2024 football_betting > /opt/backups/football_betting_\${DATE}.sql
find /opt/backups/ -name "football_betting_*.sql" -mtime +7 -delete
EOF'

sudo chmod +x /opt/backup_db.sh

# 添加到 crontab (每天凌晨 2 点备份)
echo "0 2 * * * /opt/backup_db.sh" | sudo crontab -
```

## 📊 监控建议

### 1. 服务监控

```bash
# 定期检查服务状态
watch -n 60 'systemctl status football-betting-api'
```

### 2. 日志监控

```bash
# API 日志
sudo journalctl -u football-betting-api -f

# 抓取日志
ssh mysql-backup "tail -f /var/log/football_scraper.log"

# Nginx 访问日志
sudo tail -f /var/log/nginx/www.jetwong.top.access.log
```

### 3. 资源监控

```bash
# CPU 和内存使用
htop

# 磁盘使用
df -h

# 数据库大小
du -sh /var/lib/mysql/football_betting/
```

## 🔄 更新流程

### 更新 API 服务

```bash
cd /opt/football-betting-system
git pull
cd api-service
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart football-betting-api
```

### 更新抓取服务

```bash
cd /opt/football-betting-system
git pull
rsync -avz scraper-service/ mysql-backup:/opt/football-betting-system/scraper-service/
```

### 更新前端

```bash
# 本地
cd /path/to/football-betting-system/frontend
git pull
npm install
npm run build:h5
rsync -avz dist/build/h5/ guiyun:/opt/football-betting-system/frontend/dist/
```

## 📞 故障排查

详见 [故障排查文档](./troubleshooting.md)

## ✅ 部署检查清单

- [ ] guiyun 服务器环境准备完成
- [ ] mysql-backup 服务器环境准备完成
- [ ] MySQL 数据库配置完成
- [ ] MySQL 远程访问配置完成
- [ ] API 服务部署完成
- [ ] API Systemd 服务配置完成
- [ ] API Nginx 反向代理配置完成
- [ ] 抓取服务部署完成
- [ ] 抓取服务定时任务配置完成
- [ ] 前端构建完成
- [ ] 前端 Nginx 配置完成
- [ ] 所有服务测试通过
- [ ] HTTPS 配置完成（可选）
- [ ] 防火墙配置完成
- [ ] 数据库备份配置完成
- [ ] 监控配置完成

