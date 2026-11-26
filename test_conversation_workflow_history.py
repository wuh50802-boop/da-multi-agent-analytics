from src.storage.workflow_storage import get_conversation_workflow_history

conversation_id = "a9849ea9-dc04-49fa-be24-095a29770b2e"

history = get_conversation_workflow_history(conversation_id)

print("历史任务数量：", len(history))

for item in history:
    print("-" * 50)
    print("Task ID：", item.get("task_id"))
    print("任务类型：", item.get("task_type"))
    print("任务状态：", item.get("status"))
    print("问题：", item.get("question"))
    print("是否有查询结果：", item.get("query_results") is not None)