
import logging
import mysql.connector

from config import (
    DB_CONFIG,
    DEEPSEEK_INPUT_PRICE,
    DEEPSEEK_OUTPUT_PRICE,
    TOKEN_PRICE_UNIT
)

logger = logging.getLogger(__name__)


def save_usage_log(
    task_id,
    agent_name,
    model_name,
    prompt_tokens,
    completion_tokens,
    total_tokens
):
    """保存一次大模型调用的 Token 使用记录"""
    estimated_cost = (
    prompt_tokens * DEEPSEEK_INPUT_PRICE
    + completion_tokens * DEEPSEEK_OUTPUT_PRICE
) / TOKEN_PRICE_UNIT
    
    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            INSERT INTO llm_usage_logs (
                task_id,
                agent_name,
                model_name,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                input_price_per_million,
                output_price_per_million,
                estimated_cost_rmb
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            task_id,
            agent_name,
            model_name,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            DEEPSEEK_INPUT_PRICE,
            DEEPSEEK_OUTPUT_PRICE,
            estimated_cost
        )

        cursor.execute(sql, values)
        connection.commit()

        logger.info(
            "Token 记录保存成功 | Agent：%s | Token：%s | 估算成本：¥%.8f",
            agent_name,
            total_tokens,
            estimated_cost
        )

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("Token 使用记录保存失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()
            
def get_task_usage(task_id):
    """查询一个任务已经消耗的 Token 和成本"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_cost_rmb), 0) AS total_cost_rmb
            FROM llm_usage_logs
            WHERE task_id = %s
        """

        cursor.execute(sql, (task_id,))
        result = cursor.fetchone()

        return result

    except Exception:
        logger.exception("查询任务 Token 使用量失败")
        raise

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_task_agent_usage(task_id):
    """按 Agent 统计单个任务的 Token 和成本"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT
                agent_name,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(estimated_cost_rmb) AS total_cost_rmb
            FROM llm_usage_logs
            WHERE task_id = %s
            GROUP BY agent_name
            ORDER BY total_tokens DESC
        """

        cursor.execute(sql, (task_id,))

        results = cursor.fetchall()

        logger.info(
            "任务 Agent 消耗统计成功 | Task：%s | Agent 数量：%s",
            task_id,
            len(results)
        )

        return results

    except Exception:
        logger.exception("任务 Agent 消耗统计失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_dashboard_usage_stats(start_time=None, end_time=None):
    """获取 Dashboard 全局 Token 和成本统计，支持时间筛选"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 动态构建时间筛选条件
        conditions = []
        params = []

        if start_time:
            conditions.append("created_at >= %s")
            params.append(start_time)

        if end_time:
            conditions.append("created_at < %s")
            params.append(end_time)

        where_sql = ""

        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_cost_rmb), 0) AS total_cost_rmb
            FROM llm_usage_logs
            {where_sql}
        """

        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()

        return {
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "total_tokens": result["total_tokens"],
            "total_cost_rmb": float(result["total_cost_rmb"])
        }

    except Exception:
        logger.exception("获取 Dashboard Token 和成本统计失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_dashboard_agent_usage_stats(start_time=None, end_time=None):
    """获取 Dashboard 各 Agent 的 Token 和成本统计，支持时间筛选"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 动态构建时间筛选条件
        conditions = []
        params = []

        if start_time:
            conditions.append("created_at >= %s")
            params.append(start_time)

        if end_time:
            conditions.append("created_at < %s")
            params.append(end_time)

        where_sql = ""

        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                agent_name,
                COUNT(*) AS call_count,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_cost_rmb), 0) AS total_cost_rmb
            FROM llm_usage_logs
            {where_sql}
            GROUP BY agent_name
            ORDER BY total_cost_rmb DESC
        """

        cursor.execute(sql, tuple(params))
        results = cursor.fetchall()

        for item in results:
            item["total_cost_rmb"] = float(
                item["total_cost_rmb"] or 0
            )

        logger.info(
            "Dashboard Agent 成本统计成功，共 %s 个 Agent",
            len(results)
        )

        return results

    except Exception:
        logger.exception("获取 Dashboard Agent 统计失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_dashboard_usage_trend(start_time=None, end_time=None):
    """获取每日 Token 和成本趋势，支持时间筛选"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 动态构建时间筛选条件
        conditions = []
        params = []

        if start_time:
            conditions.append("created_at >= %s")
            params.append(start_time)

        if end_time:
            conditions.append("created_at < %s")
            params.append(end_time)

        where_sql = ""

        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                DATE(created_at) AS date,

                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,

                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,

                COALESCE(SUM(total_tokens), 0) AS total_tokens,

                COALESCE(SUM(estimated_cost_rmb), 0) AS total_cost_rmb

            FROM llm_usage_logs

            {where_sql}

            GROUP BY DATE(created_at)

            ORDER BY date ASC
        """

        cursor.execute(sql, tuple(params))
        results = cursor.fetchall()

        # 格式转换，方便 API JSON 序列化
        for item in results:
            item["date"] = item["date"].strftime("%Y-%m-%d")
            item["total_cost_rmb"] = float(
                item["total_cost_rmb"] or 0
            )

        logger.info(
            "Dashboard 每日 Token 趋势查询成功，共 %s 天",
            len(results)
        )

        return results

    except Exception:
        logger.exception("获取 Dashboard 每日 Token 趋势失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()