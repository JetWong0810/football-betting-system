# Football Betting System

竞彩(中国体育彩票)足球预测系统:7 因子方向预测 + 历史同赔分析 + 资金管理。

## 技术栈
- **后端**: FastAPI + PyMySQL + MySQL 8.0(`api-service/`)
- **前端**: UniApp + Vue 3(`frontend/`,H5)
- **抓取**: `scraper-service/`(每 10min 同步在售比赛+赔率)
- **部署**: Docker Compose → mysql-backup 服务器,公网 Cloudflare Tunnel(`fc.jetwong.top`)

## 三服务 + 共享 MySQL
- `football-api`(:7001) / `football-scraper`(循环同步) / `football-frontend`(:8088→nginx) / `football-mysql`(:3321)
- **MySQL 10.130.130.139:3321/football_betting 是共享生产库**——本地直连即写生产,改 DB 需谨慎(用户历史多次要求显式同意)。
- `.env`(`api-service/.env`、`deploy/.env`)含 DB 密码,**已 gitignore,勿提交**。

## 核心数据约定(关键,易踩坑)
- **spf = 胜平负(raw 1x2)**;**nspf = 让球胜平负(handicapped 1x2)**。两套口径不可混。
- **readpl 接口 wtype 反转**(500.com `zx.500.com/jczq/kaijiang.php?step=readpl`):`wtype=nspf` 返回真 spf,`wtype=spf` 返回 nspf。抓 spf 必须用 `wtype=nspf`。
- **亚盘让球符号**:系统统一 **负=主让**(标准亚盘)。`jczq_ah_history.close_handicap` 存标准(负=主让);`matches.asian_handicap` 存 500.com 原值(正=主让,读时取反)。
- **竞彩让球(hhad,整数 ±1/±2)≠ 亚盘让球(小数 ±0.25/±0.5)**。系统预测/盘路分析必须用亚盘,竞彩整数让球无意义。
- 本地 MySQL = 生产 MySQL,所有 DB 写直接影响生产。

## 预测体系
- 竞彩 7 因子(对齐世界杯): F1近期状态 / F2实力定位 / F3市场信号 / F4市场热度 / F5竞彩赔率 / F6历史同赔 / F7单关修正。`predict_service.predict_match`。
- 世界杯版: `wc_predict_service.py`(同构)。
- 历史同赔(F6): `jczq_similar_odds.py`,spf 口径,池 45038 场已完赛(2018-2026)。匹配条件:低赔方±0.03 + 高赔方±0.1(初/终盘) + 同侧 + 方向一致(无变动时降级放行) + 剔除自身。

## 关键文件
| 文件 | 作用 |
|---|---|
| `api-service/predict_service.py` | 预测主逻辑(7因子+置信度) |
| `api-service/jczq_similar_odds.py` | 历史同赔匹配引擎(spf池+find_similar_spf+_ah_outcome) |
| `api-service/main.py` | FastAPI 路由(预测/批量同赔/赛果/同赔查询) |
| `api-service/odds500_service.py` | 500.com 抓取(亚盘/欧赔/fid/score) |
| `api-service/analysis_functions.py` | NL 查询→同赔分析函数 |
| `scraper-service/scraper/sporttery_service.py` | 竞彩官方 API 抓取 |
| `scraper-service/repository.py` | DB 读写(含 spf/nspf 变动记录) |
| `frontend/src/pages/predict/predict.vue` | 预测页(选赛事+7因子+同赔弹窗) |
| `frontend/src/pages/predict/batch-analysis.vue` | 批量同赔分析页(当日/已结束回测) |
| `deploy/deploy-remote.sh` | 部署脚本(ssh+git pull+docker build) |

## 本地开发
`./start-local.sh`(起 API:7001 + Frontend:5173)。`--restart`/`--stop`/`--status`。日志 `logs/`。

## 详细项目知识
按文件自动触发的详细规则在 `.cursor/rules/`(Cursor 自动加载;Claude Code 可按需读):
- `data-conventions.mdc` — spf/nspf + 亚盘符号 + readpl 反转 + 共享 DB 警示
- `jczq-similar-odds.mdc` — 竞彩 7 因子 + 历史同赔匹配(最活跃)
- `prediction-factors.mdc` — 因子架构 + 置信度算法
- `data-sync.mdc` — 数据来源 + fid 坑 + 比分回填
- `fund-management.mdc` — 信心档资金管理
- `f1f2-backtest.mdc` — F1/F2 历史回测
- `reverse-factors-pending.mdc` — 待实现的反向因子设计
- `frontend-conventions.mdc` — 无 emoji + 小圆角 6rpx
- `dev-deploy.mdc` — 本地启动 + 部署流程

## 用户偏好
- 不用 emoji 图标,用文字或 CSS。
- 标签/按钮小圆角(6rpx),不用大圆角 pill。
- 改共享生产表(jczq_odds_history/matches 等)的 UPDATE/DELETE 需显式同意。
- 仅在用户要求时 commit/push;部署须在 main 分支。
