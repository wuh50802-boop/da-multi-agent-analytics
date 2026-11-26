
import logging
from uuid import uuid4

from src.storage.conversation_storage import save_message

logger = logging.getLogger(__name__)


def create_conversation():
    """创建一段新的对话"""

    conversation_id = str(uuid4())

    logger.info(
        "创建新对话 | Conversation：%s",
        conversation_id
    )

    return conversation_id


def add_user_message(conversation_id, task_id, content):
    """保存用户消息"""

    save_message(
        conversation_id=conversation_id,
        task_id=task_id,
        role="user",
        content=content
    )


def add_assistant_message(conversation_id, task_id, content):
    """保存 AI 消息"""

    save_message(
        conversation_id=conversation_id,
        task_id=task_id,
        role="assistant",
        content=content
    )
