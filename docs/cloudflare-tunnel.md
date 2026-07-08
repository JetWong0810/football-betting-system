# Cloudflare Tunnel 部署与维护手册

记录如何通过 Cloudflare Tunnel 把内网 `mysql-backup` 上部署的 football-betting-system 暴露到公网，无需 VPS、无需公网 IP、无需在路由器开入站端口。

## 架构

```
手机/浏览器
   │  HTTPS
   ▼
fc.jetwong.top  ──CNAME──▶  <tunnel-id>.cfargotunnel.com  (Cloudflare 边缘 Anycast IP)
   │
   ▼  (cloudflared 出站长连接，无入站端口)
mysql-backup (10.130.130.139, 内网)
   │  cloudflared.service (systemd, 开机自启)
   ▼  ingress: fc.jetwong.top → http://localhost:8088
football-frontend (nginx, Docker, 宿主机 8088 端口)
   │  nginx 反代 /api → football-api:7001
   ▼
football-api (FastAPI, Docker)
```

**关键点**：cloudflared 只发起到 Cloudflare 的**出站连接**，内网不需要任何入站端口、不需要公网 IP。只要 `mysql-backup` 能访问外网（能连 Cloudflare）服务就在线。

## 前置条件

- 域名 `jetwong.top` 的 NS 托管在 Cloudflare（免费）。本项目的 NS 为：
  - `armando.ns.cloudflare.com`
  - `peaches.ns.cloudflare.com`
- Cloudflare 账号下已添加站点 `jetwong.top`（Free 套餐），现有 DNS 记录已导入齐全。
- `mysql-backup` 可 ssh 登录（root），能访问外网。

## 关键资源信息

| 项 | 值 |
|---|---|
| 隧道名 | `football` |
| 隧道 ID | `e4711304-62ba-4bf4-ba47-0d365621d6e4` |
| 凭证文件 | `/root/.cloudflared/e4711304-62ba-4bf4-ba47-0d365621d6e4.json` |
| 配置文件（service 实际使用） | `/etc/cloudflared/config.yml` |
| 配置文件（CLI 默认读取） | `/root/.cloudflared/config.yml` |
| 证书（origin cert） | `/root/.cloudflared/cert.pem` |
| systemd 服务 | `cloudflared.service` |
| 内网目标 | `http://localhost:8088`（football-frontend nginx） |
| 公网域名 | `https://fc.jetwong.top` |

## 首次部署步骤（已完成，仅供参考）

### 1. 域名迁入 Cloudflare

1. Cloudflare 后台 Add Site → 输入 `jetwong.top` → 选 Free 套餐
2. CF 扫描导入现有 DNS 记录，核对齐全（尤其 `fc` 这条）
3. CF 给出两个 NS，到域名注册商（本项目为商务中国 BIZCN）把 NS 从 `ns1/ns2.4everdns.com` 改成 CF 的两个
4. 等 NS 全球生效（`dig @1.1.1.1 NS jetwong.top` 看到 cloudflare 即生效）

### 2. 安装 cloudflared

```bash
ssh mysql-backup
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
cloudflared --version
```

### 3. 登录授权（拿 origin cert）

headless 服务器上 `cloudflared tunnel login` 的浏览器回调到 localhost 不便操作，改用本地 macOS 执行后把 cert 传过去：

```bash
# 本地 mac（已装 brew install cloudflared）
cloudflared tunnel login          # 浏览器打开 URL，选择 jetwong.top 授权
# cert 落到 ~/.cloudflared/cert.pem
scp ~/.cloudflared/cert.pem mysql-backup:~/.cloudflared/cert.pem
```

### 4. 创建隧道 + 配置 ingress

```bash
ssh mysql-backup
cloudflared tunnel create football
# → 生成 /root/.cloudflared/<tunnel-id>.json 凭证

cat > /root/.cloudflared/config.yml <<'EOF'
tunnel: e4711304-62ba-4bf4-ba47-0d365621d6e4
credentials-file: /root/.cloudflared/e4711304-62ba-4bf4-ba47-0d365621d6e4.json
ingress:
  - hostname: fc.jetwong.top
    service: http://localhost:8088
  - service: http_status:404
EOF

# 自动在 Cloudflare DNS 写一条 CNAME: fc.jetwong.top → <tunnel-id>.cfargotunnel.com
cloudflared tunnel route dns football fc.jetwong.top
```

### 5. 装 systemd 服务

```bash
cloudflared service install     # 会把 /root/.cloudflared/config.yml 复制到 /etc/cloudflared/config.yml
systemctl enable cloudflared
systemctl start cloudflared
```

### 6. 等边缘证书 + 验证

新 zone 的 Universal SSL 证书签发需要几分钟到 1 小时（CA 排队）。CF 后台 SSL/TLS → Edge Certificates 状态变 Active 后：

```bash
ssh mysql-backup 'curl -s -o /dev/null -w "%{http_code}\n" https://fc.jetwong.top/api/health'
# 期望 200
```

## 日常维护操作

### 查看服务状态
```bash
ssh mysql-backup 'systemctl status cloudflared --no-pager'
ssh mysql-backup 'systemctl is-active cloudflared'
```

### 查看隧道实时日志
```bash
ssh mysql-backup 'journalctl -u cloudflared -f --no-pager'
# 或最近 100 行
ssh mysql-backup 'journalctl -u cloudflared -n 100 --no-pager'
```

### 重启隧道（改配置后）
```bash
ssh mysql-backup 'systemctl restart cloudflared'
```

### 修改 ingress（如改内网目标端口）
1. 编辑 `/etc/cloudflared/config.yml` 和 `/root/.cloudflared/config.yml`（两份保持一致）
2. `systemctl restart cloudflared`

> 注意：service 用 `/etc/cloudflared/config.yml`；手动跑 `cloudflared tunnel run` 默认读 `/root/.cloudflared/config.yml`。两份都要改，避免手动运行时配置不一致。

### 查看 Cloudflare 侧隧道状态
- 后台：https://one.dash.cloudflare.com → Networks → Tunnels → `football`
- 可看到连接数、边缘节点、健康状态

### 更换公网域名 / 增加子域名
```bash
# 加一条 hostname 路由
cloudflared tunnel route dns football <新子域名>.jetwong.top
# 然后在 config.yml 的 ingress 里加一条 hostname → service 规则（放在 http_status:404 之前）
systemctl restart cloudflared
```

## 问题排查

### `fc.jetwong.top` 打不开 / 5xx

按顺序排查：

**1. 隧道服务是否在跑**
```bash
ssh mysql-backup 'systemctl is-active cloudflared'
# 不在就 systemctl start cloudflared
```

**2. 内网目标是否在服务**
```bash
ssh mysql-backup 'curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8088/'
# 期望 200；不是 200 说明 football-frontend 容器挂了，docker ps / docker-compose restart
```

**3. 隧道连接是否注册到 CF 边缘**
```bash
ssh mysql-backup 'journalctl -u cloudflared --no-pager | grep -i "Registered tunnel connection" | tail -3'
# 应有最近注册记录；没有看 ERR 行
```

### TLS handshake failure（证书问题）

```bash
ssh mysql-backup 'echo | openssl s_client -connect fc.jetwong.top:443 -servername fc.jetwong.top 2>&1 | grep -iE "subject=|alert"'
```

- 报 `sslv3 alert handshake failure` 且无 `subject=` → 边缘没证书。CF 后台 SSL/TLS → Edge Certificates 看 Universal SSL 是否 Active。
- 证书 Pending Validation(TXT) 超过 30 分钟：检查 CF 后台该证书的 DCV 状态。`dig @1.1.1.1 TXT _acme-challenge.jetwong.top` 应有 TXT 记录（CF 自动加）。通常只是 CA 排队，继续等；超 2 小时联系 CF 支持。
- 主证书迟迟不签时，CF 会自动签一张 backup 证书顶上，状态显示 "backup issued" → active。

### HTTP 404

- 隧道在跑但 ingress 没匹配上 Host：检查 `/etc/cloudflared/config.yml` 的 ingress，`fc.jetwong.top` 那条要在 `http_status:404` 之前。
- 之前踩过的坑：手动跑 `cloudflared tunnel --url ...`（quick tunnel）时会读到命名隧道的 config.yml，catch-all 404 把请求吞掉。临时测试 quick tunnel 时把两个 config.yml 都移走，详见下方「临时 Quick Tunnel」。

### HTTP 530

边缘到隧道的连接未就绪。通常隧道刚启动几秒内、或隧道进程已死但 DNS 还指过来。等几秒或重启 `cloudflared` 服务。

### 速度问题

- Cloudflare 免费版无大陆节点，国内访问走香港/东京/新加坡或美国。晚高峰（20:00-23:00）国际出口拥塞会变慢，电信通常最差。
- 若长期不可接受，考虑国内穿透服务（cpolar 等）或自建 frp（需一台国内公网机器）。

## 临时 Quick Tunnel（紧急访问/测速）

无账号、无域名也能拿到一个临时公网 URL，用于证书故障期间应急或测速：

```bash
# 注意：要先移走命名隧道 config，否则 quick tunnel 会读到 catch-all 404
ssh mysql-backup '
  systemctl stop cloudflared
  mv /etc/cloudflared/config.yml /etc/cloudflared/config.yml.bak
  mv /root/.cloudflared/config.yml /root/.cloudflared/config.yml.bak
  cat > /etc/systemd/system/cf-quick.service <<"EOF"
[Unit]
Description=Cloudflare Quick Tunnel
After=network.target
[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8088
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload && systemctl start cf-quick
  journalctl -u cf-quick --no-pager -o cat | grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" | head -1
'
```

恢复回命名隧道：
```bash
ssh mysql-backup '
  systemctl stop cf-quick && systemctl disable cf-quick && rm /etc/systemd/system/cf-quick.service
  systemctl daemon-reload
  mv /etc/cloudflared/config.yml.bak /etc/cloudflared/config.yml
  mv /root/.cloudflared/config.yml.bak /root/.cloudflared/config.yml
  systemctl start cloudflared
'
```

> Quick Tunnel URL 每次启动随机变，仅临时用，不要当正式入口。

## 升级 cloudflared

```bash
ssh mysql-backup '
  systemctl stop cloudflared
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
  systemctl start cloudflared
  cloudflared --version
'
```

## 相关文件索引

| 路径（mysql-backup） | 用途 |
|---|---|
| `/usr/local/bin/cloudflared` | 二进制 |
| `/etc/cloudflared/config.yml` | service 实际加载的配置 |
| `/root/.cloudflared/config.yml` | CLI 默认读取的配置（与上面保持一致） |
| `/root/.cloudflared/cert.pem` | 账号级 origin 证书（login 产物，管理隧道用） |
| `/root/.cloudflared/<tunnel-id>.json` | 隧道凭证（机密，勿泄露） |
| `/etc/systemd/system/cloudflared.service` | systemd 服务单元 |
| `/tmp/cf-quick.log` | 临时 quick tunnel 日志（如有） |

## 切回 VPS 方案（备选）

若 Cloudflare 速度长期不可接受，可改用 frp + 公网 VPS：
- `ssh config` 里的 `boheyun`（162.211.183.160）或 `gouyun`（38.147.187.103，原穿透 VPS，已过期需确认）作 frps 端
- `mysql-backup` 跑 frpc，反代到 `mysql-backup:8088`
- 速度看 VPS 出口，海外 VPS 与 Cloudflare 同量级，国内 VPS 速度快但要备案

详见 `docs/deploy.md`。
