
import logging

from src.llm_client import chat_with_deepseek
from src.prompts.sql_generator import SQL_GENERATOR_SYSTEM_PROMPT
from src.governance.metadata import get_schema_context
from config import ALLOWED_TABLES, ENABLE_TOOL_CALLING

logger = logging.getLogger(__name__)


def generate_sql(question, task_id=None, knowledge=None, use_tools=None):
    """根据用户问题生成 SQL。

    优先使用元数据字典中的真实表结构（治理驱动），
    字典未采集时回退到静态提示词。
    knowledge 为 RAG 检索命中的业务口径片段，注入后模型须优先遵守。
    """

    system_prompt = SQL_GENERATOR_SYSTEM_PROMPT

    dynamic_schema = get_schema_context(ALLOWED_TABLES)
    if dynamic_schema:
        # 用动态 Schema 替换静态提示词中的可用数据表段落
        marker_start = system_prompt.find("可用数据表：")
        marker_end = system_prompt.find("# Metric Rules")
        if marker_start != -1 and marker_end != -1:
            system_prompt = (
                system_prompt[:marker_start]
                + dynamic_schema + "\n"
                + system_prompt[marker_end:]
            )
            logger.info("SQL 提示词已注入元数据字典 Schema")

    # RAG 业务口径注入：命中片段作为权威口径，优先级高于通用规则
    if knowledge:
        lines = [
            "",
            "# Business Context（业务口径，来自企业知识库）",
            "以下口径为权威定义，与通用规则冲突时以本节为准：",
        ]
        for index, item in enumerate(knowledge, start=1):
            title = item.get("title", "")
            content = item.get("content", "")
            lines.append(f"[{index}]《{title}》：{content}")
        system_prompt += "\n".join(lines) + "\n"
        logger.info("SQL 提示词已注入 %s 条业务口径", len(knowledge))

    # Tool calling 增强模式（方案 B）：模型可自主调用只读工具补充信息。
    # 只暴露只读工具，不触碰人工审批门禁；默认关闭，可按需开启。
    if use_tools is None:
        use_tools = ENABLE_TOOL_CALLING

    if use_tools:
        from src.tools.langchain_adapter import chat_with_tools

        sql = chat_with_tools(
            question=question,
            system_prompt=system_prompt,
            task_id=task_id,
        )
        logger.info("SQL 生成成功（tool calling 增强模式）")
        return sql

    messages = [{"role": "user", "content": question}]

    sql = chat_with_deepseek(
        messages,
        system_prompt=system_prompt,
        agent_name="sql_agent",
        task_id=task_id
    )

    logger.info("SQL 生成成功")
    return sql
