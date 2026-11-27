import json
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.chat import CHAT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def generate_chat_response(context, question, task_id=None):
    """通用对话 Agent：结合统一上下文回答用户问题。

    context 来自 build_workflow_context()，包含对话消息与历史任务摘要；
    历史任务摘要会被并入 system prompt，只用于理解语境，不代表当前任务结果。
    """

    messages = list(context.get("messages", []))
    task_history = context.get("task_history", [])

    system_prompt = CHAT_SYSTEM_PROMPT

    if task_history:
        system_prompt += (
            "\n\n以下是与当前问题相关的历史任务摘要，"
            "仅用于理解对话上下文，不代表当前任务的执行结果：\n"
            + json.dumps(
                task_history,
                ensure_ascii=False,
                default=str
            )
        )

    messages.append({"role": "user", "content": question})

    answer = chat_with_deepseek(
        messages,
        system_prompt=system_prompt,
        agent_name="chat_agent",
        task_id=task_id
    )

    logger.info("通用对话完成")
    return answer
