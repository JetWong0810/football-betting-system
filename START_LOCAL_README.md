# 本地服务启动脚本使用说明

## 功能说明

`start-local.sh` 是一个一键启动本地前后端服务的脚本，支持：

- ✅ 自动启动 API Service（后端）和 Frontend（前端）
- ✅ 后台运行，不占用终端
- ✅ 自动检测端口占用和服务状态
- ✅ 智能日志管理
- ✅ 支持停止、重启、状态查询

## 使用方法

### 1. 启动所有服务

```bash
./start-local.sh
```

这会：
- 检查 MySQL 连接状态
- 启动 API Service（端口 7001）
- 启动 Frontend（端口 5173）
- 服务在后台运行，日志输出到 `logs/` 目录

### 2. 查看服务状态

```bash
./start-local.sh --status
```

显示当前服务运行状态，包括 PID 和端口信息。

### 3. 停止所有服务

```bash
./start-local.sh --stop
```

优雅停止所有服务，并清理端口占用。

### 4. 重启所有服务

```bash
./start-local.sh --restart
```

先停止再启动所有服务。

## 访问地址

启动成功后，可通过以下地址访问：

- **前端页面**: http://localhost:5173
- **后端 API**: http://localhost:7001
- **API 文档**: http://localhost:7001/docs
- **健康检查**: http://localhost:7001/api/health

## 日志查看

日志文件位于 `logs/` 目录：

```bash
# 查看 API Service 日志
tail -f logs/api-service.log

# 查看 Frontend 日志
tail -f logs/frontend.log
```

## 环境要求

### 1. Python 环境（API Service）

- Python 3.9+
- 依赖会自动安装（如果未安装）

### 2. Node.js 环境（Frontend）

- Node.js 14+
- npm 依赖会自动安装（如果 `node_modules` 不存在）

### 3. MySQL 数据库

确保 MySQL 服务已启动：

```bash
# macOS
brew services start mysql

# Linux
sudo systemctl start mysql
```

### 4. 环境变量配置

确保 `api-service/.env` 文件存在且配置正确，参考：

```env
# 微信小程序配置
WECHAT_APPID=your_appid
WECHAT_SECRET=your_secret

# MySQL 数据库配置（可选，使用默认值）
# MYSQL_HOST=localhost
# MYSQL_PORT=3306
# MYSQL_USER=root
# MYSQL_PASSWORD=your_password
# MYSQL_DATABASE=football_betting
```

## 常见问题

### 1. 端口已被占用

**错误信息**:
```
✗ 端口 7001 已被占用，请先停止占用进程
```

**解决方案**:
```bash
# 先停止所有服务
./start-local.sh --stop

# 然后重新启动
./start-local.sh
```

### 2. API Service 启动失败

**解决步骤**:

1. 查看日志找到错误原因：
```bash
cat logs/api-service.log
```

2. 常见原因：
   - MySQL 连接失败 → 检查数据库配置和服务状态
   - 缺少依赖包 → 手动安装：`cd api-service && pip3 install -r requirements.txt`
   - `.env` 文件缺失 → 创建并配置环境变量

### 3. Frontend 启动失败

**解决步骤**:

1. 查看日志：
```bash
cat logs/frontend.log
```

2. 常见原因：
   - 缺少依赖 → 手动安装：`cd frontend && npm install`
   - Node 版本过低 → 升级到 Node.js 14+

### 4. MySQL 连接失败

**检查步骤**:

```bash
# 确认 MySQL 服务运行中
brew services list | grep mysql  # macOS
sudo systemctl status mysql      # Linux

# 测试连接
mysql -u root -p -e "SELECT 1"

# 确认数据库存在
mysql -u root -p -e "SHOW DATABASES LIKE 'football_betting'"
```

## 进程管理

脚本使用 PID 文件管理进程：

- API Service PID: `/tmp/football-betting-api.pid`
- Frontend PID: `/tmp/football-betting-frontend.pid`

如果脚本无法正常停止服务，可手动清理：

```bash
# 手动杀死进程
kill $(cat /tmp/football-betting-api.pid)
kill $(cat /tmp/football-betting-frontend.pid)

# 或直接通过端口杀死
lsof -ti:7001 | xargs kill
lsof -ti:5173 | xargs kill

# 清理 PID 文件
rm -f /tmp/football-betting-*.pid
```

## 与生产环境区别

**本地开发环境**:
- API Service: 直接运行 `python3 main.py`（带 auto-reload）
- Frontend: Vite 开发服务器，支持热更新
- 数据库: 本地 MySQL（localhost）

**生产环境**:
- API Service: systemd 管理，部署在 guiyun 服务器
- Frontend: 编译为静态文件，由 Nginx 提供服务
- 数据库: 远程 MySQL（guiyun 服务器）

详见项目根目录的 `WARP.md` 了解生产环境部署。

## 脚本结构

```
start-local.sh
├── 服务启动 (start_api, start_frontend)
├── 服务停止 (stop_service, stop_all)
├── 状态检查 (show_status, is_running)
├── 端口检测 (check_port, wait_for_port)
└── MySQL 检查 (check_mysql)
```

## 注意事项

1. **首次运行**: 会自动安装依赖，可能需要较长时间
2. **后台运行**: 服务在后台运行，关闭终端不会影响服务
3. **日志轮转**: 日志文件会不断增长，建议定期清理
4. **数据同步**: 本地开发时，scraper service 通常不需要运行（使用远程数据库的数据）

## 快速参考

```bash
# 启动
./start-local.sh

# 状态
./start-local.sh --status

# 停止
./start-local.sh --stop

# 重启
./start-local.sh --restart

# 查看日志
tail -f logs/api-service.log
tail -f logs/frontend.log
```
