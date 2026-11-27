"""LangChain tool calling 适配层。

用 ChatOpenAI 指向 DeepSeek（OpenAI 兼容端点），bind_tools 后
让模型自主选择只读工具，执行工具调用循环，最终收敛为文本回答。

关键约束（对齐方案 B）：
- 只绑定 READ_ONLY 工具，执行类工具不暴露，人工审批门禁不受影响
- 每轮调用前检查预算，沿用 llm_client 的 check_task_budget
- Token 用量写入同一张 llm_usage_logs，agent_name 标记为 tool_agent
- 工具调用结果写审计，保证可追溯
"""

import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage, SystemMessage, ToolMessage,
)

from config import DEEPSEEK_API_KEY
from src.core.budget import check_task_budget, BudgetExceededError
from src.storage.usage_storage import save_usage_log
from src.governance.audit import write_audit
from src.tools.registry import get_tools

logger = logging.getLogger(__name__)

MODEL_NAME = "deepseek-flash"
MAX_TOOL_ROUNDS = 4


def get_chat_model():
    """构造绑定只读工具的 DeepSeek ChatOpenAI 实例。"""
    if not DEEPSEEK_API_KEY:
        raise ValueError("未配置 DEEPSEEK_API_KEY，请检查 .env 文件")

    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        temperature=0,
    )
    return llm.bind_tools(get_tools(stage="pre_approval"))


def chat_with_tools(
    question,
    system_prompt,
    task_id=None,
    trace_id=None,
    max_rounds=MAX_TOOL_ROUNDS,
):
    """运行 tool calling 循环，返回模型最终文本回答。

    流程：
      用户问题 -> 模型（可请求工具）-> 执行只读工具 -> 结果回灌 ->
      模型继续 -> ... -> 无工具请求时输出最终文本。
    """
    model = get_chat_model()
    tool_map = {t.name: t for t in get_tools(stage="pre_approval")}

    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=question))

    final_answer = ""

    for round_index in range(1, max_rounds + 1):
        if task_id is not None and not check_task_budget(task_id):
            raise BudgetExceededError(
                f"任务 {task_id} 已超过预算，停止 tool calling"
            )

        response = model.invoke(messages)

        usage = response.usage_metadata or {}
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        save_usage_log(
            task_id=task_id,
            agent_name="tool_agent",
            model_name=MODEL_NAME,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        tool_calls = response.tool_calls or []
        messages.append(response)

        if not tool_calls:
            final_answer = response.content or ""
            break

        for call in tool_calls:
            name = call.get("name")
            args = call.get("args", {})
            call_id = call.get("id")

            tool = tool_map.get(name)
            if tool is None:
                result = f"未知工具：{name}"
            else:
                try:
                    result = tool.invoke(args)
                except Exception as exc:
                    result = f"工具执行失败：{exc}"

            write_audit(
                "execution", f"Tool calling：{name}",
                task_id=task_id, trace_id=trace_id,
                actor="tool_agent",
                detail={"tool": name, "args": args, "result": str(result)[:500]},
                risk_level="L1",
            )
            logger.info("工具调用完成：%s | 轮次：%s", name, round_index)

            messages.append(
                ToolMessage(content=str(result), tool_call_id=call_id)
            )
    else:
        final_answer = "工具调用轮次已达上限，请简化问题后重试。"
        logger.warning("tool calling 达到最大轮次：%s", max_rounds)

    return final_answer
