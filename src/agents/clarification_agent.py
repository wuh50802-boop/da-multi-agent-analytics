import logging

from src.llm_client import chat_with_deepseek
from src.prompts.clarification import CLARIFICATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def ask_clarification(question, task_id=None):
    """澄清 Agent：问题信息不足时，说明缺口并给出补充示例。"""

    answer = chat_with_deepseek(
        [{"role": "user", "content": question}],
        system_prompt=CLARIFICATION_SYSTEM_PROMPT,
        agent_name="clarification_agent",
        task_id=task_id
    )

    logger.info("澄清回复生成完成")
    return answer
