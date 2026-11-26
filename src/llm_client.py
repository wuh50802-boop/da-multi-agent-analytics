
import logging
from openai import OpenAI
from src.core.budget import check_task_budget, BudgetExceededError
from config import DEEPSEEK_API_KEY
from src.storage.usage_storage import save_usage_log

logger = logging.getLogger(__name__)

MODEL_NAME = "deepseek-flash"


def get_llm_client():
    if not DEEPSEEK_API_KEY:
        raise ValueError("未配置 DEEPSEEK_API_KEY，请检查 .env 文件")

    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )


def chat_with_deepseek(
    messages,
    system_prompt=None,
    agent_name="unknown",
    task_id=None
):
    try:
        client = get_llm_client()

        if system_prompt:
            messages = [
                {"role": "system", "content": system_prompt}
            ] + [
                message for message in messages
                if message.get("role") != "system"
            ]

        if task_id is not None:
            if not check_task_budget(task_id):
                raise BudgetExceededError(
                    f"任务 {task_id} 已超过 Token 或成本预算，停止调用模型"
                )
            

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )

        answer = response.choices[0].message.content
        usage = response.usage

        if usage:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens

            logger.info(
                "DeepSeek Token 使用情况 | 输入：%s | 输出：%s | 总计：%s",
                prompt_tokens,
                completion_tokens,
                total_tokens
            )

            save_usage_log(
                task_id=task_id,
                agent_name=agent_name,
                model_name=MODEL_NAME,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )
        else:
            logger.warning("本次 DeepSeek 响应未返回 Token 使用信息")

        logger.info("DeepSeek 调用成功")
        return answer

    except Exception:
        logger.exception("DeepSeek API 调用失败或 Token 记录失败")
        raise
