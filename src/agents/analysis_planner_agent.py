import json
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.analysis_planner import ANALYSIS_PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def plan_analysis(question, task_id=None):
    """分析规划 Agent：把用户问题拆成目标/指标/维度/策略的结构化计划。"""

    response = chat_with_deepseek(
        [{"role": "user", "content": question}],
        system_prompt=ANALYSIS_PLANNER_SYSTEM_PROMPT,
        agent_name="analysis_planner_agent",
        task_id=task_id
    )

    try:
        plan = json.loads(response)
    except (json.JSONDecodeError, ValueError):
        logger.warning("分析计划解析失败，使用最小计划")
        plan = {
            "goal": question,
            "metrics": [],
            "dimensions": [],
            "strategy": "直接生成 SQL",
            "feasible": True,
            "note": "计划解析失败",
        }

    logger.info("分析规划完成：feasible=%s", plan.get("feasible"))
    return plan
