from pydantic import BaseModel, Field, field_validator
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
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
from src.service.scheduler import (
    start_scheduler,
    shutdown_scheduler,
    get_scheduler_status
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动时开启定时调度，关闭时释放调度器。"""
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Multi-Agent Workflow API",
    description="多智能体数据分析工作流服务",
    version="1.0.0",
    lifespan=lifespan,
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
        "message": "Multi-Agent API is running",
        "scheduler": get_scheduler_status()
    }


@app.post("/chat")
def chat(request: ChatRequest, http_request: Request):
    """接收用户问题并创建工作流任务（含入口治理）"""

    trace_id = http_request.headers.get("X-Trace-Id")
    user = http_request.headers.get("X-User-Id")

    try:
        result = create_task(
            question=request.question,
            conversation_id=request.conversation_id,
            trace_id=trace_id,
            user=user,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    if result.get("status") == "rejected" and not result.get("task_id"):
        raise HTTPException(status_code=403, detail=result.get("error"))

    return {
        "task_id": result["task_id"],
        "conversation_id": result.get("conversation_id"),
        "status": result["status"],
        "task_type": result.get("task_type"),
        "sql": result.get("sql"),
        "reason": result.get("reason"),
        "trace_id": result.get("trace_id"),
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


# ==================== 企业治理端点 ====================

class MetadataSyncResponse(BaseModel):
    field_count: int


class DocUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source_type: str = "text"


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int | None = None
    mode: str = "hybrid"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value):
        mode = value.lower()
        if mode not in {"bm25", "vector", "hybrid"}:
            raise ValueError("mode 只能是 bm25 / vector / hybrid")
        return mode


@app.post("/admin/metadata/sync", response_model=MetadataSyncResponse)
def sync_metadata_api():
    """元数据治理：从 information_schema 采集表结构"""
    from src.governance.metadata import sync_metadata
    try:
        return {"field_count": sync_metadata()}
    except Exception:
        logger.exception("元数据同步 API 失败")
        raise HTTPException(status_code=500, detail="元数据同步失败")


@app.get("/admin/metadata")
def list_metadata_api(table: str | None = None):
    """查询元数据字典"""
    import mysql.connector
    from config import DB_CONFIG
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        if table:
            cursor.execute("""
                SELECT * FROM sys_metadata_dict WHERE table_name = %s
                ORDER BY column_order
            """, (table,))
        else:
            cursor.execute("SELECT * FROM sys_metadata_dict ORDER BY table_name, column_order")
        rows = cursor.fetchall()
        for r in rows:
            if r.get("updated_at"):
                r["updated_at"] = r["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
            if r.get("created_at"):
                r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        cursor.close()
        conn.close()
        return {"total": len(rows), "data": rows}
    except Exception:
        logger.exception("元数据查询 API 失败")
        raise HTTPException(status_code=500, detail="元数据查询失败")


@app.get("/admin/audit")
def query_audit_api(
    trace_id: str | None = None,
    task_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
):
    """审计治理：查询全链路审计日志"""
    from src.governance.audit import query_audit
    return {
        "data": query_audit(
            trace_id=trace_id, task_id=task_id,
            event_type=event_type, limit=limit,
        )
    }


@app.post("/admin/rag/documents")
def upload_doc_api(request: DocUploadRequest, http_request: Request):
    """RAG 治理：上传文档并自动切块向量化"""
    from src.governance.rag import upload_document
    try:
        return upload_document(
            title=request.title,
            content=request.content,
            source_type=request.source_type,
            trace_id=http_request.headers.get("X-Trace-Id"),
        )
    except Exception:
        logger.exception("文档上传 API 失败")
        raise HTTPException(status_code=500, detail="文档上传失败")


@app.get("/admin/rag/documents")
def list_docs_api():
    """RAG 治理：列出文档"""
    from src.governance.rag import list_documents
    return {"data": list_documents()}


@app.post("/admin/rag/search")
def rag_search_api(request: RagQueryRequest):
    """RAG 治理：BM25 / 向量数据库 / 混合检索"""
    from src.governance.rag import retrieve
    return {
        "data": retrieve(
            request.query,
            top_k=request.top_k,
            mode=request.mode,
        )
    }


@app.post("/admin/rag/rebuild")
def rag_rebuild_api():
    """RAG 治理：从 MySQL 全量重建 Chroma 向量数据库"""
    from src.governance.rag import rebuild_vector_db
    from src.governance.audit import write_audit
    try:
        count = rebuild_vector_db()
        write_audit(
            "execution", "RAG 向量数据库重建",
            actor="admin", detail={"chunks": count}, risk_level="L1",
        )
        return {"chunks": count}
    except Exception:
        logger.exception("向量库重建 API 失败")
        raise HTTPException(status_code=500, detail="向量库重建失败")


@app.get("/tasks/{task_id}/export")
def export_task_data_api(task_id: str):
    """输出治理：任务结果导出 CSV（Excel 可直接打开）"""
    from fastapi.responses import Response
    from src.governance.export import export_results_csv
    from src.governance.audit import write_audit

    state = load_workflow_state(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    results = state.get("query_results") or []
    csv_text = export_results_csv(results)

    write_audit(
        "output", "查询结果导出 CSV",
        trace_id=state.get("trace_id"), task_id=task_id,
        actor="user", detail={"rows": len(results)},
        risk_level="L2" if results else "L1",
    )

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{task_id}.csv"'
        },
    )

