"""业务口径检索 Agent。

从 RAG 知识库检索与当前问题相关的业务口径文档片段，
供 SQL Agent 生成时参考。检索失败降级为空列表，不影响主流程。
"""

import logging

from src.governance.rag import retrieve

logger = logging.getLogger(__name__)


def retrieve_business_context(question, trace_id=None, top_k=None):
    """检索业务口径片段。

    Returns:
        list[dict]: 命中片段，每项含 title/content/score/source/chunk_index
    """
    if not question:
        return []

    try:
        hits = retrieve(
            question,
            top_k=top_k,
            mode=None,
            trace_id=trace_id,
        )
        logger.info("业务口径检索完成：命中 %s 块", len(hits))
        return hits
    except Exception:
        logger.exception("业务口径检索失败，降级为空上下文")
        return []
