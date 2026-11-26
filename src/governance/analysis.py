"""分析治理：分析规划 + 结果有效性判断 + 空结果友好处理。

对应母版「分析治理」：分析规划 Agent、查询预算守卫、结果有效性判断、空结果处理。
"""
import json
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.analysis_planner import ANALYSIS_PLANNER_SYSTEM_PROMPT
from src.governance.audit import write_audit

logger = logging.getLogger(__name__)


def plan_analysis(question, task_id=None, trace_id=None):
    """生成结构化分析计划（目标/指标/维度/策略）。"""
    response = chat_with_deepseek(
        [{"role": "user", "content": question}],
        system_prompt=ANALYSIS_PLANNER_SYSTEM_PROMPT,
        agent_name="analysis_planner",
        task_id=task_id,
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

    write_audit(
        "execution", f"分析规划：{plan.get('goal', '')[:60]}",
        task_id=task_id, trace_id=trace_id, actor="analysis_planner",
        detail=plan, risk_level="L1",
    )
    logger.info("分析规划完成：feasible=%s", plan.get("feasible"))
    return plan


def format_empty_result(question):
    """空结果的友好提示（不编造数据）。"""
    return (
        f"针对「{question}」的查询没有返回数据。\n\n"
        "可能原因：\n"
        "- 所选时间范围内没有符合条件的订单；\n"
        "- 筛选条件（平台/达人/商品）过于严格。\n\n"
        "建议：放宽时间范围或更换筛选条件后重新提问。"
    )


def check_result_validity(question, query_results, task_id=None, trace_id=None):
    """结果有效性判断：为空时返回友好提示，否则返回 None。"""
    if not query_results:
        write_audit(
            "execution", "查询结果为空，返回友好提示",
            task_id=task_id, trace_id=trace_id, actor="analysis_guard",
            detail={"question": question}, risk_level="L1",
        )
        return format_empty_result(question)
    return None
