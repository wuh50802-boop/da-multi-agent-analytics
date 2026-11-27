"""RAG 向量化封装：优先中文语义向量，模型不可用时回退哈希向量。"""
import hashlib
import logging

import numpy as np

from config import RAG_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

VECTOR_DIM = 256
_model = None


def hash_embed(text):
    """字符 n-gram 哈希向量（确定性、零依赖，作为降级方案）。"""
    vec = np.zeros(VECTOR_DIM, dtype=np.float64)
    text = (text or "").lower()
    tokens = list(text) + [
        text[i:i + 2] for i in range(len(text) - 1)
    ]
    for token in tokens:
        h = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(h[:2], "big") % VECTOR_DIM
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return (vec / norm if norm > 0 else vec).tolist()


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=RAG_EMBEDDING_MODEL)
    return _model


def embed_texts(texts):
    """批量向量化，返回 (向量列表, 模型标识)。

    语义模型不可达时回退 hash 向量，调用方需根据模型标识决定是否写入向量库。
    """
    try:
        model = _get_model()
        vectors = [v.tolist() for v in model.embed(list(texts))]
        logger.info("语义向量生成完成：%s 条，模型 %s", len(vectors), RAG_EMBEDDING_MODEL)
        return vectors, RAG_EMBEDDING_MODEL
    except Exception:
        logger.exception("语义向量模型不可用，回退哈希向量")
        return [hash_embed(t) for t in texts], "hash"


def embed_query(text):
    """查询向量化；查询侧不使用 hash 降级，避免与向量库维度不一致。"""
    try:
        model = _get_model()
        return next(model.embed([text])).tolist(), RAG_EMBEDDING_MODEL
    except Exception:
        logger.exception("查询语义向量生成失败")
        return None, None
