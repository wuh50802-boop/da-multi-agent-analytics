"""元数据字典自动采集。

参考母版：从 information_schema 采集业务表结构，ON DUPLICATE KEY UPDATE 幂等同步，
为 Text-to-SQL Agent 提供结构化 Schema 上下文。
"""
import logging

import mysql.connector

from config import DB_CONFIG, SENSITIVE_FIELDS

logger = logging.getLogger(__name__)

# 纳入治理的业务表（与 ALLOWED_TABLES 保持一致）
GOVERNED_TABLES = [
    "ods_orders_raw", "dwd_orders", "dim_product", "dim_kol",
    "dws_kol_daily", "ads_kol_rank",
]


def _connect():
    return mysql.connector.connect(**DB_CONFIG)


def sync_metadata():
    """从 information_schema 采集业务表结构，幂等写入 sys_metadata_dict。

    返回本次采集的字段数。
    """
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor()

        placeholders = ", ".join(["%s"] * len(GOVERNED_TABLES))
        sql = f"""
        SELECT
            c.TABLE_NAME,
            t.TABLE_COMMENT,
            c.COLUMN_NAME,
            CASE
                WHEN c.DATA_TYPE IN ('varchar','char')
                    THEN CONCAT(c.DATA_TYPE, '(', c.CHARACTER_MAXIMUM_LENGTH, ')')
                WHEN c.DATA_TYPE IN ('decimal','float','double')
                    AND c.NUMERIC_PRECISION IS NOT NULL
                    THEN CONCAT(c.DATA_TYPE, '(', c.NUMERIC_PRECISION, ',', c.NUMERIC_SCALE, ')')
                ELSE c.DATA_TYPE
            END AS column_type,
            c.COLUMN_COMMENT,
            CASE WHEN c.COLUMN_KEY = 'PRI' THEN 1 ELSE 0 END AS is_pk,
            c.IS_NULLABLE,
            c.ORDINAL_POSITION
        FROM information_schema.COLUMNS c
        LEFT JOIN information_schema.TABLES t
            ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
            AND c.TABLE_NAME = t.TABLE_NAME
        WHERE c.TABLE_SCHEMA = %s
          AND c.TABLE_NAME IN ({placeholders})
        ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
        """
        cursor.execute(sql, (DB_CONFIG["database"], *GOVERNED_TABLES))
        rows = cursor.fetchall()

        insert_sql = """
        INSERT INTO sys_metadata_dict (
            table_name, table_comment, column_name, column_type,
            column_comment, is_pk, is_nullable, column_order,
            security_level, is_sensitive
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            table_comment = VALUES(table_comment),
            column_type = VALUES(column_type),
            column_comment = VALUES(column_comment),
            is_pk = VALUES(is_pk),
            is_nullable = VALUES(is_nullable),
            column_order = VALUES(column_order),
            updated_at = NOW()
        """
        records = []
        for (table, table_comment, col, col_type, col_comment,
             is_pk, nullable, order) in rows:
            sensitive = col in SENSITIVE_FIELDS
            level = "L2" if sensitive else "L1"
            records.append((
                table, table_comment or "", col, col_type or "",
                col_comment or "", is_pk, nullable, order,
                level, 1 if sensitive else 0,
            ))

        if records:
            cursor.executemany(insert_sql, records)
        conn.commit()

        logger.info("元数据采集完成：%s 字段", len(records))
        return len(records)
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("元数据采集失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_schema_context(tables=None):
    """从元数据字典读取表结构，拼成 SQL 提示词可用的 Schema 文本。

    字典为空时返回 None，调用方回退到静态提示词。
    """
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT table_name, table_comment, column_name, column_type, column_comment
        FROM sys_metadata_dict
        """
        values = []
        if tables:
            placeholders = ", ".join(["%s"] * len(tables))
            sql += f" WHERE table_name IN ({placeholders})"
            values.extend(tables)
        sql += " ORDER BY table_name, column_order"

        cursor.execute(sql, tuple(values))
        rows = cursor.fetchall()
        if not rows:
            return None

        # 按表分组
        by_table = {}
        for r in rows:
            by_table.setdefault(r["table_name"], {
                "comment": r["table_comment"], "columns": []
            })
            by_table[r["table_name"]]["columns"].append(
                f"- {r['column_name']}：{r['column_comment'] or r['column_type']}"
            )

        lines = ["# 数据库真实表结构（来自元数据字典，权威来源）", ""]
        for table, info in by_table.items():
            lines.append(f"表名：{table}")
            lines.append(f"含义：{info['comment'] or table}")
            lines.append("字段：")
            lines.extend(info["columns"])
            lines.append("")

        return "\n".join(lines)
    except Exception:
        logger.exception("读取元数据字典失败")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_sensitive_columns():
    """读取标记为敏感的字段清单。"""
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT column_name
            FROM sys_metadata_dict
            WHERE is_sensitive = 1 OR security_level IN ('L2','L3')
        """)
        return {row[0] for row in cursor.fetchall()}
    except Exception:
        logger.exception("读取敏感字段失败")
        return set(SENSITIVE_FIELDS)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
