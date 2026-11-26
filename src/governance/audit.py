"""全链路审计日志。

记录入口/权限/路由/执行/QA/输出各治理事件，供追溯与演示。
"""
import json
import logging
import uuid
from datetime import datetime

import mysql.connector

from config import DB_CONFIG

logger = logging.getLogger(__name__)


def new_trace_id():
    """生成统一链路追踪 ID（入口治理用）。"""
    return f"TR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def write_audit(
    event_type,
    action,
    trace_id=None,
    task_id=None,
    actor="system",
    detail=None,
    risk_level="L1",
):
    """写入一条审计事件。审计失败不影响主流程，只记录告警。"""
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sys_audit_log
                (trace_id, task_id, event_type, actor, action, detail, risk_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            trace_id or "-",
            task_id,
            event_type,
            actor,
            action,
            json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
            risk_level,
        ))
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("审计日志写入失败（不影响主流程）")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def query_audit(trace_id=None, task_id=None, event_type=None, limit=100):
    """查询审计日志，支持按链路/任务/事件类型过滤。"""
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT trace_id, task_id, event_type, actor, action,
                   detail, risk_level, created_at
            FROM sys_audit_log WHERE 1=1
        """
        values = []
        if trace_id:
            sql += " AND trace_id = %s"
            values.append(trace_id)
        if task_id:
            sql += " AND task_id = %s"
            values.append(task_id)
        if event_type:
            sql += " AND event_type = %s"
            values.append(event_type)
        sql += " ORDER BY created_at DESC LIMIT %s"
        values.append(limit)
        cursor.execute(sql, tuple(values))
        rows = cursor.fetchall()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            if r.get("detail"):
                try:
                    r["detail"] = json.loads(r["detail"])
                except (ValueError, TypeError):
                    pass
        return rows
    except Exception:
        logger.exception("审计日志查询失败")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
