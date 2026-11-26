"""权限治理：敏感字段拦截、数据范围守卫、管理员白名单。

对应母版「权限治理」+「分析治理」的查询预算守卫部分。
"""
import logging
import re
from datetime import datetime, timedelta

from config import (
    ADMIN_USERS, MAX_QUERY_DAYS, MAX_QUERY_ROWS,
)
from src.governance.metadata import get_sensitive_columns
from src.governance.audit import write_audit

logger = logging.getLogger(__name__)


def check_sql_permission(sql, user=None, trace_id=None, task_id=None):
    """检查 SQL 是否触碰敏感字段或超出数据范围。

    返回 (allowed, reason, risk_level)。
    """
    if not sql:
        return False, "SQL 为空", "L1"

    sensitive_cols = get_sensitive_columns()
    normalized = sql.lower()

    # 1. 敏感字段检查
    hit = [c for c in sensitive_cols if c.lower() in normalized]
    if hit:
        is_admin = user in ADMIN_USERS if user else False
        write_audit(
            "permission", f"敏感字段{'放行' if is_admin else '拦截'}：{','.join(hit)}",
            trace_id=trace_id, task_id=task_id, actor=user or "agent",
            detail={"fields": hit, "is_admin": is_admin},
            risk_level="L2",
        )
        if not is_admin:
            return False, (
                f"查询涉及敏感字段（{'、'.join(hit)}），需要管理员权限"
            ), "L2"

    # 2. 数据范围守卫：回溯天数（从 SQL 中的日期字面量粗略判断）
    if MAX_QUERY_DAYS > 0:
        dates = re.findall(r"'(\d{4})-(\d{2})-(\d{2})'", sql)
        if dates:
            earliest = min(
                datetime(int(y), int(m), int(d)) for y, m, d in dates
            )
            if (datetime.now() - earliest).days > MAX_QUERY_DAYS:
                write_audit(
                    "permission", "数据范围超限：回溯天数超标",
                    trace_id=trace_id, task_id=task_id, actor=user or "agent",
                    detail={"earliest_date": earliest.strftime("%Y-%m-%d"),
                            "max_days": MAX_QUERY_DAYS},
                    risk_level="L2",
                )
                return False, (
                    f"查询时间范围超过 {MAX_QUERY_DAYS} 天限制"
                ), "L2"

    # 3. 行数守卫（提示性，实际 LIMIT 由 sql_executor 强制）
    if re.search(r"\bselect\s+\*", normalized) and not re.search(r"\blimit\b", normalized):
        logger.info("查询使用 SELECT * 且无 LIMIT，执行器将强制限制 %s 行", MAX_QUERY_ROWS)

    write_audit(
        "permission", "SQL 权限校验通过",
        trace_id=trace_id, task_id=task_id, actor=user or "agent",
        detail={"sensitive_fields": hit}, risk_level="L1",
    )
    return True, None, "L1"


def mask_sensitive_value(value, column_name):
    """输出脱敏：敏感字段值打码（简单实现，供结果展示层使用）。"""
    if column_name in get_sensitive_columns() and value:
        text = str(value)
        if len(text) <= 4:
            return "*" * len(text)
        return text[:2] + "*" * (len(text) - 4) + text[-2:]
    return value
