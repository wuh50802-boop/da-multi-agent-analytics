import logging
import threading

from config import MAX_QA_REVISIONS
from src.core.budget import BudgetExceededError
from src.storage.workflow_storage import (
    load_workflow_state,
    save_workflow_state,
    claim_task_resume,
    claim_workflow_execution,
    renew_workflow_lease,
    verify_workflow_execution,
    release_workflow_lease
)
from src.agents.supervisor import route_task
from src.agents.sql_agent import generate_sql
from src.agents.sql_executor import execute_sql
from src.agents.report_agent import generate_report
from src.agents.qa_agent import review_task
from src.core.retry import retry_call
from src.core.context_manager import (
    build_agent_context,
    limit_context_size
)

logger = logging.getLogger(__name__)

LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20


class WorkflowLeaseLostError(ValueError):
    """工作流执行权丢失或被其他执行者占用"""

class WorkflowHeartbeat:
    """工作流执行期间的自动租约续期"""

    def __init__(self, task_id, execution_token):
        self.task_id = task_id
        self.execution_token = execution_token

        self.stop_event = threading.Event()
        self.lost_event = threading.Event()

        self.thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"heartbeat-{task_id}",
            daemon=True
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def _heartbeat_loop(self):

        while not self.stop_event.wait(HEARTBEAT_SECONDS):

            try:
                renewed = renew_workflow_lease(
                    task_id=self.task_id,
                    execution_token=self.execution_token,
                    lease_seconds=LEASE_SECONDS
                )

                if not renewed:
                    self.lost_event.set()

                    logger.error(
                        "工作流执行权丢失，停止心跳 | Task：%s",
                        self.task_id
                    )

                    return

            except Exception:

                self.lost_event.set()

                logger.exception(
                    "工作流心跳续期异常 | Task：%s",
                    self.task_id
                )

                return


def check_execution_lease(
    task_id,
    execution_token,
    lost_event
):
    """检查执行者是否仍拥有有效执行权"""

    if lost_event.is_set():
        raise WorkflowLeaseLostError(
            f"工作流执行权已丢失：{task_id}"
        )

    valid = verify_workflow_execution(
        task_id,
        execution_token
    )

    if not valid:
        lost_event.set()

        raise WorkflowLeaseLostError(
            f"工作流执行权已失效：{task_id}"
        )


def run_step(
    state,
    step_name,
    func,
    *args,
    execution_token,
    lost_event,
    **kwargs
):
    """执行步骤，持久化结果，支持已完成步骤跳过"""

    logger.info("开始检查步骤：%s", step_name)

    result_fields = {
        "routing": "routing_result",
        "sql_generation": "sql",
        "sql_execution": "query_results",
        "report_generation": "report",
        "qa_review": "qa_result",
        "chat_response": "report"
    }

    if step_name not in result_fields:
        raise ValueError(
            f"未定义步骤结果字段：{step_name}"
        )

    result_field = result_fields[step_name]

    # 1. 检查执行权
    check_execution_lease(
        state["task_id"],
        execution_token,
        lost_event
    )

    # 2. 已完成步骤复用结果
    if (
        state.get("steps", {}).get(step_name) == "completed"
        and state.get(result_field) is not None
    ):

        logger.info(
            "步骤已完成，跳过重复执行：%s",
            step_name
        )

        return state[result_field]

    logger.info("开始执行步骤：%s", step_name)

    # 3. 标记 running
    state["steps"][step_name] = "running"

    save_workflow_state(
        state,
        execution_token=execution_token
    )

    try:

        # 4. 执行实际任务
        result = retry_call(
            func,
            *args,
            **kwargs
        )

        # 5. Agent 执行完后，再次验证执行权
        check_execution_lease(
            state["task_id"],
            execution_token,
            lost_event
        )

        # 6. 保存结果
        state[result_field] = result

        if step_name == "routing":

            state["task_type"] = result["task_type"]
            state["reason"] = result.get("reason")
            state["resolved_question"] = (
                result["resolved_question"]
            )

        state["error"] = None
        state["steps"][step_name] = "completed"

        # 结果与 completed 同一次写入
        save_workflow_state(
            state,
            execution_token=execution_token
        )

        logger.info(
            "步骤执行成功：%s",
            step_name
        )

        return result

    except WorkflowLeaseLostError:
        raise

    except Exception as e:

        # 只有仍持有执行权时，才能写入 failed
        check_execution_lease(
            state["task_id"],
            execution_token,
            lost_event
        )

        state["steps"][step_name] = "failed"
        state["error"] = str(e)

        save_workflow_state(
            state,
            execution_token=execution_token
        )

        logger.exception(
            "步骤执行失败：%s",
            step_name
        )

        raise


def build_workflow_context(state):
    """为当前工作流构建并限制统一上下文"""

    context = build_agent_context(
        task_id=state["task_id"],
        conversation_id=state.get("conversation_id"),
        current_question=(
            state.get("resolved_question")
            or state["question"]
        ),
        task_type=state.get("task_type")
    )

    return limit_context_size(context)


def run_workflow(state):
    """领取执行权后运行工作流，支持租约心跳"""

    task_id = state["task_id"]

    # 1. 原子领取执行权
    claimed = claim_workflow_execution(
        task_id=task_id,
        initial_state=state,
        lease_seconds=LEASE_SECONDS
    )

    if claimed is None:
        raise WorkflowLeaseLostError(
            f"任务已被其他执行者领取或状态不允许执行：{task_id}"
        )

    state, execution_token = claimed

    # 2. 启动心跳线程
    heartbeat = WorkflowHeartbeat(
        task_id,
        execution_token
    )

    heartbeat.start()

    logger.info(
        "工作流启动 | Task：%s",
        task_id
    )

    try:

        # 3. Supervisor 路由
        if state["task_type"] is None:

            routing = state.get("routing_result")

            if routing is None:

                context = build_workflow_context(state)

                routing = run_step(
                    state,
                    "routing",
                    route_task,
                    context=context,
                    task_id=task_id,
                    execution_token=execution_token,
                    lost_event=heartbeat.lost_event
                )

            state["task_type"] = routing["task_type"]
            state["reason"] = routing.get("reason")
            state["resolved_question"] = (
                routing["resolved_question"]
            )

        # 4. SQL / Analysis
        if state["task_type"] in ["sql", "analysis"]:

            # SQL 生成
            if state["sql"] is None:

                state["sql"] = run_step(
                    state,
                    "sql_generation",
                    generate_sql,
                    state["resolved_question"] or state["question"],
                    task_id=task_id,
                    execution_token=execution_token,
                    lost_event=heartbeat.lost_event
                )

            
            # 无法回答的 SQL 不进入审批流程
            if (
                isinstance(state["sql"], str)
                and state["sql"].strip().upper() == "-- CANNOT_ANSWER"
            ):

                check_execution_lease(
                    task_id,
                    execution_token,
                    heartbeat.lost_event
                )

                state["sql"] = None
                state["report"] = (
                    "当前数据源暂时无法回答这个问题。"
                    "目前可用的数据表为 dwd_orders（订单明细表）、"
                    "dws_kol_daily（达人日汇总表）、"
                    "ads_kol_rank（达人月度榜单）和 ods_orders_raw（原始订单快照）。"
                    "请确认问题是否属于电商订单分析范畴。"
                )
                state["status"] = "completed"
                state["error"] = None

                save_workflow_state(
                    state,
                    execution_token=execution_token
                )

                logger.info(
                    "SQL 无法回答，已返回数据源限制说明 | Task：%s",
                    task_id
                )

                return state


            # 等待审批
            if not state["sql_approved"]:

                check_execution_lease(
                    task_id,
                    execution_token,
                    heartbeat.lost_event
                )

                state["status"] = "awaiting_approval"

                save_workflow_state(
                    state,
                    execution_token=execution_token
                )

                logger.info(
                    "等待 SQL 人工审批 | Task：%s",
                    task_id
                )

                return state

            # SQL 执行
            if state["query_results"] is None:

                state["query_results"] = run_step(
                    state,
                    "sql_execution",
                    execute_sql,
                    state["sql"],
                    execution_token=execution_token,
                    lost_event=heartbeat.lost_event
                )

            # 报告生成 + QA 质检 + 返工闭环
            # 循环体内：生成报告 -> 质检 -> 通过则完成，不通过则带意见重写
            while True:

                # 分析报告（首次生成，或返工后重新生成）
                if (
                    state["task_type"] == "analysis"
                    and state["report"] is None
                ):

                    state["report"] = run_step(
                        state,
                        "report_generation",
                        generate_report,
                        state["resolved_question"] or state["question"],
                        state["sql"],
                        state["query_results"],
                        task_id=task_id,
                        execution_token=execution_token,
                        lost_event=heartbeat.lost_event,
                        revision_notes=state.get("revision_notes")
                    )

                # QA 质检
                if state["qa_result"] is None:

                    state["qa_result"] = run_step(
                        state,
                        "qa_review",
                        review_task,
                        question=(
                            state["resolved_question"]
                            or state["question"]
                        ),
                        task_type=state["task_type"],
                        sql=state["sql"],
                        query_results=state["query_results"],
                        report=state["report"],
                        task_id=task_id,
                        execution_token=execution_token,
                        lost_event=heartbeat.lost_event
                    )

                qa_result = state.get("qa_result") or {}
                qa_passed = qa_result.get("passed") is True

                # 本次质检序号（质检结果存在后才计数）
                attempt = state.get("qa_attempts", 0) + 1

                check_execution_lease(
                    task_id,
                    execution_token,
                    heartbeat.lost_event
                )

                # 质检通过 -> 完成
                if qa_passed:
                    state["qa_attempts"] = attempt
                    state.setdefault("qa_history", []).append({
                        "attempt": attempt,
                        "passed": True,
                        "issues": [],
                        "suggestions": [],
                        "summary": qa_result.get("summary")
                    })

                    state["status"] = "completed"
                    state["error"] = None

                    save_workflow_state(
                        state,
                        execution_token=execution_token
                    )

                    logger.info(
                        "工作流完成 | Task：%s | QA 质检次数：%s",
                        task_id, attempt
                    )

                    return state

                # 质检未通过 -> 记录并判断是否返工
                issues = qa_result.get("issues") or []
                suggestions = qa_result.get("suggestions") or []
                state["qa_attempts"] = attempt

                state.setdefault("qa_history", []).append({
                    "attempt": attempt,
                    "passed": False,
                    "issues": issues,
                    "suggestions": suggestions,
                    "summary": qa_result.get("summary")
                })

                can_revise = (
                    state["task_type"] == "analysis"
                    and state.get("report") is not None
                    and attempt <= MAX_QA_REVISIONS
                )

                if not can_revise:
                    state["status"] = "failed"

                    if issues:
                        detail = "；".join(str(i) for i in issues)
                        state["error"] = (
                            f"QA 质检未通过（已质检 {attempt} 次）：{detail}"
                        )
                    else:
                        state["error"] = (
                            f"QA 质检未通过（已质检 {attempt} 次）"
                        )

                    save_workflow_state(
                        state,
                        execution_token=execution_token
                    )

                    logger.warning(
                        "QA 未通过且不可返工，任务失败 | Task：%s | "
                        "次数：%s | Issues：%s",
                        task_id, attempt, issues
                    )

                    return state

                # 构造质检意见，回喂给报告 Agent
                revision_lines = []
                if issues:
                    revision_lines.append(
                        "质检提出的问题：\n"
                        + "\n".join(
                            f"- {issue}" for issue in issues
                        )
                    )
                if suggestions:
                    revision_lines.append(
                        "质检改进建议：\n"
                        + "\n".join(
                            f"- {suggestion}" for suggestion in suggestions
                        )
                    )
                revision_lines.append(
                    f"这是第 {attempt} 次质检未通过，请基于同一份查询结果"
                    "逐条修正上述问题。"
                )

                state["revision_notes"] = "\n\n".join(revision_lines)

                # 重置报告与质检步骤，强制下一轮重新生成/重新质检
                state["report"] = None
                state["steps"]["report_generation"] = "pending"
                state["qa_result"] = None
                state["steps"]["qa_review"] = "pending"

                save_workflow_state(
                    state,
                    execution_token=execution_token
                )

                logger.info(
                    "QA 未通过，触发第 %s 次返工 | Task：%s",
                    attempt, task_id
                )

        # 5. Chat 任务
        elif state["task_type"] == "chat":

            if state["report"] is None:

                from src.llm_client import chat_with_deepseek

                context = build_workflow_context(state)

                messages = list(
                    context.get("messages", [])
                )

                task_history = context.get(
                    "task_history",
                    []
                )

                if task_history:

                    import json

                    messages.append({
                        "role": "system",
                        "content": (
                            "以下是与当前问题相关的历史任务摘要，"
                            "仅用于理解对话上下文，不代表当前任务的执行结果：\n"
                            + json.dumps(
                                task_history,
                                ensure_ascii=False,
                                default=str
                            )
                        )
                    })

                messages.append({
                    "role": "user",
                    "content": (
                        state["resolved_question"]
                        or state["question"]
                    )
                })

                state["report"] = run_step(
                    state,
                    "chat_response",
                    chat_with_deepseek,
                    messages,
                    agent_name="chat",
                    task_id=task_id,
                    execution_token=execution_token,
                    lost_event=heartbeat.lost_event
                )

            check_execution_lease(
                task_id,
                execution_token,
                heartbeat.lost_event
            )

            state["status"] = "completed"
            state["error"] = None

            save_workflow_state(
                state,
                execution_token=execution_token
            )

            logger.info(
                "Chat 工作流完成 | Task：%s",
                task_id
            )

            return state

        else:

            raise ValueError(
                f"未知任务类型：{state['task_type']}"
            )

    except WorkflowLeaseLostError:

        # 失去执行权时绝不能再写数据库
        logger.error(
            "工作流停止：执行权已丢失 | Task：%s",
            task_id
        )

        state["status"] = "execution_lost"

        return state

    except BudgetExceededError as e:

        check_execution_lease(
            task_id,
            execution_token,
            heartbeat.lost_event
        )

        state["status"] = "budget_exceeded"
        state["error"] = str(e)

        save_workflow_state(
            state,
            execution_token=execution_token
        )

        logger.warning(
            "工作流预算超限 | Task：%s",
            task_id
        )

        return state

    except Exception as e:

        # 异常后确认执行权仍有效
        try:

            check_execution_lease(
                task_id,
                execution_token,
                heartbeat.lost_event
            )

            state["status"] = "failed"
            state["error"] = str(e)

            save_workflow_state(
                state,
                execution_token=execution_token
            )

        except WorkflowLeaseLostError:

            logger.error(
                "异常发生时执行权已经丢失，不写入失败状态 | Task：%s",
                task_id
            )

            state["status"] = "execution_lost"

        except Exception:

            logger.exception(
                "工作流异常状态保存失败 | Task：%s",
                task_id
            )

        logger.exception(
            "工作流执行异常 | Task：%s",
            task_id
        )

        return state

    finally:

        # 6. 关闭心跳
        heartbeat.stop()

        # 7. 释放当前执行者的租约
        try:

            release_workflow_lease(
                task_id,
                execution_token
            )

        except Exception:

            logger.exception(
                "工作流租约清理失败 | Task：%s",
                task_id
            )


def resume_workflow(task_id):
    """并发安全地恢复失败工作流"""

    logger.info(
        "准备恢复工作流任务：%s",
        task_id
    )

    state = claim_task_resume(task_id)

    if state is None:
        raise ValueError(
            f"未找到工作流任务：{task_id}"
        )

    if state is False:
        raise ValueError(
            "当前任务已被恢复，或任务状态不允许恢复"
        )

    logger.info(
        "恢复任务 | Task：%s",
        task_id
    )

    return run_workflow(state)


def continue_approved_workflow(task_id):
    """继续执行已审批的工作流"""

    logger.info(
        "准备继续执行已审批任务：%s",
        task_id
    )

    state = load_workflow_state(task_id)

    if state is None:
        raise ValueError(
            f"未找到工作流任务：{task_id}"
        )

    if state["status"] != "pending":
        raise ValueError(
            f"当前任务不是待执行状态：{state['status']}"
        )

    if not state["sql_approved"]:
        raise ValueError(
            "任务尚未通过 SQL 审批"
        )

    return run_workflow(state)