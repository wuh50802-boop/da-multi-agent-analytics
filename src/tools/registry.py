"""工具注册表：分级管理 Agent 可调用的外部能力。

工具分级：
- READ_ONLY：只读工具，SQL 生成阶段（审批前）即可用
- EXECUTION：执行类工具，仅 SQL 审批通过后放开（本演示默认不启用，
  因为真实 SQL 执行由 workflow 的 sql_execution 步骤负责，不能被模型绕过）

每个工具都是 LangChain @tool，可被 bind_tools 暴露给模型。
"""

import logging

from langchain_core.tools import tool

from config import ALLOWED_TABLES
from src.governance.metadata import get_schema_context
from src.governance.rag import retrieve as rag_retrieve

logger = logging.getLogger(__name__)


@tool
def get_table_schema(table_names: str = "") -> str:
    """查询可用于问数的数据表结构（表名、字段、含义）。

    当用户问题涉及不确定该用哪张表、字段名是什么时使用。
    table_names 为逗号分隔的表名；留空则返回全部受管表。
    """
    names = [n.strip() for n in table_names.split(",") if n.strip()]
    tables = names or ALLOWED_TABLES
    context = get_schema_context(tables)
    return context or "元数据字典尚未采集，请先调用 /admin/metadata/sync。"


@tool
def search_business_docs(query: str) -> str:
    """检索企业知识库中的业务口径文档。

    当问题涉及指标定义（如 GMV、净 GMV、退货率）、统计口径、
    业务规则时使用。query 传用户原问题或关键术语。
    """
    if not query:
        return "查询内容为空。"
    try:
        hits = rag_retrieve(query, mode="hybrid")
    except Exception:
        return "知识库检索暂时不可用。"
    if not hits:
        return "知识库中没有相关内容。"
    return "\n".join(
        f"[{i}]《{h.get('title', '')}》：{h.get('content', '')}"
        for i, h in enumerate(hits, start=1)
    )


@tool
def list_allowed_tables() -> str:
    """列出当前允许查询的数据表及其用途摘要。"""
    lines = ["当前可用于问数的数据表："]
    summaries = {
        "dwd_orders": "电商订单明细（一单一行），最常用",
        "dws_kol_daily": "达人日汇总（达人×日期×平台）",
        "ads_kol_rank": "达人月度榜单",
        "dim_product": "商品维表（平台×商品ID）",
        "dim_kol": "达人维表（平台×达人UID）",
        "ods_orders_raw": "原始订单快照，一般不用",
    }
    for name in ALLOWED_TABLES:
        lines.append(f"- {name}：{summaries.get(name, '业务数据表')}")
    return "\n".join(lines)


# 分级注册表
READ_ONLY_TOOLS = [get_table_schema, search_business_docs, list_allowed_tables]

# 执行类工具刻意不注册给模型：
# 真实 SQL 执行由 workflow 的 sql_execution 步骤 + 权限治理 + 人工审批控制，
# 若暴露给模型自主调用，会绕过审批门禁（见方案 C 风险分析）。
EXECUTION_TOOLS = []


def get_tools(stage="pre_approval"):
    """按阶段返回可用工具集。

    stage="pre_approval"：只读工具（SQL 生成阶段）
    stage="post_approval"：预留执行工具入口（当前为空）
    """
    if stage == "post_approval":
        return READ_ONLY_TOOLS + EXECUTION_TOOLS
    return READ_ONLY_TOOLS


def tool_names(stage="pre_approval"):
    return [t.name for t in get_tools(stage)]
