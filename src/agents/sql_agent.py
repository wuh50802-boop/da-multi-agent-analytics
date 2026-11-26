
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.sql_generator import SQL_GENERATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def generate_sql(question, task_id=None):
    """根据用户问题生成 SQL"""

    messages = [
        {
            "role": "user",
            "content": question
        }
    ]

    sql = chat_with_deepseek(
        messages,
        system_prompt=SQL_GENERATOR_SYSTEM_PROMPT,
        agent_name="sql_agent",
        task_id=task_id
    )

    logger.info("SQL 生成成功")

    return sql
