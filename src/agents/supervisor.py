
import json
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def route_task(context, task_id=None):
    """
    根据统一上下文判断任务类型，
    并将当前问题转换为完整、独立的问题。
    """

    current_task = context.get("current_task", {})
    messages = context.get("messages", [])
    task_history = context.get("task_history", [])

    question = current_task.get("question")

    if not question:
        raise ValueError("统一上下文中缺少当前问题")

    # 1. 加入原始对话消息
    conversation_messages = []

    if messages:
        conversation_messages.extend(messages)

    # 2. 整理筛选后的历史任务摘要
    if task_history:
        task_context = []

        for item in task_history:
            task_context.append({
                "task_id": item.get("task_id"),
                "question": item.get("question"),
                "resolved_question": item.get("resolved_question"),
                "task_type": item.get("task_type"),
                "status": item.get("status"),
                "error": item.get("error"),
                "result_count": item.get("result_count")
            })

        conversation_messages.append({
            "role": "system",
            "content": (
                "以下是当前对话中与用户问题相关的历史任务摘要。\n"
                "请结合历史任务理解用户的省略、代词和指代表达，"
                "但不要把历史任务当作当前任务。\n"
                "历史任务可能包含失败或未完成的任务，"
                "不能将其视为已经成功执行的数据结果。\n"
                "历史任务摘要：\n"
                + json.dumps(
                    task_context,
                    ensure_ascii=False,
                    default=str
                )
            )
        })

    # 3. 加入当前问题
    conversation_messages.append({
        "role": "user",
        "content": question
    })

    # 4. 调用 DeepSeek
    response = chat_with_deepseek(
        conversation_messages,
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        agent_name="supervisor",
        task_id=task_id
    )

    # 5. 解析模型返回结果
    try:
        result = json.loads(response)

        task_type = result.get("task_type")
        resolved_question = result.get("resolved_question")

        if task_type not in ["sql", "analysis", "chat"]:
            raise ValueError("模型返回了无效任务类型")

        if not resolved_question:
            raise ValueError("模型没有返回 resolved_question")

        logger.info(
            "任务路由成功：%s | 完整问题：%s",
            task_type,
            resolved_question
        )

        return result

    except (json.JSONDecodeError, ValueError):
        logger.exception("Supervisor 返回格式错误")
        raise
