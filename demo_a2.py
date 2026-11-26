"""A2 端到端演示：自然语言问数 → 路由 → SQL → 人工审批 → 执行 → 报告 → QA。

用法：.venv/Scripts/python.exe demo_a2.py
"""

import json

from src.logger import setup_logging
from src.service.task_service import create_task, approve_task
from src.storage.usage_storage import get_task_usage, get_task_agent_usage

setup_logging()

# 演示问题：明确要求"分析 + 建议"，让 Supervisor 路由到 analysis，
# 从而完整展示 路由→SQL→审批→执行→报告→QA 全链路。
QUESTION = "分析本月抖店达人 GMV 表现，指出头部达人的优势并给出运营建议"


def brief(state):
    return {
        "task_id": state.get("task_id"),
        "status": state.get("status"),
        "task_type": state.get("task_type"),
        "steps": state.get("steps"),
        "error": state.get("error"),
    }


def main():
    print("=" * 72)
    print("A2 端到端演示：自然语言 → 多 Agent → 人工审批 → 报告 → QA")
    print("=" * 72)
    print(f"\n[用户提问] {QUESTION}\n")

    # 1. 创建任务，工作流自动跑到审批门禁
    result = create_task(question=QUESTION)
    print("[步骤 1] 创建任务 + Supervisor 路由 + SQL 生成")
    print(json.dumps(brief(result), ensure_ascii=False, indent=2))
    print(f"\n  路由理由：{result.get('reason')}")
    print(f"  SQL：\n{result.get('sql')}")

    if result.get("status") != "awaiting_approval":
        print(f"\n[中止] 预期停在 awaiting_approval，实际为 {result.get('status')}")
        print(f"  错误：{result.get('error')}")
        return

    print("\n" + "-" * 72)
    print("[人工审批门禁] SQL 执行前需人工确认 —— 模拟点击「批准」")
    print("-" * 72)

    final = approve_task(result["task_id"])

    print("\n[步骤 2] 执行 SQL → 生成报告 → QA 质检")
    print(json.dumps(brief(final), ensure_ascii=False, indent=2))

    print("\n[查询结果]")
    rows = final.get("query_results") or []
    if isinstance(rows, list):
        print(f"  共 {len(rows)} 行，前 3 行：")
        for row in rows[:3]:
            print("   ", json.dumps(row, ensure_ascii=False, default=str))
    else:
        print("  ", rows)

    print("\n[分析报告]")
    print(final.get("report") or "(空)")

    qa = final.get("qa_result") or {}
    print("\n[QA 质检]")
    print(f"  通过：{qa.get('passed')}")
    print(f"  问题：{qa.get('issues') or '无'}")
    print(f"  建议：{qa.get('suggestions') or '无'}")

    usage = get_task_usage(result["task_id"])
    agent_usage = get_task_agent_usage(result["task_id"])
    print("\n[Token 与成本]")
    print("  合计：", json.dumps(usage, ensure_ascii=False, default=str))
    print("  各 Agent：")
    for row in agent_usage or []:
        print("   ", json.dumps(row, ensure_ascii=False, default=str))

    print("\n" + "=" * 72)
    print("演示结束")
    print("=" * 72)


if __name__ == "__main__":
    main()
