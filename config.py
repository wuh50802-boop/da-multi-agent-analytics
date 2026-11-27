
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# RAG 语义模型缓存固定到项目内，避免依赖系统临时目录
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH",
    str(BASE_DIR / "data" / "fastembed_cache")
)

# 读取项目根目录的 .env
load_dotenv(BASE_DIR / ".env")

# 数据源配置：mock_api（本地模拟开放平台） / doudian（真实抖店，需凭证）
DATA_SOURCE = os.getenv("DATA_SOURCE", "mock_api")

# 模拟订单数据文件（模拟 API 服务的底层数据源）
MOCK_ORDERS_FILE = BASE_DIR / "data" / "mock_orders.json"

# 本地模拟开放平台 API
MOCK_API_HOST = os.getenv("MOCK_API_HOST", "127.0.0.1")
MOCK_API_PORT = int(os.getenv("MOCK_API_PORT", "8899"))
MOCK_API_TOKEN = os.getenv("MOCK_API_TOKEN", "demo-token-2026")

# 采集分页大小
COLLECT_PAGE_SIZE = int(os.getenv("COLLECT_PAGE_SIZE", "200"))
COLLECT_MAX_RETRIES = int(os.getenv("COLLECT_MAX_RETRIES", "3"))

# 真实平台凭证（配置后可用 DATA_SOURCE=doudian 切换）
DOUDIAN_APP_KEY = os.getenv("DOUDIAN_APP_KEY")
DOUDIAN_APP_SECRET = os.getenv("DOUDIAN_APP_SECRET")

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

# Agent 允许查询的数据表（电商数仓：ODS/DWD/DIM/DWS/ADS）
ALLOWED_TABLES = [
    "ods_orders_raw",
    "dwd_orders",
    "dim_product",
    "dim_kol",
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

# QA 未通过时最多重写报告的次数（0 表示不返工，直接失败）
MAX_QA_REVISIONS = int(os.getenv("MAX_QA_REVISIONS", "2"))

# ==================== 企业治理配置 ====================
# 敏感字段清单（命中 SQL 时按权限分级拦截）
SENSITIVE_FIELDS = {"用户ID", "收件省份", "收件城市", "原始数据"}
# 管理员白名单（管理员可查询敏感字段；空列表表示仅演示模式全员可查）
ADMIN_USERS = [u.strip() for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]
# 数据范围守卫：SQL 涉及的最大回溯天数（0 表示不限制）
MAX_QUERY_DAYS = int(os.getenv("MAX_QUERY_DAYS", "366"))
# 入口治理：Webhook 签名密钥（为空则跳过校验）
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
# 敏感词拦截（命中即拒绝，防止破坏性操作和批量导出）
SENSITIVE_KEYWORDS = [
    "drop table", "truncate", "delete from", "update ", "alter table",
    "导出手机号", "导出用户", "全部手机号",
]
# ==================== RAG 检索增强配置 ====================
# 切块参数
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# 检索模式：bm25 / vector / hybrid
RAG_DEFAULT_MODE = os.getenv("RAG_DEFAULT_MODE", "hybrid")
RAG_RRF_K = int(os.getenv("RAG_RRF_K", "60"))

# 语义向量模型（首次使用需下载，缓存到 data/fastembed_cache）
RAG_EMBEDDING_MODEL = os.getenv(
    "RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
)

# Chroma 向量数据库（嵌入式持久化，无需单独服务）
RAG_VECTOR_DB_PATH = BASE_DIR / "data" / "chroma_db"
RAG_CHROMA_COLLECTION = os.getenv(
    "RAG_CHROMA_COLLECTION", "rag_chunks"
)