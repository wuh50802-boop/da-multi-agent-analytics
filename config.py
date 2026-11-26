
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# 读取项目根目录的 .env
load_dotenv(BASE_DIR / ".env")

# 模拟数据源配置（已替代 jsonplaceholder 帖子 API）
MOCK_ORDERS_FILE = BASE_DIR / "data" / "mock_orders.json"

# 文件目录
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "etl.log"

# MySQL 配置
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "multi_agent_db"),
}

AGENT_DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("AGENT_DB_USER", ""),
    "password": os.getenv("AGENT_DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "multi_agent_db"),
}

# DeepSeek API Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# SQL 查询最多返回多少条记录
MAX_QUERY_ROWS = 1000

# SQL 查询超时时间，单位：秒
SQL_QUERY_TIMEOUT = 10

# Agent 允许查询的数据表（电商数仓四层）
ALLOWED_TABLES = [
    "ods_orders_raw",
    "dwd_orders",
    "dws_kol_daily",
    "ads_kol_rank",
]

# DeepSeek API 价格：人民币 / 百万 Token
DEEPSEEK_INPUT_PRICE = 2.0
DEEPSEEK_OUTPUT_PRICE = 8.0

# 每百万 Token
TOKEN_PRICE_UNIT = 1_000_000

# 单个工作流任务的预算限制
MAX_TASK_TOKENS = 100000
MAX_TASK_COST_RMB = 1.0