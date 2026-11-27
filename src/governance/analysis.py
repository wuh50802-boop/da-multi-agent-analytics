"""分析治理：分析规划 + 结果有效性判断 + 空结果友好处理。

对应母版「分析治理」：分析规划 Agent、查询预算守卫、结果有效性判断、空结果处理。
"""
import logging

from src.agents.analysis_planner_agent import plan_analysis as run_analysis_plan
from src.governance.audit import write_audit

logger = logging.getLogger(__name__)


def plan_analysis(question, task_id=None, trace_id=None):
    """分析治理：调用分析规划 Agent，并把计划写入审计。

    Agent 负责模型调用与 JSON 解析；治理层只负责留痕。
    """
    plan = run_analysis_plan(question, task_id=task_id)

    write_audit(
        "execution", f"分析规划：{plan.get('goal', '')[:60]}",
        task_id=task_id, trace_id=trace_id, actor="analysis_planner_agent",
        detail=plan, risk_level="L1",
    )
    logger.info("分析规划治理留痕完成")
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
