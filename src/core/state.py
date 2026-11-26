
from uuid import uuid4



def create_initial_state(question, conversation_id=None):
    """创建工作流初始状态"""

    return {
        "sql_approved": False,
        "task_id": str(uuid4()),
        "question": question,
        "resolved_question": None,
        "task_type": None,
        "reason": None,
        "routing_result": None,

        # 保存 Supervisor 的完整路由结果
        "routing_result": None,

        "sql": None,
        "query_results": None,
        "report": None,
        "conversation_id": conversation_id,
        "qa_result": None,

        "steps": {
            "routing": "pending",
            "sql_generation": "pending",
            "sql_execution": "pending",
            "report_generation": "pending",
            "qa_review": "pending",
            "chat_response": "pending"
        },

        "status": "pending",
        "error": None
    }
