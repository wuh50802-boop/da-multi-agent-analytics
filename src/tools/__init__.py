"""Tool calling 工具层：LangChain 工具注册与分级治理。

设计原则：
- 审批前只暴露只读工具（查 Schema / 查字典 / RAG 检索）
- execute_sql 执行类工具审批后才可用，绝不绕过人工审批门禁
- 所有工具调用走审计留痕
"""
