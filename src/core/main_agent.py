
import logging
from src.logger import setup_logging
from src.core.state import create_initial_state
from src.core.workflow import run_workflow
from src.service.task_service import (
    create_task,
    approve_task,
    reject_task
)
logger = logging.getLogger(__name__)


def run_agent(question, conversation_id=None):

    result = create_task(
        question,
        conversation_id=conversation_id
    )
    if conversation_id is None:
     conversation_id = result["conversation_id"]

    # 如果任务需要人工审批
    if result["status"] == "awaiting_approval":
        print("\n========== SQL 审批 ==========")
        print("\n生成的 SQL：")
        print(result["sql"])
        approval = input(
            "\n是否批准执行这条 SQL？(y/n)："
        ).strip().lower()

        if approval == "y":
            result = approve_task(result["task_id"])

        elif approval == "n":
            result = reject_task(result["task_id"])

        else:
            print("输入无效，本次任务不执行。")
            result = reject_task(result["task_id"])

    else:
        # 无需审批且已经完成的任务，保存助手回复
        if result["status"] == "completed":
            from src.service.conversation_manager import add_assistant_message

            answer = result.get("report")

            if answer is None and result.get("query_results") is not None:
                import json
                answer = json.dumps(
                    result["query_results"],
                    ensure_ascii=False,
                    default=str
                )

            if answer:
                add_assistant_message(
                    result["conversation_id"],
                    result["task_id"],
                    answer
                )

    return result, conversation_id


if __name__ == "__main__":

    setup_logging()

    conversation_id = None

    while True:
        question = input("\n请输入问题（输入 exit 退出）：")

        if question.strip().lower() == "exit":
            break

        result, conversation_id = run_agent(
            question,
            conversation_id=conversation_id
        )

        print("\n========== 工作流状态 ==========")
        print("任务类型：", result["task_type"])
        print("执行状态：", result["status"])

        if result["error"]:
            print("错误信息：", result["error"])

        if result["sql"]:
            print("\n生成的 SQL：")
            print(result["sql"])

        if result["query_results"] is not None:
            print("\n查询结果：")
            print(result["query_results"])

        if result["report"]:
            print("\n最终回答：")
            print(result["report"])

        if result["qa_result"]:
            print("\n========== QA 审核结果 ==========")
            print("是否通过：", result["qa_result"]["passed"])
            print("问题：", result["qa_result"]["issues"])
            print("建议：", result["qa_result"]["suggestions"])
            print("审核总结：", result["qa_result"]["summary"])