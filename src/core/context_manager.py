
import json
import logging
import re

from ..storage.workflow_storage import get_conversation_workflow_history
from ..storage.conversation_storage import get_conversation_history

logger = logging.getLogger(__name__)


def estimate_tokens(text):
    """粗估 Token 数（中文约 1.5 token/字，英文约 1.3 token/词）。

    不引入额外依赖，用于上下文裁剪的预算控制。
    精度要求不高——只要能稳定防止上下文超长即可。
    """
    if not text:
        return 0

    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    words = re.findall(r"[a-zA-Z0-9_]+", text)
    others = re.findall(r"[^\u4e00-\u9fff\s]", text)

    return int(
        len(chinese) * 1.5
        + len(words) * 1.3
        + len(others) * 0.5
    )


def inject_knowledge(context, knowledge_hits):
    """把 RAG 检索命中的业务口径注入统一上下文。

    放在 task_history 之后、截断之前，确保 limiter 能按优先级裁剪。
    """
    if not knowledge_hits:
        return context

    blocks = []
    for index, hit in enumerate(knowledge_hits, start=1):
        blocks.append({
            "index": index,
            "title": hit.get("title", ""),
            "content": hit.get("content", ""),
            "score": hit.get("score"),
            "source": hit.get("source"),
        })

    context["knowledge"] = blocks
    context.setdefault("metadata", {})["selected_knowledge"] = len(blocks)

    logger.info(
        "业务口径已注入上下文 | Task：%s | 命中：%s",
        context.get("current_task", {}).get("task_id"),
        len(blocks)
    )
    return context


def format_knowledge_block(context):
    """把上下文中的知识片段格式化为可直接拼入 Prompt 的文本。"""
    knowledge = context.get("knowledge") or []
    if not knowledge:
        return ""

    lines = [
        "以下是与本问题相关的业务口径文档片段，"
        "生成 SQL 时必须优先遵守（如与通用规则冲突，以文档口径为准）：",
    ]
    for item in knowledge:
        lines.append(
            f"[{item['index']}] 《{item['title']}》："
            f"{item['content']}"
        )
    return "\n".join(lines)


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
        "knowledge": [],
        "metadata": {
            "total_messages": len(messages),
            "selected_messages": len(messages),
            "total_history": len(tasks),
            "selected_tasks": len(selected_tasks),
            "selected_knowledge": 0
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
    max_chars=4000,
    max_tokens=3000
):
    """
    限制上下文长度。

    裁剪优先级（从高到低）：
      1. 当前任务（必须保留）
      2. 业务口径知识 knowledge（RAG 命中，SQL 生成强依赖）
      3. 最近对话消息
      4. 相关历史任务摘要

    同时受 max_chars 与 max_tokens 双重约束，任一超限即停止追加。
    """

    current_task = context.get("current_task", {})
    messages = context.get("messages", [])
    task_history = context.get("task_history", [])
    knowledge = context.get("knowledge", [])

    limited_context = {
        "current_task": current_task,
        "messages": [],
        "task_history": [],
        "knowledge": [],
        "metadata": context.get("metadata", {}).copy()
    }

    def serialized(data):
        return json.dumps(data, ensure_ascii=False, default=str)

    def get_context_size(data):
        return len(serialized(data))

    def get_context_tokens(data):
        return estimate_tokens(serialized(data))

    def over_limit():
        return (
            get_context_size(limited_context) > max_chars
            or get_context_tokens(limited_context) > max_tokens
        )

    def update_metadata():
        meta = limited_context["metadata"]
        meta["selected_messages"] = len(limited_context["messages"])
        meta["selected_tasks"] = len(limited_context["task_history"])
        meta["selected_knowledge"] = len(limited_context["knowledge"])
        meta["context_truncated"] = (
            len(limited_context["messages"]) < len(messages)
            or len(limited_context["task_history"]) < len(task_history)
            or len(limited_context["knowledge"]) < len(knowledge)
        )
        meta["estimated_tokens"] = get_context_tokens(limited_context)
        meta["token_limit_exceeded"] = (
            get_context_tokens(limited_context) > max_tokens
        )

    # 1. 当前任务必须保留；超限则只保留任务本身
    if over_limit():
        limited_context["metadata"]["selected_messages"] = 0
        limited_context["metadata"]["selected_tasks"] = 0
        limited_context["metadata"]["selected_knowledge"] = 0
        limited_context["metadata"]["context_truncated"] = True
        limited_context["metadata"]["token_limit_exceeded"] = True
        logger.warning("当前任务上下文已超过限制")
        return limited_context

    # 2. 业务口径优先于对话与历史任务
    for item in knowledge:
        limited_context["knowledge"].append(item)
        if over_limit():
            limited_context["knowledge"].pop()
            break

    # 3. 保留最近的原始对话
    recent_messages = messages[-max(0, max_messages):]

    for message in reversed(recent_messages):
        limited_context["messages"].insert(0, message)
        if over_limit():
            limited_context["messages"].pop(0)
            break

    # 4. 最后追加相关历史任务
    candidates = task_history[:max(0, max_history)]

    for task in candidates:
        limited_context["task_history"].append(task)
        if over_limit():
            limited_context["task_history"].pop()
            break

    update_metadata()

    logger.info(
        "Agent 上下文长度控制完成 | 消息：%s | 历史任务：%s | 口径：%s | 估算 Token：%s",
        len(limited_context["messages"]),
        len(limited_context["task_history"]),
        len(limited_context["knowledge"]),
        limited_context["metadata"].get("estimated_tokens")
    )

    return limited_context
