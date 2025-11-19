# 🚀 快速部署指南

本文档介绍代码修改并推送到 GitHub 后，如何在本地快速一键部署。

## 📋 前置条件

1. ✅ 代码已推送到 GitHub
2. ✅ 本地已配置 SSH 密钥，可以免密登录服务器
3. ✅ 服务器上已首次部署过系统（使用 `deploy.sh` 完整部署）

## 🎯 快速部署流程

### 标准流程（3 步）

```bash
# 1. 提交并推送到 GitHub
git add .
git commit -m "你的提交信息"
git push origin main

# 2. 一键部署所有服务
./deploy.sh

# 3. 完成！✅
```

### 只更新某个服务

如果只修改了某个服务的代码，可以只部署该服务：

```bash
# 只更新 API 服务
./deploy.sh --api-only

# 只更新抓取服务
./deploy.sh --scraper-only

# 只更新前端服务（会自动构建）
./deploy.sh --frontend-only
```

### 前端快速更新（跳过构建）

如果前端代码没有变化，只是重新部署：

```bash
./deploy.sh --frontend-only --skip-build
```

## 📝 详细说明

### 部署脚本会自动做什么？

1. **自动检测 Git 仓库**

   - 从本地 `.git` 配置自动获取 GitHub 仓库地址
   - 无需手动输入仓库 URL

2. **自动拉取最新代码**

   - 在服务器上执行 `git pull origin main`
   - 自动切换到指定分支（默认 `main`）

3. **自动更新依赖**

   - API 服务：更新 Python 依赖
   - 抓取服务：更新 Python 依赖
   - 前端服务：自动构建（除非使用 `--skip-build`）

4. **自动重启服务**
   - API 服务：重启 Systemd 服务
   - 抓取服务：定时任务自动运行（无需重启）
   - 前端服务：Nginx 自动重载配置

### 指定 Git 分支

如果代码在其他分支（如 `develop`）：

```bash
./deploy.sh --branch develop
```

### 完整部署命令示例

```bash
# 部署所有服务（main 分支）
./deploy.sh

# 部署所有服务（develop 分支）
./deploy.sh --branch develop

# 只部署 API（main 分支）
./deploy.sh --api-only

# 只部署前端（跳过构建）
./deploy.sh --frontend-only --skip-build

# 组合使用
./deploy.sh --api-only --branch develop
```

## ⚡ 最快部署方式

### 场景 1: 只修改了 API 代码

```bash
git push origin main
./deploy.sh --api-only
```

**耗时**: ~30 秒

### 场景 2: 只修改了前端代码

```bash
git push origin main
./deploy.sh --frontend-only
```

**耗时**: ~2-3 分钟（包含构建时间）

### 场景 3: 只修改了抓取服务代码

```bash
git push origin main
./deploy.sh --scraper-only
```

**耗时**: ~20 秒

### 场景 4: 修改了多个服务

```bash
git push origin main
./deploy.sh
```

**耗时**: ~3-5 分钟

## 🔍 验证部署

部署完成后，脚本会自动验证，你也可以手动检查：

### 检查 API 服务

```bash
# 检查服务状态
ssh guiyun "sudo systemctl status football-betting-api"

# 测试 API
curl http://103.140.229.232:7001/api/health

# 查看最新日志
ssh guiyun "sudo journalctl -u football-betting-api -n 20"
```

### 检查抓取服务

```bash
# 查看定时任务日志
ssh mysql-backup "tail -f /var/log/football_scraper.log"

# 手动测试
ssh mysql-backup "docker exec py39-dev bash -c 'cd /workspace/scraper-service && python3 main.py'"
```

### 检查前端服务

```bash
# 浏览器访问
open https://www.jetwong.top

# 或检查文件
ssh guiyun "ls -la /opt/football-betting-system/frontend/dist/"
```

## 🐛 常见问题

### Q1: 提示 "无法连接到服务器"

**原因**: SSH 配置问题

**解决**:

```bash
# 测试 SSH 连接
ssh guiyun
ssh mysql-backup

# 如果失败，检查 ~/.ssh/config
cat ~/.ssh/config
```

### Q2: Git pull 失败

**原因**: 服务器上的代码有本地修改

**解决**:

```bash
# 在服务器上重置代码
ssh guiyun "cd /opt/football-betting-system && git reset --hard origin/main && git pull"
```

### Q3: API 服务启动失败

**原因**: 依赖更新或代码错误

**解决**:

```bash
# 查看详细日志
ssh guiyun "sudo journalctl -u football-betting-api -n 50"

# 手动测试
ssh guiyun "cd /opt/football-betting-system/api-service && source venv/bin/activate && python3 main.py"
```

### Q4: 前端构建失败

**原因**: Node.js 版本或依赖问题

**解决**:

```bash
# 清理并重新安装
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build:h5
```

## 💡 最佳实践

1. **提交前测试**

   ```bash
   # 本地测试 API
   cd api-service
   source venv/bin/activate
   uvicorn main:app --reload

   # 本地测试前端
   cd frontend
   npm run dev:h5
   ```

2. **使用分支管理**

   ```bash
   # 开发分支
   git checkout develop
   git push origin develop
   ./deploy.sh --branch develop --api-only

   # 生产分支
   git checkout main
   git merge develop
   git push origin main
   ./deploy.sh
   ```

3. **部署前检查**

   ```bash
   # 查看将要部署的更改
   git log origin/main..HEAD
   git diff origin/main
   ```

4. **部署后验证**

   > 部署脚本会自动检测 `api.football.jetwong.top` 和 `www.jetwong.top` 的可访问性，
   > 如提示域名不可达，请按照下列命令自行确认并排查 DNS / Nginx。

   ```bash
   # 快速健康检查
   curl http://103.140.229.232:7001/api/health
   open https://www.jetwong.top
   ```

### ❗ 常见问题：前端域名重定向次数过多

- **症状**：访问 `https://www.jetwong.top` 提示 `ERR_TOO_MANY_REDIRECTS`，`curl -I https://www.jetwong.top` 持续返回 `301 Moved Permanently`。
- **原因**：服务器上残留旧版 `www.jetwong.top.conf`，其内容是把请求永久重定向到同一个地址，导致浏览器在 `https://www.jetwong.top` 与自己之间死循环。新脚本写入的正确配置没有生效。
- **修复办法**：
  1. 重新执行 `./deploy.sh --frontend-only --skip-build`（已内置清理逻辑，会删除残留的 `sites-available/sites-enabled` 旧文件并重新生成配置）。
  2. 或者手工清理：`ssh guiyun 'sudo rm -f /etc/nginx/sites-{available,enabled}/www.jetwong.top*'`，再运行脚本写回配置。
  3. 执行 `ssh guiyun 'sudo nginx -t && sudo systemctl reload nginx'`，随后 `curl -I https://www.jetwong.top` 应该返回 `200`/`304`。

> 新配置还额外提供 `jetwong.top -> www.jetwong.top` 的显式跳转，等根域名解析生效后即可自动汇聚到 `www`。

## 📊 部署时间参考

| 服务     | 首次部署 | 更新部署  |
| -------- | -------- | --------- |
| API 服务 | ~2 分钟  | ~30 秒    |
| 抓取服务 | ~1 分钟  | ~20 秒    |
| 前端服务 | ~5 分钟  | ~2-3 分钟 |
| 全部服务 | ~8 分钟  | ~3-5 分钟 |

## 🎯 一键部署命令总结

```bash
# 最常用：部署所有服务
./deploy.sh

# 只更新 API
./deploy.sh --api-only

# 只更新前端
./deploy.sh --frontend-only

# 指定分支
./deploy.sh --branch develop

# 前端跳过构建
./deploy.sh --frontend-only --skip-build
```

---

**提示**: 首次部署请使用完整部署流程，后续更新使用快速部署即可。
