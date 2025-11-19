# API 服务

足球竞彩后端 API 服务，提供 RESTful API 接口供前端调用。

## 📋 功能

- RESTful API 接口
- 比赛列表查询（支持分页、筛选）
- 比赛详情查询
- 各类赔率数据查询
- 健康检查接口
- API 文档（Swagger/OpenAPI）

## 📦 依赖

- Python 3.12+
- FastAPI - Web 框架
- Uvicorn - ASGI 服务器
- PyMySQL - MySQL 驱动
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
```

### 3. 启动服务

```bash
python3 main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 7001 --reload
```

访问 http://localhost:7001/docs 查看 API 文档

## 📝 API 接口

### 健康检查

```bash
GET /api/health
```

### 获取比赛列表

```bash
GET /api/matches?page=1&page_size=20&date=2024-01-01&league=英超
```

### 获取比赛详情

```bash
GET /api/matches/{match_id}
```

### 获取比赛赔率

```bash
GET /api/matches/{match_id}/plays
```

完整 API 文档：访问 `/docs` 查看 Swagger UI

## 🔧 服务管理

### 查看服务状态

```bash
sudo systemctl status football-betting-api
```

### 查看日志

```bash
sudo journalctl -u football-betting-api -f
```

## 🐛 常见问题

### 服务无法启动

查看日志：`sudo journalctl -u football-betting-api -n 50`

常见原因：

- 端口 7001 被占用
- 数据库连接失败
- 环境变量配置错误

### 数据库连接失败

检查：

- MySQL 服务是否运行
- `.env` 文件配置是否正确
- 数据库是否已创建

## 📖 部署

部署说明请查看根目录的 [快速部署指南](../QUICK_DEPLOY.md)
