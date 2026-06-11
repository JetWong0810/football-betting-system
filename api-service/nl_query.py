"""自然语言查询 Demo

基于现有数据库，用 LLM 将自然语言转成 SQL 并执行返回结果。
支持两个数据源：
  - MySQL (football_betting): 2026年竞彩比赛、亚盘、赔率
  - SQLite (worldcup_odds.db): 历届世界杯(2014/2018/2022)欧赔、亚盘、大小球

使用方式:
  python nl_query.py "法国vs尼日利亚的盘口数据"          # 默认用 Claude
  python nl_query.py --model deepseek "让球0.5的比赛"   # 用 DeepSeek
  python nl_query.py                                   # 交互模式
"""

import json
import sqlite3
import sys
import os
from pathlib import Path
from typing import Optional, Tuple

import pymysql
import requests
from dotenv import load_dotenv

load_dotenv()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "football_betting"),
    "charset": "utf8mb4",
}

WORLDCUP_DB_PATH = Path(__file__).parent / "data" / "worldcup_odds.db"

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Claude via AWS Bedrock
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
CLAUDE_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

SCHEMA_PROMPT = """你是一个足球数据分析SQL专家。根据用户的自然语言问题，生成正确的 SQL 查询语句。

系统有两个数据库，你需要根据问题判断查询哪一个：

---

## 数据库 A: worldcup (SQLite) — 历届世界杯数据 (2014/2018/2022)
当用户问到"世界杯"、具体世界杯球队对阵、历届大赛数据时，使用此库。

### matches - 比赛表
- id: 比赛ID (主键, INTEGER)
- year: 世界杯年份 (2014/2018/2022)
- match_date: 日期 (如 "2014-06-30")
- match_time: 时间
- stage: 阶段 ("group"=小组赛, "round_of_16"=16强, "quarter"=1/4决赛, "semi"=半决赛, "final"=决赛, "third"=三四名)
- group_name: 小组名 (如 "A"/"B"/NULL)
- home_team: 主队英文名 (如 "France", "Brazil", "Germany")
- away_team: 客队英文名
- home_score: 主队进球
- away_score: 客队进球
- result: 结果 ("H"=主胜, "D"=平, "A"=客胜)
- extra_time: 是否加时 (0/1)
- penalties: 是否点球 (0/1)

### odds_snapshot - 欧赔快照 (多家公司初盘/终盘)
- match_id: 关联 matches.id
- company_name: 公司名 (如 "竞彩官方", "Bet365", "威廉希尔", "澳门", "香港马会")
- odds_home_open: 初盘主胜赔率
- odds_draw_open: 初盘平赔率
- odds_away_open: 初盘客胜赔率
- odds_home_close: 终盘主胜赔率
- odds_draw_close: 终盘平赔率
- odds_away_close: 终盘客胜赔率
- return_rate_open: 初盘返还率
- return_rate_close: 终盘返还率

### odds_movement - 赔率变动历史 (每次变动一条)
- match_id: 关联 matches.id
- company_name: 公司名
- odds_home / odds_draw / odds_away: 该时刻的赔率
- change_time: 变动时间
- direction_home / direction_draw / direction_away: 变动方向

### wc_asian_handicap - 世界杯亚盘数据
- match_id: 关联 matches.id
- company: 公司名 (如 "澳门", "Bet365", "皇冠", "立博")
- initial_home_odds: 初盘主队水位
- initial_handicap: 初盘让球文字描述 (如 "一球", "半球/一球", "球半")
- initial_handicap_value: 初盘让球数值 (如 1.0, 0.75, 1.5)
- initial_away_odds: 初盘客队水位
- close_home_odds: 终盘主队水位
- close_handicap: 终盘让球文字
- close_handicap_value: 终盘让球数值
- close_away_odds: 终盘客队水位

### wc_over_under - 世界杯大小球数据
- match_id: 关联 matches.id
- company: 公司名
- initial_over_odds: 初盘大球水位
- initial_line: 初盘盘口文字 (如 "2.5", "2.5/3")
- initial_line_value: 初盘盘口数值 (如 2.5, 2.75)
- initial_under_odds: 初盘小球水位
- close_over_odds: 终盘大球水位
- close_line: 终盘盘口文字
- close_line_value: 终盘盘口数值
- close_under_odds: 终盘小球水位

---

## 数据库 B: football_betting (MySQL) — 2026年竞彩数据
当用户问到日常联赛(英超/西甲/德甲等)、竞彩、近期比赛时，使用此库。
**重要**: 2026年世界杯的比赛数据也在这个库中 (league_name = '世界杯')，不在 SQLite 世界杯库中！
- 用户提到"今年世界杯"、"2026世界杯"、"即将开始的世界杯"时，应该查这个库
- SQLite 世界杯库只包含 2010/2014/2018/2022 历史数据

### matches - 比赛表
- match_id: 比赛ID VARCHAR (主键)
- league_name: 联赛名称 (如 "英超", "西甲", "德甲")
- match_date: 日期 ("YYYY-MM-DD")
- home_team_name: 主队中文名
- away_team_name: 客队中文名
- home_score / away_score: 进球数
- is_single: 是否单关 (1=是)
- match_status: "finished" / "not_started"

### okooo_asian_odds - 亚盘 (多家公司)
- match_id: 比赛ID
- company: "澳门" / "Bet365" / "威廉希尔" / "Pinnacle"
- initial_home_odds / initial_handicap / initial_away_odds: 初盘
- latest_home_odds / latest_handicap / latest_away_odds: 终盘
- handicap正数=主让, 负数=客让

### odds_win_draw_lose - 竞彩胜平负
- match_id / odds_type ("had"/"hhad") / handicap / win_odds / draw_odds / lose_odds

### jczq_odds_history - 竞彩赔率变动
- match_id / odds_type ("spf"/"nspf") / odds_win / odds_draw / odds_loss / direction_win / direction_draw / direction_loss / change_time

### odds_total_goals - 总进球数
- match_id / goal_range / min_goals / max_goals / odds

---

## 业务术语
- "上盘"=让球方, "下盘"=被让方, "走水"/"走盘"=刚好等于让球数
- 上盘赢盘: 主让时 home_score - away_score > handicap; 客让时 away_score - home_score > |handicap|
- "深盘"=让球>=1, "浅盘"=让球<=0.5, "高水">1.0, "低水"<0.85
- 世界杯球队用英文名(France, Brazil等), 竞彩用中文名

## 输出格式要求
第一行必须输出数据库标识: `-- DB: worldcup` 或 `-- DB: football_betting`
第二行开始是 SQL 语句。

## 规则
1. 只生成 SELECT 语句
2. LIMIT 50
3. worldcup 库用 SQLite 语法, football_betting 库用 MySQL 语法
4. 世界杯球队名用英文: France, Brazil, Germany, Argentina, Spain 等
5. 如果用户提到具体世界杯比赛但用了中文队名，自动转英文
6. 不要包含 ```sql 标记，不要解释
7. **SQLite 限制**: 不能在 UNION ALL 子查询中使用 ORDER BY + LIMIT，要取每组最小值请用 SELECT MIN(id) GROUP BY year 的方式
8. **所有列必须用中文别名** (AS 中文名)，例如: m.year AS '年份', m.home_team AS '主队'
8. **只返回关键字段**，不要返回所有列。用户关心的核心信息优先，去掉 match_id、company_id 等内部字段
9. 世界杯亚盘查询默认只查 company = '澳门'，除非用户指定其他公司或要求对比多家
10. 世界杯大小球查询默认只查 company = '澳门'
11. "揭幕战" = 每届世界杯的第一场比赛 (按 match_date 排序取第一场)
12. 查询结果应该简洁有用：比赛信息 + 盘口/赔率核心数据 + 比分结果
15. **赔率展示默认以竞彩(company_name='竞彩官方')的初盘和终盘为准**，除非用户特别指定其他公司。列名用"初盘主胜/初盘平/初盘客胜/终盘主胜/终盘平/终盘客胜"
16. **初盘和终盘必须成对出现**：只要查了初盘赔率就必须同时返回终盘赔率，只要查了初盘盘口就必须同时返回终盘盘口
13. **同赔/相似赔率查询**: 如果用户想找"与某场比赛赔率相似的历史比赛"，需要分两步思考:
    - 先确定目标比赛的赔率（如果是2026世界杯比赛在MySQL库，历史数据在SQLite库，只能查同一个库内的数据）
    - 如果目标比赛和历史比赛在不同库，则只查询历史库(worldcup)中与用户描述的赔率范围接近的比赛
    - "赔率相似"标准: 初盘低赔 ±0.05~0.1
14. **跨年份世界杯查询**: "今年世界杯"/"2026世界杯" → 查 football_betting (MySQL)；"历届世界杯"/"往届世界杯" → 查 worldcup (SQLite)；如果同时涉及今年和历届，优先查历届(SQLite)并说明

## 常见中英文队名映射
法国=France, 巴西=Brazil, 德国=Germany, 阿根廷=Argentina, 西班牙=Spain,
荷兰=Netherlands, 英格兰=England, 葡萄牙=Portugal, 意大利=Italy, 日本=Japan,
韩国=South Korea, 尼日利亚=Nigeria, 喀麦隆=Cameroon, 克罗地亚=Croatia,
比利时=Belgium, 墨西哥=Mexico, 哥伦比亚=Colombia, 乌拉圭=Uruguay,
瑞士=Switzerland, 哥斯达黎加=Costa Rica, 澳大利亚=Australia, 伊朗=Iran,
沙特阿拉伯=Saudi Arabia, 摩洛哥=Morocco, 塞内加尔=Senegal, 加纳=Ghana,
厄瓜多尔=Ecuador, 卡塔尔=Qatar, 威尔士=Wales, 美国=USA, 加拿大=Canada,
塞尔维亚=Serbia, 丹麦=Denmark, 突尼斯=Tunisia, 波兰=Poland, 秘鲁=Peru,
哥斯达黎加=Costa Rica, 巴拿马=Panama, 冰岛=Iceland, 瑞典=Sweden, 俄罗斯=Russia

用户问题: {question}

输出:"""


def generate_sql_claude(question: str) -> Optional[str]:
    try:
        import anthropic
    except ImportError:
        print("[错误] 需要安装 anthropic 库: pip install anthropic")
        return None

    client = anthropic.AnthropicBedrock(
        aws_access_key=AWS_ACCESS_KEY_ID,
        aws_secret_key=AWS_SECRET_ACCESS_KEY,
        aws_region=AWS_REGION,
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL_ID,
            max_tokens=1500,
            temperature=0,
            messages=[
                {"role": "user", "content": SCHEMA_PROMPT.format(question=question)}
            ],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[Claude 错误] {e}")
        return None


def generate_sql_deepseek(question: str) -> Optional[str]:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": SCHEMA_PROMPT.format(question=question)}
        ],
        "temperature": 0,
        "max_tokens": 1500,
    }

    try:
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[DeepSeek 错误] {e}")
        return None


def generate_sql(question: str, model: str = "claude") -> Optional[str]:
    if model == "claude":
        return generate_sql_claude(question)
    else:
        return generate_sql_deepseek(question)


def parse_response(raw: str) -> Tuple[str, str]:
    """解析 LLM 返回，提取数据库标识和 SQL"""
    lines = raw.strip().split("\n")
    db = "football_betting"
    sql_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-- DB:"):
            db_name = stripped.replace("-- DB:", "").strip().lower()
            if "worldcup" in db_name:
                db = "worldcup"
            else:
                db = "football_betting"
        elif stripped.startswith("```"):
            continue
        else:
            sql_lines.append(line)

    sql = "\n".join(sql_lines).strip()
    return db, sql


def execute_mysql(sql: str):
    conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    except Exception as e:
        return f"[MySQL 执行错误] {e}"
    finally:
        conn.close()


def execute_sqlite(sql: str):
    if not WORLDCUP_DB_PATH.exists():
        return f"[错误] 世界杯数据库不存在: {WORLDCUP_DB_PATH}"
    conn = sqlite3.connect(str(WORLDCUP_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return f"[SQLite 执行错误] {e}"
    finally:
        conn.close()


def execute_sql(db: str, sql: str):
    if db == "worldcup":
        return execute_sqlite(sql)
    else:
        return execute_mysql(sql)


def format_result(rows):
    if isinstance(rows, str):
        return rows
    if not rows:
        return "查询无结果"

    headers = list(rows[0].keys())
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, h in enumerate(headers):
            val = str(row[h]) if row[h] is not None else "-"
            col_widths[i] = max(col_widths[i], len(val.encode("gbk", "replace")))

    lines = []
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "|" + "|".join(f" {str(h):<{col_widths[i]}} " for i, h in enumerate(headers)) + "|"
    lines.append(sep)
    lines.append(header_line)
    lines.append(sep)
    for row in rows:
        vals = [str(row[h]) if row[h] is not None else "-" for h in headers]
        row_line = "|" + "|".join(f" {v:<{col_widths[i]}} " for i, v in enumerate(vals)) + "|"
        lines.append(row_line)
    lines.append(sep)
    lines.append(f"\n共 {len(rows)} 条记录")
    return "\n".join(lines)


def query(question: str, model: str = "claude"):
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print(f"模型: {model.upper()}")
    print(f"{'='*60}")

    print("\n[1/3] 生成 SQL...")
    raw = generate_sql(question, model)
    if not raw:
        print("生成 SQL 失败")
        return

    db, sql = parse_response(raw)
    db_label = "世界杯(SQLite)" if db == "worldcup" else "竞彩(MySQL)"

    print(f"\n[2/3] 数据库: {db_label}")
    print(f"SQL:\n{sql}")

    if not sql.strip().upper().startswith("SELECT"):
        print("\n[安全] 拒绝执行非 SELECT 语句")
        return

    print(f"\n[3/3] 执行查询...")
    result = execute_sql(db, sql)
    output = format_result(result)
    print(f"\n{output}")

    if isinstance(result, str) and "执行错误" in result:
        print("\n[重试] SQL 执行出错，尝试让 AI 修正...")
        retry_q = f"上次SQL执行报错。数据库: {db}, SQL: {sql}, 错误: {result}。请修正。原始问题: {question}"
        raw2 = generate_sql(retry_q, model)
        if raw2:
            _, sql2 = parse_response(raw2)
            if sql2.strip().upper().startswith("SELECT"):
                print(f"\n[重试 SQL]:\n{sql2}")
                result2 = execute_sql(db, sql2)
                print(f"\n{format_result(result2)}")


def interactive_mode(model: str = "claude"):
    print("=" * 60)
    print("  足球数据自然语言查询")
    print(f"  模型: {model.upper()}")
    print("  数据源: 世界杯(2014/2018/2022) + 竞彩(2026)")
    print("  输入 'q' 退出, 's' 切换模型")
    print("=" * 60)

    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("q", "quit", "exit"):
            break
        if question.lower() == "s":
            model = "deepseek" if model == "claude" else "claude"
            print(f"  已切换到: {model.upper()}")
            continue
        query(question, model)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="足球数据自然语言查询")
    parser.add_argument("question", nargs="*", help="查询问题")
    parser.add_argument("--model", "-m", choices=["claude", "deepseek"], default="claude")
    args = parser.parse_args()

    if args.model == "claude" and not AWS_ACCESS_KEY_ID:
        print("错误: 请在 .env 中设置 AWS_ACCESS_KEY_ID")
        sys.exit(1)
    if args.model == "deepseek" and not DEEPSEEK_API_KEY:
        print("错误: 请在 .env 中设置 DEEPSEEK_API_KEY")
        sys.exit(1)

    if args.question:
        query(" ".join(args.question), args.model)
    else:
        interactive_mode(args.model)
