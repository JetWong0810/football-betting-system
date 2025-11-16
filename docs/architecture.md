# 系统架构文档

## 📐 架构概览

足球竞彩投注追踪系统采用分布式微服务架构，将数据抓取、API 服务和前端展示分离部署。

## 🏗️ 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                                 │
│                   (浏览器/移动设备)                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTPS
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                    Nginx 反向代理                             │
│          (guiyun: 103.140.229.232:80/443)                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ www.jetwong.top        │  api.football.jetwong.top  │    │
│  │ (静态文件服务)          │  (API 代理)                 │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
             │                               │
       ┌─────┴──────┐                 ┌──────┴──────┐
       │            │                 │             │
       ↓            │                 ↓             │
┌─────────────┐    │          ┌──────────────┐    │
│  静态文件     │    │          │ FastAPI       │    │
│   (H5)       │    │          │  (port 7001)  │    │
│             │    │          │              │    │
│ - Vue 3     │    │          │ - REST API   │    │
│ - UniApp    │    │          │ - Swagger UI │    │
└─────────────┘    │          └──────┬───────┘    │
                   │                 │             │
                   │                 │             │
                   │                 ↓             │
                   │          ┌──────────────┐    │
                   │          │   MySQL      │    │
                   │          │   (3306)     │    │
                   │          │              │    │
                   │          │ - 比赛数据   │    │
                   │          │ - 赔率数据   │    │
                   │          │ - 同步状态   │    │
                   │          └──────┬───────┘    │
                   │                 ↑             │
                   │                 │             │
                   │                 │ TCP:3306    │
                   │                 │             │
┌──────────────────────────────────────────────────────────────┐
│              mysql-backup 服务器                               │
│              (120.133.42.145)                                 │
│  ┌────────────────────────────────────────────────────┐      │
│  │         Docker 容器 (py39-dev)                       │      │
│  │  ┌─────────────────────────────────────────────┐  │      │
│  │  │    数据抓取服务 (Python 3.9)                 │  │      │
│  │  │                                              │  │      │
│  │  │  - 定时执行 (crontab: */10 * * * *)         │  │      │
│  │  │  - HTTP 客户端 (httpx)                      │  │      │
│  │  │  - 数据解析                                  │  │      │
│  │  │  - 数据入库                                  │  │      │
│  │  └───────────────┬──────────────────────────────┘  │      │
│  └──────────────────┼─────────────────────────────────┘      │
└────────────────────┼────────────────────────────────────────┘
                     │
                     │ HTTPS
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                 外部竞彩 API                                  │
│      https://webapi.sporttery.cn/...                         │
│                                                              │
│  - 比赛列表                                                   │
│  - 实时赔率                                                   │
│  - 比赛状态                                                   │
└─────────────────────────────────────────────────────────────┘
```

## 📦 服务划分

### 1. 前端服务 (Frontend Service)

**技术栈**:
- UniApp (Vue 3)
- Vite
- Pinia
- uni-ui

**职责**:
- 用户界面展示
- 用户交互处理
- 状态管理
- API 调用封装

**部署**:
- 服务器: guiyun (103.140.229.232)
- 方式: Nginx 静态文件服务
- 域名: www.jetwong.top

### 2. API 服务 (API Service)

**技术栈**:
- FastAPI 0.121.2
- Uvicorn 0.38.0
- PyMySQL 1.1.2
- APScheduler 3.11.1

**职责**:
- 提供 RESTful API
- 数据库查询
- 业务逻辑处理
- API 文档生成

**部署**:
- 服务器: guiyun (103.140.229.232)
- 方式: Systemd 服务 + Nginx 反向代理
- 端口: 7001 (内部)
- 域名: api.football.jetwong.top

### 3. 抓取服务 (Scraper Service)

**技术栈**:
- Python 3.9
- httpx 0.28.1
- PyMySQL 1.1.2
- Docker

**职责**:
- 定时抓取外部 API
- 数据解析和转换
- 数据持久化
- 同步状态更新

**部署**:
- 服务器: mysql-backup (120.133.42.145)
- 方式: Docker 容器 + Crontab 定时任务
- 频率: 每 10 分钟

### 4. 数据库 (MySQL)

**版本**: MySQL 8.0.43

**职责**:
- 数据持久化
- 数据一致性保证
- 索引优化
- 远程访问支持

**部署**:
- 服务器: guiyun (103.140.229.232)
- 端口: 3306
- 远程访问: 允许来自 mysql-backup 的连接

## 🔄 数据流

### 数据抓取流程

```
1. Crontab 触发
        ↓
2. Docker 容器执行 Python 脚本
        ↓
3. HTTP 请求外部竞彩 API
        ↓
4. 解析 JSON 响应
        ↓
5. 数据转换和验证
        ↓
6. 通过网络连接 MySQL
        ↓
7. UPSERT 数据到数据库
        ↓
8. 更新同步状态
```

### API 请求流程

```
1. 用户浏览器发起请求
        ↓
2. DNS 解析域名
        ↓
3. Nginx 接收请求
        ↓
4. Nginx 反向代理到 FastAPI (7001)
        ↓
5. FastAPI 路由匹配
        ↓
6. 业务逻辑处理
        ↓
7. MySQL 数据库查询
        ↓
8. 数据格式化
        ↓
9. 返回 JSON 响应
        ↓
10. Nginx 返回给客户端
```

### 前端加载流程

```
1. 用户访问 www.jetwong.top
        ↓
2. Nginx 返回 index.html
        ↓
3. 浏览器加载静态资源 (JS/CSS/图片)
        ↓
4. Vue 应用初始化
        ↓
5. 调用 API 获取数据
        ↓
6. 渲染界面
        ↓
7. 用户交互
```

## 🗄️ 数据库设计

### ER 图

```
┌──────────────────┐
│    matches       │  比赛表
├──────────────────┤
│ PK match_id      │──┐
│    match_number  │  │
│    league_name   │  │
│    home_team     │  │
│    away_team     │  │
│    match_date    │  │
│    ...           │  │
└──────────────────┘  │
                      │ 1:N
         ┌────────────┴────────────┬────────────────────┬──────────────────┐
         │                         │                    │                  │
         ↓                         ↓                    ↓                  ↓
┌─────────────────────┐  ┌──────────────────┐ ┌──────────────────┐ ┌───────────────────┐
│ odds_win_draw_lose  │  │odds_correct_score│ │odds_total_goals  │ │odds_half_full_time│
├─────────────────────┤  ├──────────────────┤ ├──────────────────┤ ├───────────────────┤
│ PK,FK match_id      │  │ PK,FK match_id   │ │ PK,FK match_id   │ │ PK,FK match_id    │
│ PK odds_type        │  │ PK result_type   │ │ PK goal_range    │ │ PK half_result    │
│    handicap         │  │ PK home_score    │ │    min_goals     │ │ PK full_result    │
│    win_odds         │  │ PK away_score    │ │    max_goals     │ │    result_label   │
│    draw_odds        │  │    score_label   │ │    odds          │ │    odds           │
│    lose_odds        │  │    odds          │ └──────────────────┘ └───────────────────┘
│    ...              │  └──────────────────┘
└─────────────────────┘

┌──────────────────┐
│  sync_status     │  同步状态表
├──────────────────┤
│ PK id            │
│    last_synced_at│
│    total_matches │
│    total_odds    │
└──────────────────┘
```

### 主要表结构

#### matches (比赛表)

| 字段 | 类型 | 说明 |
|------|------|------|
| match_id | VARCHAR(50) PK | 比赛ID |
| match_number | VARCHAR(20) | 期号 |
| match_code | VARCHAR(10) | 比赛编号 |
| league_name | VARCHAR(100) | 联赛名称 |
| home_team_name | VARCHAR(100) | 主队名称 |
| away_team_name | VARCHAR(100) | 客队名称 |
| match_date | DATE | 比赛日期 |
| match_time | TIME | 比赛时间 |
| match_status | VARCHAR(20) | 比赛状态 |

#### odds_win_draw_lose (胜平负赔率表)

| 字段 | 类型 | 说明 |
|------|------|------|
| match_id | VARCHAR(50) PK | 比赛ID |
| odds_type | VARCHAR(10) PK | 赔率类型 (had/hhad) |
| handicap | DECIMAL(3,1) | 让球数 |
| win_odds | DECIMAL(5,2) | 胜赔率 |
| draw_odds | DECIMAL(5,2) | 平赔率 |
| lose_odds | DECIMAL(5,2) | 负赔率 |

## 🔐 安全架构

### 网络安全

```
                      Internet
                         │
                         │ HTTPS (443)
                         ↓
                    ┌─────────┐
                    │  CDN    │ (可选)
                    └────┬────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ↓                     ↓
      ┌───────────────┐     ┌───────────────┐
      │ www.jetwong   │     │ api.football  │
      │   .top        │     │  .jetwong.top │
      └───────┬───────┘     └───────┬───────┘
              │                     │
              ↓                     ↓
        ┌──────────────────────────────┐
        │         Nginx                │
        │    (SSL/TLS Termination)     │
        └──────────────────────────────┘
              │                     │
              ↓                     ↓
        Static Files          FastAPI (7001)
                                    │
                                    ↓
                              MySQL (localhost)
                                    ↑
                                    │ Port 3306
                                    │ (Firewall: Only mysql-backup)
                            ┌───────┴────────┐
                            │  mysql-backup  │
                            │  Scraper       │
                            └────────────────┘
```

### 安全措施

1. **网络层**
   - 防火墙限制端口访问
   - MySQL 仅允许特定 IP 连接
   - HTTPS 加密传输（推荐）

2. **应用层**
   - CORS 配置
   - API 请求限流
   - SQL 注入防护（参数化查询）
   - XSS 防护

3. **数据层**
   - 数据库用户权限最小化
   - 定期数据备份
   - 敏感数据加密

## 📊 性能优化

### 缓存策略

```
浏览器缓存 (30天)
    ↓
CDN 缓存 (可选)
    ↓
Nginx 静态文件
    ↓
FastAPI 响应
    ↓
MySQL 查询结果
```

### 数据库优化

- 索引优化
- 查询优化
- 连接池
- 慢查询日志

### 前端优化

- 代码分割
- 懒加载
- Gzip 压缩
- 图片优化

## 🔧 可扩展性

### 水平扩展

```
     Load Balancer
          │
    ┌─────┼─────┐
    │     │     │
   API1  API2  API3  (多个 API 实例)
    │     │     │
    └─────┼─────┘
          │
      MySQL Master
          │
    ┌─────┼─────┐
    │     │     │
  Slave1 Slave2 Slave3  (读写分离)
```

### 垂直扩展

- 增加服务器资源 (CPU/内存/磁盘)
- 数据库性能调优
- 缓存层添加 (Redis)

## 📈 监控和日志

### 监控指标

- API 响应时间
- 数据库查询性能
- 服务器资源使用率
- 抓取任务成功率
- 错误日志统计

### 日志系统

```
Application Logs
    ↓
Systemd Journal / File Logs
    ↓
(Optional) ELK Stack / Grafana
    ↓
Alert System
```

## 🔄 持续集成/部署 (CI/CD)

建议的 CI/CD 流程：

```
Git Push
    ↓
GitHub Actions / GitLab CI
    ↓
┌─────────────┬─────────────┬─────────────┐
│             │             │             │
Build Frontend  Build API   Build Scraper
│             │             │             │
└─────────────┴─────────────┴─────────────┘
    ↓
Run Tests
    ↓
Deploy to Production
```

## 📞 相关文档

- [部署文档](./deployment.md)
- [API 服务文档](../api-service/README.md)
- [抓取服务文档](../scraper-service/README.md)
- [前端服务文档](../frontend/README.md)

