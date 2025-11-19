# 抓取服务

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
- 定时自动执行（每 10 分钟）

## 📦 依赖

- Python 3.9+
- httpx - HTTP 客户端
- pymysql - MySQL 驱动
- python-dotenv - 环境变量管理

## 🚀 本地开发

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=football_betting
HTTP_TIMEOUT=20
```

### 3. 运行

```bash
python3 main.py
```

## 🔧 配置说明

| 变量名         | 说明              | 默认值           |
| -------------- | ----------------- | ---------------- |
| MYSQL_HOST     | MySQL 主机        | -                |
| MYSQL_PORT     | MySQL 端口        | 3306             |
| MYSQL_USER     | MySQL 用户        | -                |
| MYSQL_PASSWORD | MySQL 密码        | -                |
| MYSQL_DATABASE | 数据库名          | football_betting |
| HTTP_TIMEOUT   | HTTP 超时时间(秒) | 20               |

## 📊 数据流程

1. **抓取比赛列表** - 从竞彩 API 获取当前在售的比赛
2. **抓取赔率数据** - 获取各类赔率（胜平负、让球、比分等）
3. **数据存储** - 使用 UPSERT 语法更新或插入数据

## 🐛 常见问题

### 无法连接数据库

检查：

- MySQL 服务是否运行
- 防火墙规则（端口 3306）
- 用户名和密码是否正确

### 抓取失败

检查：

- 网络连接
- 外部 API 地址是否正确
- HTTP 超时设置

### 定时任务未执行

检查：

```bash
crontab -l
systemctl status cron
```

## 📖 部署

部署说明请查看根目录的 [快速部署指南](../QUICK_DEPLOY.md)
