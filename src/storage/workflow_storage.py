
import json
import logging
import uuid
import mysql.connector

from config import DB_CONFIG

logger = logging.getLogger(__name__)

def save_workflow_state(
    state,
    execution_token=None
):
    """
    保存工作流状态。

    执行中的任务必须验证 token 和租约。
    防止旧执行者覆盖新执行者的状态。
    """

    connection = None
    cursor = None

    task_id = state["task_id"]
    status = state["status"]

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        state_json = json.dumps(
            state,
            ensure_ascii=False,
            default=str
        )

        # 执行过程中的状态保存
        if status == "running":

            if not execution_token:
                raise RuntimeError(
                    "保存 running 状态必须提供 execution_token"
                )

            sql = """
                UPDATE workflow_runs
                SET task_type = %s,
                    status = %s,
                    state_json = %s,
                    error = %s
                WHERE task_id = %s
                  AND execution_token = %s
                  AND lease_expires_at > NOW()
                  AND status = 'running'
            """

            values = (
                state.get("task_type"),
                status,
                state_json,
                state.get("error"),
                task_id,
                execution_token
            )

        # 执行结束或进入审批状态
        else:

            if not execution_token:
                raise RuntimeError(
                    "保存工作流最终状态必须提供 execution_token"
                )

            sql = """
                UPDATE workflow_runs
                SET task_type = %s,
                    status = %s,
                    state_json = %s,
                    error = %s,
                    execution_token = NULL,
                    lease_expires_at = NULL
                WHERE task_id = %s
                  AND execution_token = %s
                  AND lease_expires_at > NOW()
                  AND status = 'running'
            """

            values = (
                state.get("task_type"),
                status,
                state_json,
                state.get("error"),
                task_id,
                execution_token
            )

        cursor.execute(sql, values)

        # 如果没有更新记录，说明 token 已失效或租约过期
        if cursor.rowcount != 1:

            connection.rollback()

            raise RuntimeError(
                f"工作流执行权已失效，拒绝保存状态 | Task：{task_id}"
            )

        connection.commit()

        logger.info(
            "工作流状态保存成功 | Task：%s | Status：%s",
            task_id,
            status
        )

    except Exception:
        if connection:
            connection.rollback()

        logger.exception(
            "工作流状态保存失败 | Task：%s",
            task_id
        )

        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


def load_workflow_state(task_id):
    """根据 task_id 读取工作流状态"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT state_json
            FROM workflow_runs
            WHERE task_id = %s
        """

        cursor.execute(sql, (task_id,))
        result = cursor.fetchone()

        if not result:
            logger.warning("没有找到工作流任务：%s", task_id)
            return None

        state = json.loads(result["state_json"])

        logger.info("工作流状态读取成功，task_id=%s", task_id)

        return state

    except Exception:
        logger.exception("工作流状态读取失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def claim_task_resume(task_id):
    """
    原子领取任务恢复权。

    允许：
    1. failed 任务恢复
    2. running 但执行租约已经过期的任务恢复

    拒绝：
    1. 租约仍然有效的 running 任务
    2. pending、completed、awaiting_approval、rejected 等其他状态
    """

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 开启事务，锁定任务记录，防止并发恢复
        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                status,
                state_json,
                (
                    lease_expires_at IS NULL
                    OR lease_expires_at <= NOW()
                ) AS lease_expired
            FROM workflow_runs
            WHERE task_id = %s
            FOR UPDATE
            """,
            (task_id,)
        )

        result = cursor.fetchone()

        # 任务不存在
        if result is None:
            connection.rollback()
            return None

        current_status = result["status"]

        # 判断任务是否允许恢复
        can_resume = (
            current_status == "failed"
            or (
                current_status == "running"
                and bool(result["lease_expired"])
            )
        )

        if not can_resume:
            connection.rollback()

            logger.warning(
                "任务不允许恢复 | Task: %s | Status: %s",
                task_id,
                current_status
            )

            return False

        # 同步更新数据库状态和 JSON 状态
        state = json.loads(result["state_json"])

        state["status"] = "pending"
        state["error"] = None

        state_json = json.dumps(
            state,
            ensure_ascii=False,
            default=str
        )

        # 清除旧执行者的 token 和租约
        cursor.execute(
            """
            UPDATE workflow_runs
            SET status = 'pending',
                state_json = %s,
                execution_token = NULL,
                lease_expires_at = NULL,
                error = NULL
            WHERE task_id = %s
            """,
            (
                state_json,
                task_id
            )
        )

        connection.commit()

        logger.info(
            "任务恢复权领取成功 | Task: %s | 原状态: %s",
            task_id,
            current_status
        )

        return state

    except Exception:
        if connection:
            connection.rollback()

        logger.exception(
            "领取任务恢复权失败 | Task: %s",
            task_id
        )
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def claim_workflow_execution(
    task_id,
    initial_state=None,
    lease_seconds=90
):
    """原子领取工作流执行权"""

    connection = None
    cursor = None
    execution_token = str(uuid.uuid4())

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        connection.start_transaction()

        # 1. 锁定任务
        cursor.execute(
            """
            SELECT status, state_json
            FROM workflow_runs
            WHERE task_id = %s
            FOR UPDATE
            """,
            (task_id,)
        )

        result = cursor.fetchone()

        # 2. 如果是全新任务，先写入初始状态
        if result is None:

            if initial_state is None:
                connection.rollback()
                return None

            cursor.execute(
                """
                INSERT INTO workflow_runs (
                    task_id,
                    question,
                    task_type,
                    status,
                    state_json,
                    error
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    task_id,
                    initial_state["question"],
                    initial_state.get("task_type"),
                    initial_state["status"],
                    json.dumps(
                        initial_state,
                        ensure_ascii=False,
                        default=str
                    ),
                    initial_state.get("error")
                )
            )

            current_status = initial_state["status"]
            current_state = initial_state.copy()

        else:
            current_status = result["status"]
            current_state = json.loads(result["state_json"])

        # 3. running 状态必须检查租约
        if current_status == "running":

            cursor.execute(
                """
                SELECT
                    lease_expires_at IS NOT NULL
                    AND lease_expires_at > NOW()
                    AS lease_valid
                FROM workflow_runs
                WHERE task_id = %s
                """,
                (task_id,)
            )

            lease_result = cursor.fetchone()

            if lease_result["lease_valid"]:
                connection.rollback()

                logger.warning(
                    "任务仍有有效执行租约 | Task：%s",
                    task_id
                )

                return None

        # 4. 只有 pending / failed / 租约过期的 running 可以领取
        elif current_status not in ["pending", "failed"]:
            connection.rollback()

            logger.warning(
                "任务不允许领取执行权 | Task：%s | Status：%s",
                task_id,
                current_status
            )

            return None

        # 5. 更新状态
        current_state["status"] = "running"
        current_state["error"] = None

        state_json = json.dumps(
            current_state,
            ensure_ascii=False,
            default=str
        )

        cursor.execute(
            """
            UPDATE workflow_runs
            SET status = 'running',
                state_json = %s,
                execution_token = %s,
                lease_expires_at = DATE_ADD(
                    NOW(),
                    INTERVAL %s SECOND
                ),
                error = NULL
            WHERE task_id = %s
            """,
            (
                state_json,
                execution_token,
                lease_seconds,
                task_id
            )
        )

        connection.commit()

        logger.info(
            "执行权领取成功 | Task：%s",
            task_id
        )

        return current_state, execution_token

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("执行权领取失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def renew_workflow_lease(
    task_id,
    execution_token,
    lease_seconds=90
):
    """续期工作流租约，只允许当前执行者续期"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            UPDATE workflow_runs
            SET lease_expires_at = DATE_ADD(
                NOW(),
                INTERVAL %s SECOND
            )
            WHERE task_id = %s
              AND execution_token = %s
              AND status = 'running'
              AND lease_expires_at > NOW()
        """

        cursor.execute(
            sql,
            (
                lease_seconds,
                task_id,
                execution_token
            )
        )

        connection.commit()

        renewed = cursor.rowcount == 1

        if renewed:
            logger.debug(
                "工作流租约续期成功 | Task：%s",
                task_id
            )
        else:
            logger.warning(
                "工作流租约续期失败，执行权可能已丢失 | Task：%s",
                task_id
            )

        return renewed

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("工作流租约续期异常")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def verify_workflow_execution(
    task_id,
    execution_token
):
    """验证当前执行者是否仍持有有效执行权"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            SELECT COUNT(*)
            FROM workflow_runs
            WHERE task_id = %s
              AND execution_token = %s
              AND status = 'running'
              AND lease_expires_at > NOW()
        """

        cursor.execute(
            sql,
            (
                task_id,
                execution_token
            )
        )

        result = cursor.fetchone()

        return result[0] == 1

    except Exception:
        logger.exception("执行权验证失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def release_workflow_lease(
    task_id,
    execution_token
):
    """释放当前执行者持有的租约"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            UPDATE workflow_runs
            SET execution_token = NULL,
                lease_expires_at = NULL
            WHERE task_id = %s
              AND execution_token = %s
        """

        cursor.execute(
            sql,
            (
                task_id,
                execution_token
            )
        )

        connection.commit()

        logger.info(
            "执行租约释放 | Task：%s | 是否释放：%s",
            task_id,
            cursor.rowcount == 1
        )

        return cursor.rowcount == 1

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("释放工作流租约失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_conversation_workflow_history(
    conversation_id,
    exclude_task_id=None,
    limit=10
):
    """根据 conversation_id 获取最近的历史工作流任务"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT state_json
            FROM workflow_runs
            WHERE JSON_UNQUOTE(
                JSON_EXTRACT(state_json, '$.conversation_id')
            ) = %s
        """

        values = [conversation_id]

        if exclude_task_id is not None:
            sql += " AND task_id != %s"
            values.append(exclude_task_id)

        # 先获取最近的历史任务
        sql += """
            ORDER BY created_at DESC
            LIMIT %s
        """

        values.append(limit)

        cursor.execute(sql, tuple(values))
        results = cursor.fetchall()

        # 解析 JSON
        history = [
            json.loads(row["state_json"])
            for row in results
        ]

        # 恢复时间正序，方便后续理解任务发展过程
        history.reverse()

        logger.info(
            "历史工作流任务读取成功 | Conversation：%s | 数量：%s",
            conversation_id,
            len(history)
        )

        return history

    except Exception:
        logger.exception("历史工作流任务读取失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()




def create_retry_task_atomically(original_task_id, new_state):
    """
    原子创建重试任务。

    锁定原任务，防止并发请求重复创建新任务。
    原任务状态保持 rejected。
    """

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        connection.start_transaction()

        # 1. 锁定原任务
        cursor.execute(
            """
            SELECT status, state_json
            FROM workflow_runs
            WHERE task_id = %s
            FOR UPDATE
            """,
            (original_task_id,)
        )

        result = cursor.fetchone()

        if not result:
            raise ValueError(f"未找到任务：{original_task_id}")

        original_state = json.loads(result["state_json"])

        # 2. 检查原任务状态
        if (
            result["status"] != "rejected"
            or original_state.get("status") != "rejected"
        ):
            raise ValueError(
                f"当前任务状态不允许重新尝试：{original_state.get('status')}"
            )

        # 3. 如果已经创建过重试任务，直接返回已有任务
        existing_retry_id = original_state.get("retry_task_id")

        if existing_retry_id:
            cursor.execute(
                """
                SELECT state_json
                FROM workflow_runs
                WHERE task_id = %s
                """,
                (existing_retry_id,)
            )

            existing_result = cursor.fetchone()

            if not existing_result:
                raise RuntimeError(
                    f"原任务记录了重试任务 ID，但新任务不存在：{existing_retry_id}"
                )

            existing_state = json.loads(
                existing_result["state_json"]
            )

            connection.commit()

            logger.info(
                "重试任务已存在，直接返回 | 原任务：%s | 新任务：%s",
                original_task_id,
                existing_retry_id
            )

            return existing_state, False

        # 4. 在原任务中记录新任务 ID
        original_state["retry_task_id"] = new_state["task_id"]

        original_state_json = json.dumps(
            original_state,
            ensure_ascii=False,
            default=str
        )

        cursor.execute(
            """
            UPDATE workflow_runs
            SET state_json = %s
            WHERE task_id = %s
              AND status = 'rejected'
            """,
            (
                original_state_json,
                original_task_id
            )
        )

        if cursor.rowcount != 1:
            raise RuntimeError("原任务重试标记写入失败")

        # 5. 在同一事务中插入新任务
        new_state_json = json.dumps(
            new_state,
            ensure_ascii=False,
            default=str
        )

        cursor.execute(
            """
            INSERT INTO workflow_runs (
                task_id,
                question,
                task_type,
                status,
                state_json,
                error
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                new_state["task_id"],
                new_state["question"],
                new_state.get("task_type"),
                new_state["status"],
                new_state_json,
                new_state.get("error")
            )
        )

        # 6. 提交事务
        connection.commit()

        logger.info(
            "原子创建重试任务成功 | 原任务：%s | 新任务：%s",
            original_task_id,
            new_state["task_id"]
        )

        return new_state, True

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("原子创建重试任务失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


def claim_task_approval(task_id, approved=True):
    """原子更新任务审批状态，防止重复审批"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 开启事务
        connection.start_transaction()

        # 读取任务状态
        cursor.execute(
            """
            SELECT state_json
            FROM workflow_runs
            WHERE task_id = %s
            FOR UPDATE
            """,
            # FOR UPDATE 会对读取到的数据库记录加排他锁。
            # 如果另一个事务也想修改同一条任务记录，就需要等待当前事务
        
            (task_id,)
        )

        result = cursor.fetchone()

        if not result:
            connection.rollback()
            return None

        state = json.loads(result["state_json"])

        # 检查是否仍然等待审批
        if state["status"] != "awaiting_approval":
            connection.rollback()
            return False

        # 更新状态
        state["sql_approved"] = approved
        state["status"] = "pending" if approved else "rejected"

        state_json = json.dumps(
            state,
            ensure_ascii=False,
            default=str
        )

        cursor.execute(
            """
            UPDATE workflow_runs
            SET status = %s,
                state_json = %s
            WHERE task_id = %s
              AND status = 'awaiting_approval'
            """,
            (
                state["status"],
                state_json,
                task_id
            )
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return False

        connection.commit()

        logger.info(
            "任务审批状态原子更新成功 | Task：%s | Status：%s",
            task_id,
            state["status"]
        )

        return state

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("任务审批状态原子更新失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_task_count(status=None, task_type=None, keyword=None):
    """
    获取任务总数，支持状态、任务类型和关键词筛选
    """

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            SELECT COUNT(*)
            FROM workflow_runs
        """

        conditions = []
        values = []

        if status:
            conditions.append("status = %s")
            values.append(status)

        if task_type:
            conditions.append("task_type = %s")
            values.append(task_type)

        if keyword and keyword.strip():
            keyword_pattern = f"%{keyword.strip()}%"

            conditions.append(
                "(task_id LIKE %s OR question LIKE %s)"
            )

            values.extend([
                keyword_pattern,
                keyword_pattern
            ])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        cursor.execute(sql, tuple(values))

        result = cursor.fetchone()

        return result[0]

    except Exception:
        logger.exception("获取任务总数失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_task_list(
    page=1,
    page_size=10,
    status=None,
    task_type=None,
    keyword=None
):
    """
    分页获取任务列表，支持状态、类型和关键词筛选
    """

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        offset = (page - 1) * page_size

        sql = """
            SELECT
                task_id,
                question,
                task_type,
                status,
                error,
                created_at,
                updated_at,
                lease_expires_at,
                (
                    lease_expires_at IS NULL
                    OR lease_expires_at <= NOW()
                ) AS lease_expired
            FROM workflow_runs
        """

        conditions = []
        values = []

        if status:
            conditions.append("status = %s")
            values.append(status)

        if task_type:
            conditions.append("task_type = %s")
            values.append(task_type)

        if keyword and keyword.strip():
            keyword_pattern = f"%{keyword.strip()}%"

            conditions.append(
                "(task_id LIKE %s OR question LIKE %s)"
            )

            values.extend([
                keyword_pattern,
                keyword_pattern
            ])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += """
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """

        values.extend([page_size, offset])

        cursor.execute(sql, tuple(values))

        tasks = cursor.fetchall()

        logger.info(
            "任务列表读取成功 | Status：%s | Type：%s | Keyword：%s | Page：%s | Count：%s",
            status,
            task_type,
            keyword,
            page,
            len(tasks)
        )

        return tasks

    except Exception:
        logger.exception("任务列表读取失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_dashboard_task_stats(start_time=None, end_time=None):
    """获取 Dashboard 任务数量统计，支持时间筛选"""

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

        # 拼接 WHERE 条件
        where_sql = ""

        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                COUNT(*) AS total_tasks,

                COALESCE(
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                    0
                ) AS completed_tasks,

                COALESCE(
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END),
                    0
                ) AS failed_tasks

            FROM workflow_runs

            {where_sql}
        """

        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()

        total_tasks = result["total_tasks"]
        completed_tasks = result["completed_tasks"]
        failed_tasks = result["failed_tasks"]

        success_rate = (
            completed_tasks / total_tasks
            if total_tasks > 0
            else 0
        )

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": round(success_rate * 100, 2)
        }

    except Exception:
        logger.exception("获取 Dashboard 任务统计失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def get_dashboard_task_trend(start_time=None, end_time=None):
    """获取每日任务量趋势，支持时间筛选"""

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

                COUNT(*) AS total_tasks,

                SUM(
                    CASE
                        WHEN status = 'completed' THEN 1
                        ELSE 0
                    END
                ) AS completed_tasks,

                SUM(
                    CASE
                        WHEN status = 'failed' THEN 1
                        ELSE 0
                    END
                ) AS failed_tasks

            FROM workflow_runs

            {where_sql}

            GROUP BY DATE(created_at)

            ORDER BY date ASC
        """

        cursor.execute(sql, tuple(params))
        results = cursor.fetchall()

        # 将日期转换为字符串，方便 API 返回和前端使用
        for item in results:
            item["date"] = item["date"].strftime("%Y-%m-%d")

        logger.info(
            "Dashboard 每日任务趋势查询成功，共 %s 天",
            len(results)
        )

        return results

    except Exception:
        logger.exception("获取 Dashboard 每日任务趋势失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()