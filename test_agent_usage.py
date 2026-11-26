from src.storage.usage_storage import get_task_agent_usage

# 先从 workflow_runs 表中找一个已经执行过大模型调用的 task_id
task_id = "eb075de5-bb94-4935-86b3-25345d748751"

results = get_task_agent_usage(task_id)

print("========== Agent 消耗统计 ==========")

for item in results:
    print("--------------------")
    print("Agent：", item["agent_name"])
    print("输入 Token：", item["prompt_tokens"])
    print("输出 Token：", item["completion_tokens"])
    print("总 Token：", item["total_tokens"])
    print("成本：", item["total_cost_rmb"])