
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.sql_generator import SQL_GENERATOR_SYSTEM_PROMPT
from src.governance.metadata import get_schema_context
from config import ALLOWED_TABLES

logger = logging.getLogger(__name__)


def generate_sql(question, task_id=None):
    """根据用户问题生成 SQL。

    优先使用元数据字典中的真实表结构（治理驱动），
    字典未采集时回退到静态提示词。
    """

    system_prompt = SQL_GENERATOR_SYSTEM_PROMPT

    dynamic_schema = get_schema_context(ALLOWED_TABLES)
    if dynamic_schema:
        # 用动态 Schema 替换静态提示词中的可用数据表段落
        marker_start = system_prompt.find("可用数据表：")
        marker_end = system_prompt.find("# Metric Rules")
        if marker_start != -1 and marker_end != -1:
            system_prompt = (
                system_prompt[:marker_start]
                + dynamic_schema + "\n"
                + system_prompt[marker_end:]
            )
            logger.info("SQL 提示词已注入元数据字典 Schema")

    messages = [{"role": "user", "content": question}]

    sql = chat_with_deepseek(
        messages,
        system_prompt=system_prompt,
        agent_name="sql_agent",
        task_id=task_id
    )

    logger.info("SQL 生成成功")
    return sql
