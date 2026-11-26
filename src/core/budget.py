import logging

from config import MAX_TASK_TOKENS, MAX_TASK_COST_RMB
from src.storage.usage_storage import get_task_usage

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """任务超出 Token 或 API 成本预算"""
    pass

def check_task_budget(task_id):
    """检查任务是否还有剩余预算"""

    usage = get_task_usage(task_id)

    total_tokens = int(usage["total_tokens"])
    total_cost = float(usage["total_cost_rmb"])

    if total_tokens >= MAX_TASK_TOKENS:
        logger.warning(
            "任务 Token 预算超限 | Task：%s | Token：%s",
            task_id,
            total_tokens
        )
        return False

    if total_cost >= MAX_TASK_COST_RMB:
        logger.warning(
            "任务成本预算超限 | Task：%s | 成本：%s",
            task_id,
            total_cost
        )
        return False

    return True