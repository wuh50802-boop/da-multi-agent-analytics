
import logging
import re

import mysql.connector
from config import (
    DB_CONFIG, 
    MAX_QUERY_ROWS,
    SQL_QUERY_TIMEOUT,
    ALLOWED_TABLES,
    AGENT_DB_CONFIG
    )

logger = logging.getLogger(__name__)


def validate_sql(sql):
    """检查 SQL 是否为允许执行的查询"""

    if not sql or not sql.strip():
        raise ValueError("SQL 不能为空")

    # 去掉首尾空白和末尾分号
    sql = sql.strip().rstrip(";").strip()

    # 只允许以 SELECT 开头
    if not re.match(r"^SELECT\b", sql, re.IGNORECASE):
        raise ValueError("只允许执行 SELECT 查询")

    # 禁止多条 SQL 拼接
    if ";" in sql:
        raise ValueError("不允许执行多条 SQL")

    # 禁止常见危险操作
    forbidden = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|"
        r"TRUNCATE|REPLACE|GRANT|REVOKE|CALL)\b",
        re.IGNORECASE
    )

    if forbidden.search(sql):
        raise ValueError("SQL 包含不允许的操作")
    
        # 检查 SQL 引用的表是否在白名单中
    table_pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?",
        re.IGNORECASE
    )

    tables = table_pattern.findall(sql)

    if not tables:
        raise ValueError("SQL 中没有识别到查询表")

    for table in tables:
        if table.lower() not in [t.lower() for t in ALLOWED_TABLES]:
            raise ValueError(f"不允许查询数据表：{table}")

    return sql


def execute_sql(sql):
    """安全检查后执行 SQL 并返回查询结果"""

    connection = None
    cursor = None

    try:
        sql = validate_sql(sql)

        connection = mysql.connector.connect(**AGENT_DB_CONFIG)

        cursor = connection.cursor(dictionary=True)

        # 设置当前会话的查询执行时间上限
        cursor.execute(
            "SET SESSION MAX_EXECUTION_TIME = %s",
            (SQL_QUERY_TIMEOUT * 1000,)
        )

        # 查询并验证当前会话配置
        cursor.execute(
            "SELECT @@SESSION.max_execution_time AS timeout_ms"
        )

        timeout_result = cursor.fetchone()

        logger.info(
            "当前 MySQL 会话查询超时限制：%s 毫秒",
            timeout_result["timeout_ms"]
        )

        # 执行用户查询
        cursor.execute(sql)
        
        # 最多获取 MAX_QUERY_ROWS + 1 条，用来判断是否超出限制
        results = cursor.fetchmany(MAX_QUERY_ROWS + 1)

        if len(results) > MAX_QUERY_ROWS:
            raise ValueError(
                f"查询结果超过最大限制：{MAX_QUERY_ROWS} 条，"
                "请缩小查询范围"
            )

        logger.info("SQL 执行成功，返回 %s 条记录", len(results))

        return results

    except Exception:
        logger.exception("SQL 执行失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()
