
import logging
import mysql.connector

from config import DB_CONFIG

logger = logging.getLogger(__name__)


def save_message(conversation_id, task_id, role, content):
    """保存一条对话消息"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            INSERT INTO conversation_messages (
                conversation_id,
                task_id,
                role,
                content
            )
            VALUES (%s, %s, %s, %s)
        """

        values = (
            conversation_id,
            task_id,
            role,
            content
        )

        cursor.execute(sql, values)
        connection.commit()

        logger.info(
            "对话消息保存成功 | Conversation：%s | Role：%s",
            conversation_id,
            role
        )

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("对话消息保存失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()



def get_conversation_history(conversation_id, exclude_task_id=None):
    """读取对话历史，可排除指定任务的消息"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT role, content
            FROM conversation_messages
            WHERE conversation_id = %s
        """

        values = [conversation_id]

        # 排除当前任务，避免当前问题重复进入 LLM
        if exclude_task_id is not None:
            sql += " AND (task_id IS NULL OR task_id != %s)"
            values.append(exclude_task_id)

        sql += " ORDER BY id ASC"

        cursor.execute(sql, tuple(values))
        messages = cursor.fetchall()

        logger.info(
            "对话历史读取成功 | Conversation：%s | 消息数量：%s",
            conversation_id,
            len(messages)
        )

        return messages

    except Exception:
        logger.exception("读取对话历史失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

def conversation_exists(conversation_id):
    """检查对话是否存在"""

    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        sql = """
            SELECT 1
            FROM conversation_messages
            WHERE conversation_id = %s
            LIMIT 1
        """

        cursor.execute(sql, (conversation_id,))

        return cursor.fetchone() is not None

    except Exception:
        logger.exception("检查对话是否存在失败")
        raise

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()