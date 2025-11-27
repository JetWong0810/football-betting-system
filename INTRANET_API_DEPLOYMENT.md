# 内网部署 API-Service + MySQL，并通过 guiyun 公网服务器转发的方案

## 1. 目标架构概览

### 1.1 服务器角色

- **内网服务器（mysql-backup，10.130.130.139，CentOS 7，有 Docker）**
  - 部署 `api-service`（FastAPI，Docker 运行）
  - 部署 **MySQL 数据库**
  - 部署/继续运行 `scraper-service`（抓取体彩网数据并写入 MySQL）
- **公网服务器（guiyun）**
  - 对外暴露域名（如 `api.football.jetwong.top`）
  - 运行 Nginx，作为 **反向代理网关**
  - 作为 SSH 反向隧道的终点（只对内使用本机端口）

### 1.2 请求与数据流

1. 用户浏览器 → 访问 `https://api.football.jetwong.top/api/...`（guiyun）
2. guiyun 上的 Nginx 接收 `/api/...` 请求
3. Nginx 反向代理到 `127.0.0.1:9001`
4. `127.0.0.1:9001` 通过 SSH 反向隧道 → 转发到内网服务器 `10.130.130.139:7001`
5. `10.130.130.139:7001` 上的 `api-service` 处理请求：
   - 通过 `MYSQL_HOST=127.0.0.1` 连接本机 MySQL
6. `scraper-service` 也在内网服务器上运行，直接写入本机 MySQL

> 结果：  
> - **API + MySQL 全部只暴露在内网服务器本机 / 内网**  
> - 公网只暴露 Nginx + SSH（标准 22 端口），减少攻击面  
> - guiyun 不再直接访问 MySQL，仅通过 API 间接访问数据

---

## 2. 组件职责划分

### 2.1 内网服务器（10.130.130.139）

- `api-service`（Docker 容器）
  - 监听：`127.0.0.1:7001`（通过 Docker `-p 127.0.0.1:7001:7001`）
  - 数据源：本机 MySQL（`MYSQL_HOST=127.0.0.1`）
- MySQL
  - 存放所有业务数据（matches、odds、users 等）
  - 监听：`127.0.0.1:3306`（推荐仅对本机开放）
- `scraper-service`
  - 周期性从体彩网接口抓取数据
  - 写入本机 MySQL（`MYSQL_HOST=127.0.0.1`）
- SSH 客户端
  - 主动连接 guiyun，建立 SSH 反向隧道
  - 将 guiyun 的 `127.0.0.1:9001` 映射到本机 `127.0.0.1:7001`

### 2.2 公网服务器（guiyun）

- Nginx
  - 对外暴露 `api.football.jetwong.top`
  - 反向代理到本机 `127.0.0.1:9001`
- SSH 服务端（sshd）
  - 接收来自内网服务器的 SSH 连接
  - 允许 `-R` 反向端口转发

---

## 3. 内网服务器：部署 MySQL（与 `api-service` 同机）

MySQL 可使用系统包或 Docker 部署，下面给出 **最简单可行的 Docker 版本**（可根据现有环境调整）。

### 3.1 使用 Docker 部署 MySQL（示例）

```bash
# 创建数据目录
mkdir -p /data/mysql

# 启动 MySQL（仅监听本机）
docker run -d --name football-mysql \
  -e MYSQL_ROOT_PASSWORD=强密码 \
  -e MYSQL_DATABASE=football_betting \
  -p 127.0.0.1:3306:3306 \
  -v /data/mysql:/var/lib/mysql \
  --restart=always \
  mysql:8.0
```

> 注意：
> - 如果你已经在这台服务器上有 MySQL，并且 scraper-service 正在使用它，可以继续沿用，只需确保 `api-service` 和 `scraper-service` 的配置指向该 MySQL。
> - 建议 MySQL 只绑定 `127.0.0.1`，不直接对外网 / 其他机器开放。

### 3.2 初始化数据（如需要迁移）

如需从 guiyun 原来的 MySQL 迁移数据，可在 guiyun 上：

```bash
mysqldump -u root -p football_betting > football_betting.sql
```

将 `football_betting.sql` 拷贝到内网服务器，然后导入：

```bash
docker exec -i football-mysql \
  mysql -u root -p football_betting < football_betting.sql
```

---

## 4. 内网服务器：部署 `api-service`（Docker）

### 4.1 Dockerfile 示例

在 `/opt/football-betting-system/api-service` 中准备 `Dockerfile`（如已有，可按此思路调整）：

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

# 这里 MySQL 在同一台机器，建议使用 127.0.0.1
ENV MYSQL_HOST=127.0.0.1 \
    MYSQL_PORT=3306 \
    MYSQL_USER=your_user \
    MYSQL_PASSWORD=your_password \
    MYSQL_DATABASE=football_betting

EXPOSE 7001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7001"]
```

### 4.2 构建与运行

```bash
cd /opt/football-betting-system/api-service

# 构建镜像
docker build -t football-api .

# 运行容器，只暴露给本机
docker run -d --name football-api \
  -p 127.0.0.1:7001:7001 \
  --restart=always \
  --env MYSQL_HOST=127.0.0.1 \
  --env MYSQL_PORT=3306 \
  --env MYSQL_USER=your_user \
  --env MYSQL_PASSWORD=your_password \
  --env MYSQL_DATABASE=football_betting \
  football-api
```

### 4.3 本机验证

```bash
curl http://127.0.0.1:7001/api/health
```

出现健康检查 OK 即表示 `api-service` 已在内网服务器工作。

---

## 5. 内网服务器：配置 `scraper-service` 使用本机 MySQL

在 `scraper-service` 的配置或 `.env` 中：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=football_betting
```

测试：

```bash
cd /opt/football-betting-system/scraper-service
python3 main.py
```

确认能正常写入 MySQL。

---

## 6. 内网服务器 → guiyun：建立 SSH 反向隧道

### 6.1 前提：内网服务器能 SSH 到 guiyun

在内网服务器上：

```bash
ssh root@guiyun
```

确保能连上，最好配置 SSH 公钥免密登录（`ssh-copy-id`）。

### 6.2 手动测试反向隧道

在内网服务器上执行（测试用）：

```bash
ssh -N -R 127.0.0.1:9001:127.0.0.1:7001 root@guiyun
```

含义：

- 在 **guiyun 上** 开一个只绑定本机的端口：`127.0.0.1:9001`
- 所有访问 `guiyun:127.0.0.1:9001` 的请求，通过 SSH 隧道转发到
- **内网服务器本机** 的 `127.0.0.1:7001`（即 `api-service`）

在 guiyun 上测试：

```bash
curl http://127.0.0.1:9001/api/health
```

如果 OK，说明隧道 + API 一切正常。

### 6.3 使用 systemd 守护隧道（生产）

在内网服务器上创建 `/etc/systemd/system/football-api-tunnel.service`：

```ini
[Unit]
Description=Reverse SSH tunnel to guiyun for football api
After=network.target

[Service]
User=root
ExecStart=/usr/bin/ssh -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -N -R 127.0.0.1:9001:127.0.0.1:7001 root@guiyun
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

应用并启动：

```bash
systemctl daemon-reload
systemctl enable --now football-api-tunnel.service
systemctl status football-api-tunnel.service
```

之后，只要该服务是 active 状态，guiyun 上的 `127.0.0.1:9001` 就始终映射到内网 `api-service`。

---

## 7. 公网服务器 guiyun：Nginx 反向代理到本地 9001

### 7.1 HTTP 示例配置

```nginx
server {
    listen 80;
    server_name api.football.jetwong.top;

    location / {
        proxy_pass http://127.0.0.1:9001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 7.2 HTTPS 情况

如 guiyun 已配置 `listen 443 ssl` 与证书，只需将原来的 `proxy_pass` 改为：

```nginx
proxy_pass http://127.0.0.1:9001;
```

其余 SSL 相关配置保持不变。

### 7.3 重载 Nginx

```bash
nginx -t
systemctl reload nginx
```

---

## 8. 端到端验证

1. **内网服务器本地：**

   ```bash
   curl http://127.0.0.1:7001/api/health
   ```

2. **guiyun 本地：**

   ```bash
   curl http://127.0.0.1:9001/api/health
   ```

3. **外网（任意机器或本地开发机）：**

   ```bash
   curl https://api.football.jetwong.top/api/health
   ```

三步都通过，则表明：

- 内网服务器上的 `api-service` + MySQL 工作正常
- SSH 反向隧道稳定
- guiyun 的 Nginx 配置生效，对外访问链路完全打通

---

## 9. 将 MySQL 放在内网服务器的优劣分析

### 9.1 优点

- **安全性提升**：
  - MySQL 不再暴露在公网，只对内网服务器本机开放
  - 公网入侵者即便拿到 guiyun 权限，也看不到 MySQL，只能通过 API 访问有限数据
- **性能更好**：
  - `api-service` 与 MySQL 同机通信（`127.0.0.1`），网络延迟几乎为 0
  - `scraper-service` 也在同机，写入延迟更低
- **运维边界清晰**：
  - 所有业务数据集中在内网服务器，guiyun 只做网关和静态资源

### 9.2 需要注意的点

- 内网服务器成为业务“单点”，需要：
  - 定期 **数据库备份**（自动化 mysqldump 或物理备份）
  - 部署监控（CPU、内存、磁盘、MySQL 连接数）
- SSH 隧道是公网访问的关键链路：
  - 建议使用公钥认证，禁用密码登录
  - 可配合 `autossh` 或 systemd 保证自动重连
- 如果未来要扩展多台 API 服务器或多机房，需要重新设计多隧道 / VPN 方案
