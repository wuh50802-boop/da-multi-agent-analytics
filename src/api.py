from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, HTTPException
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from src.storage.workflow_storage import (
    load_workflow_state,
    get_task_list,
    get_task_count,
    get_dashboard_task_stats,
    get_dashboard_task_trend
)
from src.service.task_service import (
    create_task,
    approve_task,
    reject_task,
    resume_task,
    retry_task
)
from src.storage.usage_storage import (
    get_task_usage,
    get_task_agent_usage,
    get_dashboard_usage_stats,
    get_dashboard_agent_usage_stats,
    get_dashboard_usage_trend
)
import logging
logger = logging.getLogger(__name__)
app = FastAPI(
    title="Multi-Agent Workflow API",
    description="多智能体数据分析工作流服务",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    """创建任务的请求参数"""

    question: str = Field(
        min_length=1,
        max_length=2000,
        description="用户提出的数据分析问题"
    )

    conversation_id: str | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("问题不能为空或仅包含空格")

        return value


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Multi-Agent API is running"
    }


@app.post("/chat")
def chat(request: ChatRequest):
    """接收用户问题并创建工作流任务"""

    try:
        result = create_task(
            question=request.question,
            conversation_id=request.conversation_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    return {
        "task_id": result["task_id"],
        "conversation_id": result["conversation_id"],
        "status": result["status"],
        "task_type": result["task_type"],
        "sql": result["sql"],
        "reason": result["reason"]
    }

@app.post("/tasks/{task_id}/approve")
def approve_task_api(task_id: str):
    """批准 SQL 并恢复工作流"""

    try:
        result = approve_task(task_id)

        return {
            "task_id": result["task_id"],
            "status": result["status"],
            "sql_approved": result["sql_approved"],
            "query_results": result["query_results"],
            "report": result["report"],
            "error": result["error"]
        }

    except ValueError as e:
        message = str(e)

        if "未找到任务" in message:
            raise HTTPException(status_code=404, detail=message)

        raise HTTPException(status_code=409, detail=message)


@app.post("/tasks/{task_id}/reject")
def reject_task_api(task_id: str):
    """拒绝 SQL 执行"""

    try:
        result = reject_task(task_id)

        return {
            "task_id": result["task_id"],
            "status": result["status"],
            "sql_approved": result["sql_approved"]
        }

    except ValueError as e:
        message = str(e)

        if "未找到任务" in message:
            raise HTTPException(status_code=404, detail=message)

        raise HTTPException(status_code=409, detail=message)

@app.post("/tasks/{task_id}/resume")
def resume_task_api(task_id: str):

    try:
        result = resume_task(task_id)

        return {
            "task_id": result["task_id"],
            "status": result["status"],
            "task_type": result["task_type"],
            "error": result.get("error")
        }

    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )

@app.post("/tasks/{task_id}/retry")
def retry_task_api(task_id: str):
    """重新尝试被拒绝的任务"""

    try:
        result = retry_task(task_id)

        return {
            "original_task_id": task_id,
            "task_id": result["task_id"],
            "conversation_id": result["conversation_id"],
            "status": result["status"],
            "task_type": result["task_type"],
            "sql": result["sql"],
            "reason": result["reason"],
            "error": result.get("error")
        }

    except ValueError as e:
        message = str(e)

        if "未找到任务" in message:
            raise HTTPException(
                status_code=404,
                detail=message
            )

        raise HTTPException(
            status_code=409,
            detail=message
        )

    except Exception:
        logger.exception(
            "重新尝试任务失败，task_id=%s",
            task_id
        )

        raise HTTPException(
            status_code=500,
            detail="重新尝试任务失败"
        )

@app.get("/tasks")
def get_tasks_api(
    page: int = 1,
    page_size: int = 10,
    status: str = None,
    task_type: str = None,
    keyword: str = None
):
    try:
        if page < 1:
            raise HTTPException(
                status_code=400,
                detail="page 必须大于等于 1"
            )

        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=400,
                detail="page_size 必须在 1 到 100 之间"
            )

        tasks = get_task_list(
            page=page,
            page_size=page_size,
            status=status,
            task_type=task_type,
            keyword=keyword
        )

        total = get_task_count(
            status=status,
            task_type=task_type,
            keyword=keyword
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "status": status,
            "task_type": task_type,
            "keyword": keyword,
            "tasks": tasks
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("获取任务列表失败")
        raise HTTPException(
            status_code=500,
            detail="获取任务列表失败"
        )

@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    """根据任务 ID 查询完整工作流详情"""

    try:
        state = load_workflow_state(task_id)
       # 查询任务创建时间
        task_list = get_task_list(
            page=1,
            page_size=1,
            keyword=task_id
        )

        task_record = task_list[0] if task_list else {}

        created_at = task_record.get("created_at")
        lease_expires_at = task_record.get("lease_expires_at")
        lease_expired = task_record.get("lease_expired")

        if state is None:
            raise HTTPException(
                status_code=404,
                detail=f"未找到任务：{task_id}"
            )

        # 查询任务整体 Token 和成本
        usage = get_task_usage(task_id)

        # 查询各 Agent 的 Token 和成本
        agent_usage = get_task_agent_usage(task_id)

        return {
            "task_id": state.get("task_id"),
            "conversation_id": state.get("conversation_id"),
            "question": state.get("question"),
            "resolved_question": state.get("resolved_question"),
            "task_type": state.get("task_type"),
            "status": state.get("status"),
            "created_at": created_at,
            "lease_expires_at": lease_expires_at,
            "lease_expired": lease_expired,

            # SQL 执行信息
            "sql": state.get("sql"),
            "sql_approved": state.get("sql_approved"),
            "query_results": state.get("query_results"),

            # 分析与质量检查
            "report": state.get("report"),
            "qa_result": state.get("qa_result"),

            # 工作流执行记录
            "steps": state.get("steps"),
            "error": state.get("error"),

            # Token 和成本统计
            "usage": usage,
            "agent_usage": agent_usage
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "获取任务详情失败，task_id=%s",
            task_id
        )

        raise HTTPException(
            status_code=500,
            detail="获取任务详情失败"
        )

@app.get("/dashboard/overview")
def get_dashboard_overview(
    start_time: datetime = None,
    end_time: datetime = None
):
    """获取 Dashboard 全局统计数据，支持时间筛选"""

    try:
        # 校验时间范围
        if start_time and end_time:
            if start_time >= end_time:
                raise HTTPException(
                    status_code=400,
                    detail="start_time 必须早于 end_time"
                )

        # 1. 任务数量统计
        task_stats = get_dashboard_task_stats(
            start_time=start_time,
            end_time=end_time
        )

        # 2. 全局 Token 和成本统计
        usage_stats = get_dashboard_usage_stats(
            start_time=start_time,
            end_time=end_time
        )

        # 3. 各 Agent 统计
        agent_stats = get_dashboard_agent_usage_stats(
            start_time=start_time,
            end_time=end_time
        )

        return {
            "filters": {
                "start_time": start_time,
                "end_time": end_time
            },
            "task_stats": task_stats,
            "usage_stats": usage_stats,
            "agent_stats": agent_stats
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("获取 Dashboard 全局统计失败")

        raise HTTPException(
            status_code=500,
            detail="获取 Dashboard 全局统计失败"
        )

@app.get("/dashboard/task-trend")
def get_dashboard_task_trend_api(
    start_time: datetime = None,
    end_time: datetime = None
):
    """获取每日任务趋势"""

    try:
        # 校验时间范围
        if start_time and end_time:
            if start_time >= end_time:
                raise HTTPException(
                    status_code=400,
                    detail="start_time 必须早于 end_time"
                )

        data = get_dashboard_task_trend(
            start_time=start_time,
            end_time=end_time
        )

        return {
            "start_time": start_time,
            "end_time": end_time,
            "data": data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("获取每日任务趋势 API 失败")

        raise HTTPException(
            status_code=500,
            detail="获取每日任务趋势失败"
        )

@app.get("/dashboard/usage-trend")
def get_dashboard_usage_trend_api(
    start_time: datetime = None,
    end_time: datetime = None
):
    """获取每日 Token 和成本趋势"""

    try:
        # 校验时间范围
        if start_time and end_time:
            if start_time >= end_time:
                raise HTTPException(
                    status_code=400,
                    detail="start_time 必须早于 end_time"
                )

        data = get_dashboard_usage_trend(
            start_time=start_time,
            end_time=end_time
        )

        return {
            "start_time": start_time,
            "end_time": end_time,
            "data": data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("获取每日 Token 趋势 API 失败")

        raise HTTPException(
            status_code=500,
            detail="获取每日 Token 趋势失败"
        )

