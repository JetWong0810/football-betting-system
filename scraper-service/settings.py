import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# MySQL 数据库配置（仅使用 MySQL）
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "10.130.147.121"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DATABASE", "football_betting"),
    "charset": "utf8mb4",
}

SCHEMA_MYSQL_PATH = BASE_DIR / "schema_mysql.sql"

SPORTTERY_API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry"
POOL_CODES = {
    "had_hhad": "hhad,had",
    "crs": "crs",
    "ttg": "ttg",
    "hafu": "hafu",
}

SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "600"))  # 10分钟
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
USER_AGENT = "football-betting-system/1.0"
