
import logging

from src.core.workflow import (
    run_workflow,
    resume_workflow,
    continue_approved_workflow
)

from src.core.state import create_initial_state

from src.service.conversation_manager import (
    create_conversation,
    add_user_message
)

from src.storage.conversation_storage import conversation_exists

from src.storage.workflow_storage import (
    claim_task_approval,
    load_workflow_state,
    create_retry_task_atomically
)
logger = logging.getLogger(__name__)


def create_task(
    question,
    conversation_id=None,
    trace_id=None,
    user=None,
    skip_entry_guard=False,
):
    """创建任务并启动工作流，不处理人工审批。

    入口治理：默认执行敏感词拦截并生成 traceId。
    """

    # 0. 入口治理：traceId + 敏感词拦截
    from src.governance.audit import new_trace_id
    from src.governance.entry import guard_entry

    trace_id = trace_id or new_trace_id()

    if not skip_entry_guard:
        passed, _risk, reason = guard_entry(
            question, trace_id=trace_id, task_id=None, actor=user or "user"
        )
        if not passed:
            return {
                "task_id": None,
                "status": "rejected",
                "error": reason,
                "trace_id": trace_id,
            }

    # 1. 没有传入对话 ID，就创建新对话
    if conversation_id is None:
        conversation_id = create_conversation()

    elif not conversation_exists(conversation_id):
        raise ValueError(
            f"对话不存在：{conversation_id}"
        )
    # 2. 创建工作流初始状态
    state = create_initial_state(
        question,
        conversation_id=conversation_id
    )
    state["trace_id"] = trace_id
    state["user"] = user

    logger.info(
        "创建工作流任务 | Task：%s | Conversation：%s",
        state["task_id"],
        conversation_id
    )

    # 3. 保存用户问题
    add_user_message(
        conversation_id,
        state["task_id"],
        question
    )

    # 4. 启动工作流
    result = run_workflow(state)

    return result

def approve_task(task_id):
    """批准 SQL 并恢复工作流"""

    # 1. 原子领取审批权
    state = claim_task_approval(task_id, approved=True)

    if state is None:
        raise ValueError(f"未找到任务：{task_id}")

    if state is False:
        raise ValueError("当前任务已处理或不在等待审批状态，无法重复审批")

    # 2. 恢复工作流
    result = continue_approved_workflow(task_id)

    # 3. 如果任务完成，保存最终回答
    if result["status"] == "completed":
        answer = result.get("report")

        if answer is None and result.get("query_results") is not None:
            import json

            answer = json.dumps(
                result["query_results"],
                ensure_ascii=False,
                default=str
            )

        if answer:
            from src.service.conversation_manager import add_assistant_message

            add_assistant_message(
                result["conversation_id"],
                result["task_id"],
                answer
            )

    return result


def reject_task(task_id):
    """拒绝 SQL 并终止任务"""

    # 原子领取拒绝操作
    state = claim_task_approval(task_id, approved=False)

    if state is None:
        raise ValueError(f"未找到任务：{task_id}")

    if state is False:
        raise ValueError("当前任务已处理或不在等待审批状态，无法重复拒绝")

    return state

def resume_task(task_id):
    """
    恢复执行失败的任务
    """

    logger.info("收到任务恢复请求：%s", task_id)

    result = resume_workflow(task_id)

    if result["status"] == "completed":

        answer = None

        # Analysis 类型：优先使用分析报告
        if result.get("task_type") == "analysis":
            answer = result.get("report")

        # SQL 类型：将查询结果转换成字符串
        elif result.get("task_type") == "sql":
            query_results = result.get("query_results")

            if query_results is not None:
                import json

                answer = json.dumps(
                    query_results,
                    ensure_ascii=False,
                    default=str
                )

        if answer:
            from src.service.conversation_manager import add_assistant_message

            add_assistant_message(
                result["conversation_id"],
                task_id,
                answer
            )

    return result


def retry_task(task_id):
    """
    重新尝试被拒绝的任务。

    使用原始问题创建新任务，不修改原任务状态，
    并通过数据库行锁防止并发重复创建。
    """

    logger.info("收到任务重新尝试请求：%s", task_id)

    # 1. 读取原任务，获取问题和对话 ID
    original_state = load_workflow_state(task_id)

    if original_state is None:
        raise ValueError(f"未找到任务：{task_id}")

    if original_state["status"] != "rejected":
        raise ValueError(
            f"当前任务状态不允许重新尝试：{original_state['status']}"
        )

    question = original_state["question"]
    conversation_id = original_state.get("conversation_id")

    if not conversation_id:
        raise ValueError("原任务缺少 conversation_id，无法重新尝试")

    # 2. 创建一个全新的 State
    new_state = create_initial_state(
        question,
        conversation_id=conversation_id
    )

    # 3. 原子创建任务
    # 如果另一个请求已经创建过，就返回之前创建的任务
    result_state, created = create_retry_task_atomically(
        task_id,
        new_state
    )

    # 4. 只有真正创建新任务的请求才启动工作流
    if not created:
        logger.info(
            "检测到重复 retry 请求，不重复启动工作流 | Task：%s",
            result_state["task_id"]
        )
        return result_state

    # 5. 事务已经提交，释放数据库锁后再启动工作流
    return run_workflow(result_state)
