# 抓取服务 (Scraper Service)

足球竞彩数据抓取服务，负责从外部 API 抓取比赛和赔率数据。

## 📋 功能

- 抓取足球比赛基本信息
- 抓取各种赔率数据：
  - 胜平负（HAD）
  - 让球胜平负（HHAD）
  - 比分（CRS）
  - 总进球数（TTG）
  - 半全场（HAFU）
- 数据存储到 MySQL 数据库
- 定时自动执行

## 🏗️ 架构

```
┌─────────────────────┐
│ 定时任务 (Crontab)   │
└──────────┬──────────┘
           │ 每 10 分钟
           ↓
┌─────────────────────┐
│   main.py           │
│   (抓取脚本)         │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│ SportterySyncService│
│   (抓取逻辑)         │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  外部竞彩 API        │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  MySQL 数据库        │
│  (guiyun 服务器)     │
└─────────────────────┘
```

## 📦 依赖

- Python 3.9+
- httpx - HTTP 客户端
- pymysql - MySQL 驱动
- python-dotenv - 环境变量管理
- cryptography - MySQL 连接加密

## 🚀 部署指南

### 1. 环境准备

在 mysql-backup 服务器上使用 Docker 容器：

```bash
# 进入 Docker 容器
docker exec -it py39-dev bash

# 进入项目目录
cd /workspace/scraper-service
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env
```

配置以下关键信息：

- `MYSQL_HOST`: guiyun 服务器 IP
- `MYSQL_USER`: football_sync
- `MYSQL_PASSWORD`: 数据库密码

### 4. 测试运行

```bash
python3 main.py
```

### 5. 配置定时任务

在宿主机（mysql-backup）上配置 crontab：

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每 10 分钟执行一次）
*/10 * * * * docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py" >> /var/log/football_scraper.log 2>&1
```

## 📝 使用说明

### 手动执行

```bash
# 在容器中执行
docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py"

# 或在容器内执行
cd /workspace/scraper-service
python3 main.py
```

### 查看日志

```bash
# 查看定时任务日志
tail -f /var/log/football_scraper.log

# 查看最近的执行结果
tail -100 /var/log/football_scraper.log | grep "同步完成"
```

### 停止定时任务

```bash
# 编辑 crontab
crontab -e

# 注释或删除相关行
# */10 * * * * docker exec py39-dev...
```

## 🔧 配置说明

### 环境变量

| 变量名                | 说明              | 默认值           |
| --------------------- | ----------------- | ---------------- |
| DB_TYPE               | 数据库类型        | mysql            |
| MYSQL_HOST            | MySQL 主机        | -                |
| MYSQL_PORT            | MySQL 端口        | 3306             |
| MYSQL_USER            | MySQL 用户        | football_sync    |
| MYSQL_PASSWORD        | MySQL 密码        | -                |
| MYSQL_DATABASE        | 数据库名          | football_betting |
| HTTP_TIMEOUT          | HTTP 超时时间(秒) | 20               |
| SYNC_INTERVAL_SECONDS | 同步间隔(秒)      | 600              |

### 数据库权限

确保 MySQL 用户有以下权限：

```sql
GRANT SELECT, INSERT, UPDATE ON football_betting.* TO 'football_sync'@'120.133.42.145';
```

## 📊 数据流程

1. **抓取比赛列表**

   - 从竞彩 API 获取当前在售的比赛
   - 解析比赛基本信息（球队、时间、联赛等）

2. **抓取赔率数据**

   - 胜平负（HAD）- 基本赔率
   - 让球胜平负（HHAD）- 含让球的赔率
   - 比分（CRS）- 各种比分的赔率
   - 总进球（TTG）- 总进球数的赔率
   - 半全场（HAFU）- 半场和全场结果组合

3. **数据存储**
   - 使用 UPSERT 语法更新或插入数据
   - 避免重复数据
   - 记录同步时间和统计信息

## 🐛 故障排查

### 问题 1：无法连接数据库

**现象**：

```
ERROR - Can't connect to MySQL server on '103.140.229.232'
```

**解决方案**：

1. 检查 guiyun 服务器的 MySQL 是否允许远程连接
2. 检查防火墙规则（端口 3306）
3. 验证用户名和密码

### 问题 2：抓取失败

**现象**：

```
ERROR - Sync failed: HTTPError...
```

**解决方案**：

1. 检查网络连接
2. 验证外部 API 地址是否正确
3. 检查 HTTP 超时设置

### 问题 3：定时任务未执行

**现象**：日志文件长时间无更新

**解决方案**：

```bash
# 检查 crontab 配置
crontab -l

# 检查 cron 服务状态
systemctl status cron

# 手动测试命令
docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py"
```

## 📈 监控建议

1. **定期检查日志**

   ```bash
   tail -f /var/log/football_scraper.log
   ```

2. **监控同步频率**

   ```bash
   grep "同步完成" /var/log/football_scraper.log | tail -20
   ```

3. **检查错误信息**
   ```bash
   grep "ERROR" /var/log/football_scraper.log | tail -20
   ```

## 🔄 更新部署

当代码有更新时：

```bash
# 1. 在宿主机上拉取最新代码
cd /opt/football-betting-system
git pull

# 2. 重新同步到容器（如果需要）
docker cp scraper-service py39-dev:/workspace/

# 3. 测试运行
docker exec py39-dev bash -c "cd /workspace/scraper-service && python3 main.py"
```

## 📞 相关文档

- [API 服务文档](../api-service/README.md)
- [部署文档](../docs/deployment.md)
- [架构说明](../docs/architecture.md)
