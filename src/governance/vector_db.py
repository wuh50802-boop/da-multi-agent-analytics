"""Chroma 向量数据库封装：嵌入式持久化，无需单独启动服务。

MySQL 仍是文档与切块的权威来源；Chroma 只存向量、原文和检索元数据。
"""
import logging

import chromadb
from chromadb.config import Settings

from config import RAG_CHROMA_COLLECTION, RAG_VECTOR_DB_PATH

logger = logging.getLogger(__name__)

_client = None
_collection = None


def get_collection():
    """懒加载向量数据库集合。"""
    global _client, _collection
    if _collection is None:
        RAG_VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(RAG_VECTOR_DB_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=RAG_CHROMA_COLLECTION,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "向量数据库已连接：%s，集合 %s，现有 %s 条",
            RAG_VECTOR_DB_PATH, RAG_CHROMA_COLLECTION, _collection.count(),
        )
    return _collection


def upsert_chunks(items):
    """写入/更新切块向量。items: [{id, content, embedding, metadata}]"""
    if not items:
        return 0
    collection = get_collection()
    collection.upsert(
        ids=[item["id"] for item in items],
        documents=[item["content"] for item in items],
        embeddings=[item["embedding"] for item in items],
        metadatas=[item["metadata"] for item in items],
    )
    logger.info("向量数据库写入完成：%s 条", len(items))
    return len(items)


def query(embedding, top_k):
    """向量检索，返回 [{id, content, metadata, distance, score}]"""
    collection = get_collection()
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    rows = []
    for i, chunk_id in enumerate(result["ids"][0]):
        distance = float(result["distances"][0][i])
        rows.append({
            "id": chunk_id,
            "content": result["documents"][0][i],
            "metadata": result["metadatas"][0][i] or {},
            "distance": distance,
            "score": round(1.0 - distance, 4),
        })
    return rows


def delete_doc(doc_id):
    """按文档删除向量（元数据过滤）。"""
    collection = get_collection()
    collection.delete(where={"doc_id": doc_id})
    logger.info("向量数据库删除文档：%s", doc_id)


def reset():
    """清空并重建集合（用于从 MySQL 全量重建）。"""
    global _collection
    get_collection()
    _client.delete_collection(name=RAG_CHROMA_COLLECTION)
    _collection = _client.get_or_create_collection(
        name=RAG_CHROMA_COLLECTION,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("向量数据库集合已重建：%s", RAG_CHROMA_COLLECTION)


def count():
    return get_collection().count()
