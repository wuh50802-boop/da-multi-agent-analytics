
import json
import logging
import re

from ..storage.workflow_storage import get_conversation_workflow_history
from ..storage.conversation_storage import get_conversation_history

logger = logging.getLogger(__name__)


def retrieve_recent_messages(
    conversation_id,
    exclude_task_id=None,
    limit=20
):
    """
    获取当前会话最近的原始对话消息。

    只读取历史消息，排除当前任务，避免当前问题重复进入上下文。
    """

    if not conversation_id:
        return []

    try:
        messages = get_conversation_history(
            conversation_id=conversation_id,
            exclude_task_id=exclude_task_id
        )

        messages = messages or []

        # 保留最近的消息
        if limit is not None:
            messages = messages[-limit:]

        logger.info(
            "原始对话检索完成 | Conversation：%s | 数量：%s",
            conversation_id,
            len(messages)
        )

        return messages

    except Exception:
        logger.exception(
            "原始对话检索失败 | Conversation：%s",
            conversation_id
        )
        raise


def retrieve_recent_tasks(
    conversation_id,
    exclude_task_id=None,
    limit=10
):
    """
    获取当前会话最近的历史任务。
    """

    if not conversation_id:
        logger.warning("无法获取历史任务：conversation_id 为空")
        return []

    try:
        tasks = get_conversation_workflow_history(
            conversation_id=conversation_id,
            exclude_task_id=exclude_task_id,
            limit=limit
        )

        logger.info(
            "历史任务检索完成 | Conversation：%s | 数量：%s",
            conversation_id,
            len(tasks)
        )

        return tasks or []

    except Exception:
        logger.exception(
            "历史任务检索失败 | Conversation：%s",
            conversation_id
        )
        raise


def build_task_summaries(tasks):
    """
    将历史工作流任务提炼为简洁摘要。
    """

    summaries = []

    for task in tasks:
        summary = {
            "task_id": task.get("task_id"),
            "question": task.get("question"),
            "resolved_question": task.get("resolved_question"),
            "task_type": task.get("task_type"),
            "status": task.get("status"),
            "error": task.get("error")
        }

        result = task.get("query_results")

        if isinstance(result, list):
            summary["result_count"] = len(result)

        summaries.append(summary)

    logger.info(
        "历史任务摘要构建完成 | 原始任务数：%s | 摘要数：%s",
        len(tasks),
        len(summaries)
    )

    return summaries


def select_context_tasks(
    current_question,
    summaries,
    max_tasks=5
):
    """
    根据当前问题筛选相关历史任务。
    支持关键词匹配和简短追问兜底。
    """

    if not current_question or not summaries:
        return []

    def extract_keywords(text):
        keywords = set()

        english_words = re.findall(
            r"[a-zA-Z0-9_]+",
            text.lower()
        )

        keywords.update(english_words)

        stopwords = {
            "有哪",
            "哪些",
            "什么",
            "怎么",
            "如何",
            "是否",
            "可以",
            "帮我",
            "查询",
            "一下",
            "还有",
            "多少"
        }

        chinese_texts = re.findall(
            r"[\u4e00-\u9fff]+",
            text
        )

        for chinese_text in chinese_texts:
            for i in range(len(chinese_text) - 1):
                keyword = chinese_text[i:i + 2]

                if keyword not in stopwords:
                    keywords.add(keyword)

        return keywords

    current_keywords = extract_keywords(current_question)

    scored_tasks = []

    for index, task in enumerate(summaries):

        historical_question = (
            task.get("resolved_question")
            or task.get("question")
            or ""
        )

        historical_keywords = extract_keywords(
            historical_question
        )

        common_keywords = current_keywords & historical_keywords

        score = len(common_keywords)

        # 重新尝试时，原始问题与历史被拒绝任务的问题完全一致。
        # 优先保留该任务，不让它仅因关键词匹配失败而被过滤。
        if (
            task.get("status") == "rejected"
            and current_question.strip() == (task.get("question") or "").strip()
        ):
            score += 10000

        if score > 0:
            scored_tasks.append({
                "score": score,
                "index": index,
                "task": task
            })

    # 相关性优先，相同分数时优先选择较新的任务
    scored_tasks.sort(
        key=lambda item: (
            item["score"],
            item["index"]
        ),
        reverse=True
    )

    selected_items = scored_tasks[:max_tasks]

    # 简短追问兜底
    follow_up_patterns = [
        r"那",
        r"呢",
        r"它",
        r"这个",
        r"那个",
        r"还有",
        r"继续",
        r"再",
        r"对比"
    ]

    is_short_follow_up = (
        len(current_question.strip()) <= 30
        and any(
            re.search(pattern, current_question)
            for pattern in follow_up_patterns
        )
    )

    # 没有关键词匹配，但明显属于追问时，保留最近一条历史
    if not selected_items and is_short_follow_up:
        selected_items = [{
            "score": 0,
            "index": len(summaries) - 1,
            "task": summaries[-1]
        }]

    selected_tasks = []

    for item in selected_items:
        task = item["task"]

        selected_tasks.append({
            "task_id": task.get("task_id"),
            "question": task.get("question"),
            "resolved_question": task.get("resolved_question"),
            "task_type": task.get("task_type"),
            "status": task.get("status"),
            "error": task.get("error"),
            "result_count": task.get("result_count")
        })

    logger.info(
        "历史任务筛选完成 | 候选数量：%s | 入选数量：%s",
        len(summaries),
        len(selected_tasks)
    )

    return selected_tasks


def build_agent_context(
    task_id,
    conversation_id,
    current_question,
    task_type=None
):
    """
    构建统一 Agent 上下文。

    messages：原始对话消息。
    task_history：筛选后的历史任务。
    """

    # 1. 获取原始对话
    messages = retrieve_recent_messages(
        conversation_id=conversation_id,
        exclude_task_id=task_id,
        limit=20
    )

    # 2. 获取历史任务
    tasks = retrieve_recent_tasks(
        conversation_id=conversation_id,
        exclude_task_id=task_id,
        limit=10
    )

    # 3. 构建历史任务摘要
    summaries = build_task_summaries(tasks)

    # 4. 筛选相关历史任务
    selected_tasks = select_context_tasks(
        current_question=current_question,
        summaries=summaries,
        max_tasks=5
    )

    # 5. 组装统一上下文
    context = {
        "current_task": {
            "task_id": task_id,
            "conversation_id": conversation_id,
            "question": current_question,
            "task_type": task_type
        },
        "messages": messages,
        "task_history": selected_tasks,
        "metadata": {
            "total_messages": len(messages),
            "selected_messages": len(messages),
            "total_history": len(tasks),
            "selected_tasks": len(selected_tasks)
        }
    }

    logger.info(
        "Agent 上下文构建完成 | Task：%s | 消息：%s | 历史任务：%s",
        task_id,
        len(messages),
        len(selected_tasks)
    )

    return context


def limit_context_size(
    context,
    max_messages=20,
    max_history=5,
    max_chars=4000
):
    """
    限制上下文长度。

    优先保留当前任务，其次保留最近对话消息，
    最后追加相关历史任务。
    """

    current_task = context.get("current_task", {})
    messages = context.get("messages", [])
    task_history = context.get("task_history", [])

    limited_context = {
        "current_task": current_task,
        "messages": [],
        "task_history": [],
        "metadata": context.get("metadata", {}).copy()
    }

    def get_context_size(data):
        return len(
            json.dumps(
                data,
                ensure_ascii=False,
                default=str
            )
        )

    def update_metadata():
        limited_context["metadata"]["selected_messages"] = len(
            limited_context["messages"]
        )

        limited_context["metadata"]["selected_tasks"] = len(
            limited_context["task_history"]
        )

        limited_context["metadata"]["context_truncated"] = (
            len(limited_context["messages"]) < len(messages)
            or len(limited_context["task_history"]) < len(task_history)
        )

        limited_context["metadata"]["size_limit_exceeded"] = (
            get_context_size(limited_context) > max_chars
        )

    # 当前任务必须保留
    if get_context_size(limited_context) > max_chars:
        limited_context["metadata"]["selected_messages"] = 0
        limited_context["metadata"]["selected_tasks"] = 0
        limited_context["metadata"]["context_truncated"] = True
        limited_context["metadata"]["size_limit_exceeded"] = True

        logger.warning("当前任务上下文已超过字符限制")

        return limited_context

    # 优先保留最近的原始对话
    recent_messages = messages[-max(0, max_messages):]

    for message in reversed(recent_messages):
        limited_context["messages"].insert(0, message)

        if get_context_size(limited_context) > max_chars:
            limited_context["messages"].pop(0)
            break

    # 再追加相关历史任务
    candidates = task_history[:max(0, max_history)]

    for task in candidates:
        limited_context["task_history"].append(task)

        if get_context_size(limited_context) > max_chars:
            limited_context["task_history"].pop()
            break

    update_metadata()

    logger.info(
        "Agent 上下文长度控制完成 | 消息：%s | 历史任务：%s | 字符数：%s",
        len(limited_context["messages"]),
        len(limited_context["task_history"]),
        get_context_size(limited_context)
    )

    return limited_context
