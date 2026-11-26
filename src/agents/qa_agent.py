
import json
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.qa_reviewer import QA_REVIEWER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def review_task(
    question,
    task_type,
    sql=None,
    query_results=None,
    report=None,
    task_id=None
):
    """审核 SQL、查询结果和分析报告"""

    context = {
        "question": question,
        "task_type": task_type,
        "sql": sql,
        "query_results": query_results,
        "report": report
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

    response = chat_with_deepseek(
        messages,
        system_prompt=QA_REVIEWER_SYSTEM_PROMPT,
        agent_name="qa_agent",
        task_id=task_id
    )

    try:
        result = json.loads(response)

        if not isinstance(result.get("passed"), bool):
            raise ValueError("QA 返回的 passed 必须是布尔值")

        if not isinstance(result.get("issues"), list):
            raise ValueError("QA 返回的 issues 必须是列表")

        if not isinstance(result.get("suggestions"), list):
            raise ValueError("QA 返回的 suggestions 必须是列表")

        logger.info("QA 审核完成，通过状态：%s", result["passed"])

        return result

    except (json.JSONDecodeError, ValueError):
        logger.exception("QA 返回格式错误")
        raise
