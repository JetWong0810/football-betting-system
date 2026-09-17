# BSD 赛前情报抓取方案

日期：2026-09-16
状态：方案，未建表、未接生产写

单一来源：**Bzzoiro Sports Data (BSD)**。竞彩在售场（含日职）的阵容、伤停、球员、教练、场地、近况一律走 BSD。日职 `jp_scraper` / `japan-context` 停用，不再双源合并。

7 因子、竞彩官方赔率、500.com 亚盘、同赔池不动。BSD 只服务「基本面弹窗」这一层，不进 `calc_prediction`。

## 0. 日职旧链路

停用，不再维护：

- `api-service/jp_scraper/`（jleague / ゲキサカ / Open-Meteo）
- `japan_context_service.py`
- `GET /api/predict/{match_id}/japan-context`
- 预测页 / 批量页的 `JapanIntelCard` 内嵌卡

保留（与 BSD 无关）：

- 同赔「仅日本」筛选（`isJapanLeague`，F6 口径）
- 已有 `jp_*` 表：先停写，不 DROP。BSD 稳定后再说是否归档

BSD 覆盖表：J1 阵容/统计 Full 接近 100%。天皇杯等杯赛会稀，空就显示无数据，不回退旧源。

## 1. 目标与非目标

本阶段只把原始数据抓下来、对齐竞彩场次、按时间点存快照。近几场 XI 对照、球员重要性、战意推断、建议文案，**有数据后再做**。

不做：

- 不改 F1–F7
- 不抓 BSD 赔率（与 500.com / 竞彩重复）
- 不抓 shotmap / live WebSocket / 社交
- 不建全球球员百科；只拉本场相关球队
- 不把 Transfermarkt 网页当源

## 2. 抓什么

以「一场竞彩比赛」为单元。匹配成功后拉下面这些；匹配失败只记失败，不编数据。

### 2.1 必抓（P0，弹窗骨架）

| 数据 | BSD | 用途 |
|---|---|---|
| 本场详情 | `GET /api/v2/events/{id}/` | 开球、球场、天气、场地、中立/德比、旅行距离、裁判、双方教练 |
| 本场阵容 | `.../lineups/` | 预计或确认 XI、替补、阵型；看 `lineup_status` |
| 双方伤停 | `GET /api/v2/teams/{id}/squad/` | availability / 伤病 / 预计复出 |
| 双方近 8 场赛程 | `GET /api/v2/teams/{id}/fixtures/` | 已完赛 + 未来，正式比赛，去友谊赛 |
| 近 5 场确认首发 | 每场 `.../lineups/` | XI 对照原料 |
| 相关球员场次日志 | `GET /api/v2/players/{id}/stats/` 近窗 | 分钟、是否首发、进球、xG/xA、评分 |
| 积分榜 | `GET /api/v2/leagues/{id}/season/` → standings | 战意原料（排名、积分差） |

「相关球员」= 本场 XI ∪ 近 5 场曾首发 ∪ 当前伤停名单，每队大约 18–25 人，不要拉全队 40 人。

### 2.2 顺手抓（P1，同一轮，配额够）

| 数据 | BSD | 用途 |
|---|---|---|
| 教练资料 | `GET /api/v2/managers/{id}/` | 惯用阵型、风格、战绩、上任变化 |
| 交锋 | `GET /api/v2/events/{id}/h2h/` | 弹窗备用；500.com 已有一份 |
| 球员资料 | `GET /api/v2/players/{id}/` | 位置、身价、号码；缓存 1 天 |
| BSD 模型 | `GET /api/v2/events/{id}/prediction/` | 仅对照，标签「BSD 模型」 |
| 覆盖探测 | `GET /api/v2/coverage/` | 联赛是否在季、是否有赛 |

### 2.3 暂不抓

- 逐场 shotmap / momentum / 平均站位
- 逐庄家赔率、Weight of Money
- 转会账本、生涯全量
- 裁判逐场牌日志（场次详情里的裁判 id 够用）
- 直播 WebSocket

## 3. 对齐竞彩（先打通再谈准）

BSD 英文名 vs 竞彩中文名，是整条链路的单点。独立映射表，**不改 `matches`**。

```
bsd_team_map     bsd_team_id ↔ 竞彩中文名 / 别名 / 联赛提示
bsd_event_map    bsd_event_id ↔ matches.match_id
bsd_player_map   先只挂 bsd_player_id，中文名后补
```

匹配顺序：

1. 用开球日拉 `GET /api/v2/events/?date_from&date_to`
2. 已有 `bsd_event_map` 直接用
3. 否则：开球 ±3h + 主客队都在 `bsd_team_map` 命中
4. 否则：队名模糊（别名、简繁、英文包含）+ 人工确认队列
5. 对不上：`bsd_sync_log` 记 unmatched，弹窗「无 BSD 数据」

冷启动：先对近几日在售场跑 dry-run，打印 BSD 队名 vs 竞彩队名，手工种子高频队（五大、日职、中超、北欧）。不追求一次全覆盖。

日职同样走这套映射，不走 `jp_clubs`。

## 4. 怎么存（先原始，后结构化）

独立域 `bsd_*`，不碰 `jczq_odds_history` / `matches` 赔率字段。本地 MySQL = 生产，**建表须你显式同意后再执行**。

建议表（v1）：

| 表 | 作用 |
|---|---|
| `bsd_http_cache` | `endpoint + resource_id` 最新 JSON + `fetched_at` + http status。逻辑层只读这里 |
| `bsd_event_map` / `bsd_team_map` | 对齐 |
| `bsd_match_snapshot` | 某 `match_id` + `stage` 的组装包（后面弹窗用）。本阶段可先空，或只存引用 |
| `bsd_sync_log` | 日期、场次、成功/未匹配/429、耗时、请求数 |

v1 **不**拆 `player_match_logs` 宽表。原始 JSON 进 cache 即可，对照表/重要性有实样后再抽列。

缓存 TTL（写 cache 时遵守，避免烧配额）：

| 资源 | TTL |
|---|---|
| events 列表 / 场次详情 | 30 min；开赛前 6h 内 10 min |
| lineups | `predicted` 30 min；开赛前 2h 每 15 min；`confirmed` 后不再刷 |
| squad 伤停 | 2h；开赛前 6h 每 1h |
| 近况 fixtures | 6h |
| 历史场 lineups / player stats | 24h（已完赛不变） |
| 球员资料 / 教练 | 24h |
| standings | 12h |

超 TTL 才打 BSD；429 记 log，等 `Retry-After`。

## 5. 何时抓

不进 scraper 10min 赔率环。独立 CLI，和 `jp_scraper.sync` 同位置：`api-service` 模块。

按竞彩在售、未完赛场调度：

| 阶段 | 何时 | 拉什么 |
|---|---|---|
| T-48h | 开球前 48h 内首次入窗 | 全量 P0+P1 |
| T-24h | 前 24h | 伤停、预计阵容、天气、积分 |
| T-6h | 前 6h | 伤停、预计阵容、近况 |
| T-75m | 前 2h 起每 15min | **只刷 lineups**，直到 `confirmed` 或开球 |
| 每日一次 | UTC 清晨 | 当日+次日在售场补匹配；刷 standings |

配额（免费 7500/天，热列表另有 25rps）：

粗算一天 40 场竞彩、约 70 支不重复队：

- 场次列表 + 详情 + 本场阵容 ≈ 100
- 70 ×（squad + fixtures + manager）≈ 210
- 40 × 2 × 5 场历史阵容，命中 cache 后增量很少；冷启动 ≈ 400
- 相关球员 stats 冷启动 ≈ 1500，之后按 TTL 几乎不重复

冷启动一天大约 2000–3500，日常刷新 800–1500。不要全量 8900 球员。

## 6. 代码放哪

新建 `api-service/bsd_intel/`，对标旧 `jp_scraper` 的目录职责，但只谈 BSD：

```
bsd_intel/
  client.py      token、429、RateLimit 头
  sync.py        CLI：--date --apply --dry-run --limit
  map.py         队名/场次对齐
  cache.py       读写 bsd_http_cache
  schema.sql     bsd_* 建表（apply 前须同意）
```

密钥：`api-service/.env` 的 `BSD_API_TOKEN`（已 gitignore）。文档里的 token 头是 `Authorization: Token …`。

CLI 示例（未实现，作为接口约定）：

```bash
cd api-service
python3 -m bsd_intel.sync --date 2026-09-16 --dry-run    # 只打印匹配，不写库
python3 -m bsd_intel.sync --date 2026-09-16 --apply       # 抓并写入 bsd_*
python3 -m bsd_intel.sync --kickoff-soon --apply          # 只刷 2h 内阵容
```

`--apply` 才写库。默认 dry-run。

## 7. 实施顺序

1. **探测（不写库）**  
   注册 BSD token。对 2–3 场在售竞彩（建议：五大 1、日职或中超 1、北欧/小联赛 1）打 P0 接口，把 JSON 样例落到 `docs/bsd-samples/`（可脱敏）。确认：J1 有没有阵容、伤停字段、近 5 场 lineups、球员 stats 是否含分钟/xG。

2. **映射 dry-run**  
   拉当日 BSD events 列表，和竞彩 `matches` 对打印。种子 30–50 支高频队。看匹配率，不追求 100%。

3. **建表 + 缓存抓取**（要你同意写生产库）  
   落地 `bsd_*`，CLI `--apply` 按日抓 P0。只保证 cache 里有 JSON。

4. **只读接口**  
   `GET /api/predict/{match_id}/intel` 把 cache 原样或轻组装返回。前端先能打开弹窗看生数据也行。

5. **再细化逻辑**（本方案之后）  
   XI 对照矩阵、主力/轮换、伤停 impact、战意证据、建议文案、预测页「基本面」弹窗。

6. **拆日职 UI**  
   新弹窗能展示日职场后，删 `JapanIntelCard` 内嵌、`japan-context` 路由；同赔日本筛选保留。

## 8. 质量

- 每条 cache 必须有 `fetched_at`。弹窗用快照时间，不用「现在库里的最新伤停」回放历史。
- `lineup_status=predicted` 必须原样保留，逻辑层以后才当预计。
- 历史场 `lineups: null` 跳过该列，不要用友谊赛或空列充 5 场。
- 未匹配场次允许为空，禁止用队名去别的联赛猜一场。
- 日职不再调用 jleague/gekisaka；BSD 缺字段就缺。

## 9. 探测结果（2026-09-16，只读、未建表）

Token 已放 `api-service/.env`（gitignore）。接口可用。

字段实样（西甲贝蒂斯、日职福冈、中超浙江）：

- 未开赛阵容 `predicted` + 阵型 + `ai_score`；已完赛可拿到 `confirmed`
- 伤停在 `lineups.unavailable_players` 和 squad；五大有，日职/中超本次抽到的名单全是 available
- 球员有 `market_value_eur`、每场 `minutes_played` / `expected_goals` / `expected_assists`
- 教练、球场要拿 `home_coach_id` / `venue_id` 再打一次
- `fixtures/?status=finished` 不可用，改 `date_from/date_to`

映射 dry-run（未来 6 天竞彩 25 场 vs BSD 564 场，开球 ±30min + 中文种子）：

- **22/25 = 88%** 对上，西甲/欧罗巴/解放者杯/巴甲/英联赛杯均可
- 未匹配：亚运男足、亚运女足（BSD 无此赛事）；欧罗巴「格风暴 vs 雷恩」（BSD 有 Sturm Graz vs Stade Rennais，缺「格风暴=Sturm」这条别名）
- 竞彩简称必须进种子：`巴萨` `拉科` `比利亚雷` `莱万特`。停用词不能吃掉 `athletic` / `club`
- 同时刻多场欧战必须**主客都命中**，单边 0.95 会串场

下一步要写库时才建 `bsd_*` + `bsd_team_map` 种子。

## 10. 你需要拍板的两件事

1. **同意后才 `CREATE TABLE bsd_*`**（生产库）。
2. token 已在 `.env`。若 dashboard 截图外传，去 BSD 后台 Regenerate 再改 `.env`。
