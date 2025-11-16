# 故障排查文档

本文档收集了常见问题及其解决方案。

## 🚨 API 服务问题

### 问题 1：服务无法启动

**现象**:
```bash
sudo systemctl status football-betting-api
● football-betting-api.service - Football Betting API Service
     Active: failed
```

**排查步骤**:

1. 查看详细日志
```bash
sudo journalctl -u football-betting-api -n 50
```

2. 检查端口占用
```bash
sudo lsof -i :7001
# 或
sudo netstat -tlnp | grep 7001
```

3. 检查 Python 环境
```bash
cd /opt/football-betting-system/api-service
source venv/bin/activate
python -c "import fastapi; print(fastapi.__version__)"
```

**常见原因及解决方案**:

**原因 1: 端口被占用**
```bash
# 查找占用进程
sudo lsof -i :7001
# 杀死进程
sudo kill -9 <PID>
# 重启服务
sudo systemctl restart football-betting-api
```

**原因 2: 数据库连接失败**
```bash
# 测试数据库连接
mysql -u root -p'football_betting_2024' -e "SELECT 1;"
# 检查 .env 配置
cat /opt/football-betting-system/api-service/.env
```

**原因 3: Python 依赖缺失**
```bash
cd /opt/football-betting-system/api-service
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart football-betting-api
```

### 问题 2：502 Bad Gateway

**现象**:
浏览器访问 API 时返回 502 错误

**排查步骤**:

1. 检查 API 服务状态
```bash
sudo systemctl status football-betting-api
curl http://localhost:7001/api/health
```

2. 检查 Nginx 配置
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/api.football.error.log
```

3. 检查网络连接
```bash
telnet localhost 7001
```

**解决方案**:

如果 API 服务未运行：
```bash
sudo systemctl start football-betting-api
```

如果 Nginx 配置错误：
```bash
sudo nginx -t  # 查看错误信息
sudo vim /etc/nginx/sites-available/api.football.jetwong.top
sudo systemctl reload nginx
```

### 问题 3：API 响应慢

**现象**:
API 请求响应时间超过 3 秒

**排查步骤**:

1. 检查数据库查询性能
```bash
mysql -u root -p'football_betting_2024' football_betting

# 启用慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;

# 查看慢查询
SELECT * FROM mysql.slow_log;
```

2. 检查服务器资源
```bash
htop
df -h
free -m
```

**解决方案**:

**优化数据库查询**:
```sql
-- 添加索引
CREATE INDEX idx_match_date ON matches(match_date);
CREATE INDEX idx_match_status ON matches(match_status);
CREATE INDEX idx_league_name ON matches(league_name);

-- 分析表
ANALYZE TABLE matches;
```

**增加服务器资源** 或 **优化查询逻辑**

## 🕷️ 抓取服务问题

### 问题 1：定时任务未执行

**现象**:
数据长时间未更新，日志文件无新记录

**排查步骤**:

1. 检查 crontab 配置
```bash
ssh mysql-backup
crontab -l
```

2. 检查 cron 服务状态
```bash
sudo systemctl status cron
```

3. 查看日志
```bash
tail -f /var/log/football_scraper.log
```

**解决方案**:

**原因 1: crontab 配置错误**
```bash
crontab -e

# 确保配置正确
*/10 * * * * docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py" >> /var/log/football_scraper.log 2>&1
```

**原因 2: Docker 容器未运行**
```bash
docker ps | grep py39-dev
# 如果未运行
docker start py39-dev
```

**原因 3: 脚本执行失败**
```bash
# 手动测试
docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py"
```

### 问题 2：数据库连接失败

**现象**:
```
ERROR - Can't connect to MySQL server on '103.140.229.232'
```

**排查步骤**:

1. 测试网络连接
```bash
ssh mysql-backup
telnet 103.140.229.232 3306
```

2. 检查防火墙规则
```bash
ssh guiyun
sudo ufw status
```

3. 检查 MySQL 远程访问配置
```bash
ssh guiyun
mysql -u root -p'football_betting_2024' << EOF
SELECT user, host FROM mysql.user WHERE user='football_sync';
EOF
```

**解决方案**:

**原因 1: 防火墙阻止**
在云服务器控制台添加安全组规则，允许来自 120.133.42.145 的 3306 端口访问

**原因 2: MySQL 未监听外部连接**
```bash
# 编辑配置
sudo vim /etc/mysql/mysql.conf.d/mysqld.cnf

# 修改
bind-address = 0.0.0.0

# 重启
sudo systemctl restart mysql
```

**原因 3: 用户权限不足**
```bash
mysql -u root -p'football_betting_2024' << EOF
GRANT SELECT, INSERT, UPDATE ON football_betting.* TO 'football_sync'@'120.133.42.145';
FLUSH PRIVILEGES;
EOF
```

### 问题 3：抓取失败

**现象**:
```
ERROR - Sync failed: HTTPError 403
```

**排查步骤**:

1. 检查网络连接
```bash
docker exec py39-dev curl -I https://webapi.sporttery.cn
```

2. 检查 User-Agent 配置
```bash
cat /workspace/scraper-service/.env | grep USER_AGENT
```

**解决方案**:

**原因 1: API 限流或封禁**
- 增加请求间隔
- 更换 User-Agent
- 使用代理

**原因 2: API 地址变更**
更新 `.env` 中的 `SPORTTERY_API_URL`

## 🖥️ 前端问题

### 问题 1：页面无法访问

**现象**:
浏览器访问 www.jetwong.top 返回 404 或 502

**排查步骤**:

1. 检查 Nginx 状态
```bash
sudo systemctl status nginx
```

2. 检查 Nginx 配置
```bash
sudo nginx -t
cat /etc/nginx/sites-available/www.jetwong.top
```

3. 检查文件是否存在
```bash
ls -la /opt/football-betting-system/frontend/dist/
```

**解决方案**:

**原因 1: Nginx 未运行**
```bash
sudo systemctl start nginx
```

**原因 2: 配置错误**
```bash
sudo nginx -t  # 查看错误
sudo vim /etc/nginx/sites-available/www.jetwong.top
sudo systemctl reload nginx
```

**原因 3: 文件缺失**
重新构建并上传：
```bash
# 本地
cd /path/to/football-betting-system/frontend
npm run build:h5
rsync -avz dist/build/h5/ guiyun:/opt/football-betting-system/frontend/dist/
```

### 问题 2：API 请求失败

**现象**:
浏览器控制台显示 CORS 错误或网络错误

**排查步骤**:

1. 检查浏览器控制台 (F12 -> Network)
2. 检查 API 服务状态
```bash
curl http://api.football.jetwong.top/api/health
```

3. 检查前端 API 配置
```bash
cat /path/to/frontend/src/utils/http.js
```

**解决方案**:

**原因 1: API 地址错误**
编辑 `src/utils/http.js`，确保 API 地址正确：
```javascript
return 'http://api.football.jetwong.top'
```

**原因 2: CORS 配置问题**
检查 API 服务的 CORS 设置（在 `main.py` 中）

**原因 3: API 服务未运行**
```bash
ssh guiyun
sudo systemctl start football-betting-api
```

### 问题 3：页面白屏

**现象**:
页面加载后显示空白

**排查步骤**:

1. 检查浏览器控制台错误
2. 检查网络请求是否成功
3. 检查构建产物是否完整

**解决方案**:

清除浏览器缓存并重新构建：
```bash
# 本地
rm -rf dist node_modules
npm install
npm run build:h5
rsync -avz dist/build/h5/ guiyun:/opt/football-betting-system/frontend/dist/
```

## 🗄️ 数据库问题

### 问题 1：连接数过多

**现象**:
```
ERROR 1040 (HY000): Too many connections
```

**解决方案**:

1. 临时增加最大连接数
```sql
SET GLOBAL max_connections = 500;
```

2. 永久修改
```bash
sudo vim /etc/mysql/mysql.conf.d/mysqld.cnf

# 添加
[mysqld]
max_connections = 500

# 重启
sudo systemctl restart mysql
```

### 问题 2：磁盘空间不足

**现象**:
```
ERROR 1114 (HY000): The table is full
```

**排查步骤**:

1. 检查磁盘使用
```bash
df -h
du -sh /var/lib/mysql/
```

2. 查找大文件
```bash
du -h /var/lib/mysql/ | sort -h | tail -20
```

**解决方案**:

1. 清理旧数据
```sql
-- 删除 30 天前的比赛数据
DELETE FROM matches WHERE match_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY);

-- 优化表
OPTIMIZE TABLE matches;
```

2. 清理日志文件
```bash
# 清理 binlog
mysql -u root -p << EOF
PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY);
EOF
```

### 问题 3：查询慢

**现象**:
查询时间超过 5 秒

**解决方案**:

1. 分析慢查询
```sql
SHOW FULL PROCESSLIST;
EXPLAIN SELECT * FROM matches WHERE ...;
```

2. 添加索引
```sql
CREATE INDEX idx_match_date ON matches(match_date);
```

3. 优化查询
- 避免 SELECT *
- 使用 LIMIT
- 添加适当的 WHERE 条件

## 🌐 网络问题

### 问题 1：域名无法解析

**现象**:
`ping www.jetwong.top` 失败

**排查步骤**:

1. 检查 DNS 解析
```bash
nslookup www.jetwong.top
dig www.jetwong.top
```

2. 检查域名配置
登录域名服务商控制台，检查 A 记录

**解决方案**:

确保域名 DNS 记录正确：
- `www.jetwong.top` A → 103.140.229.232
- `api.football.jetwong.top` A → 103.140.229.232

### 问题 2：SSL 证书问题

**现象**:
浏览器显示"连接不安全"

**解决方案**:

重新申请证书：
```bash
sudo certbot --nginx -d www.jetwong.top -d jetwong.top
sudo certbot --nginx -d api.football.jetwong.top
```

## 📊 性能问题

### 问题 1：服务器负载高

**现象**:
CPU 使用率持续 > 80%

**排查步骤**:

1. 查看进程
```bash
htop
top -c
```

2. 查看具体进程
```bash
ps aux | sort -k3 -r | head -10  # CPU
ps aux | sort -k4 -r | head -10  # 内存
```

**解决方案**:

1. 优化应用代码
2. 增加服务器配置
3. 使用缓存（Redis）
4. 数据库读写分离

### 问题 2：内存不足

**现象**:
```
Out of memory: Kill process...
```

**排查步骤**:

```bash
free -m
vmstat 1
```

**解决方案**:

1. 增加 swap
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

2. 优化应用内存使用
3. 升级服务器配置

## 🔧 常用排查命令

### 服务状态
```bash
# 所有服务状态
sudo systemctl status football-betting-api
sudo systemctl status nginx
sudo systemctl status mysql

# 查看端口监听
sudo netstat -tlnp
sudo lsof -i :7001
sudo lsof -i :80
sudo lsof -i :3306
```

### 日志查看
```bash
# API 服务日志
sudo journalctl -u football-betting-api -f
sudo journalctl -u football-betting-api -n 100

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/api.football.error.log

# 抓取服务日志
ssh mysql-backup "tail -f /var/log/football_scraper.log"

# 系统日志
sudo tail -f /var/log/syslog
```

### 资源监控
```bash
# CPU 和内存
htop
top

# 磁盘
df -h
du -sh *

# 网络
iftop
nethogs
```

### 数据库
```bash
# 连接数据库
mysql -u root -p'football_betting_2024' football_betting

# 查看进程
SHOW FULL PROCESSLIST;

# 查看状态
SHOW STATUS;
SHOW VARIABLES LIKE 'max_connections';

# 查看表大小
SELECT 
  table_name,
  ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size (MB)'
FROM information_schema.TABLES
WHERE table_schema = 'football_betting'
ORDER BY (data_length + index_length) DESC;
```

## 📞 获取帮助

如果以上方法无法解决问题：

1. 查看详细日志
2. 搜索错误信息
3. 查阅官方文档
4. 提交 Issue

## 相关文档

- [部署文档](./deployment.md)
- [架构文档](./architecture.md)
- [API 服务文档](../api-service/README.md)
- [抓取服务文档](../scraper-service/README.md)
- [前端服务文档](../frontend/README.md)

