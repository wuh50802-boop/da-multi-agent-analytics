
import json
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.report_generator import REPORT_GENERATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def generate_report(question, sql, query_results, task_id=None):
    """根据问题、SQL 和查询结果生成分析报告"""

    context = {
        "用户问题": question,
        "执行的SQL": sql,
        "数据库查询结果": query_results
    }

    messages = [
        {
            "role": "user",
            "content": json.dumps(
                context,
                ensure_ascii=False,
                default=str
            )
        }
    ]

    report = chat_with_deepseek(
        messages,
        system_prompt=REPORT_GENERATOR_SYSTEM_PROMPT,
        agent_name="report_agent",
        task_id=task_id
    )

    logger.info("分析报告生成成功")

    return report
