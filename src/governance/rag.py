"""RAG 知识库：文档上传、自动切块、向量检索。

用 numpy 实现轻量级向量化（字符 n-gram 哈希），无需额外依赖。
对应母版「RAG 知识库」：文档上传 + 自动切块 + 向量检索 + Agent 工具调用。
"""
import hashlib
import json
import logging
import uuid

import mysql.connector
import numpy as np

from config import (
    DB_CONFIG, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP, RAG_TOP_K,
)
from src.governance.audit import write_audit

logger = logging.getLogger(__name__)

VECTOR_DIM = 256


def _connect():
    return mysql.connector.connect(**DB_CONFIG)


def embed(text):
    """字符 n-gram 哈希向量化（确定性，无需模型）。"""
    vec = np.zeros(VECTOR_DIM, dtype=np.float64)
    text = (text or "").lower()
    # 单字 + 双字 bigram
    tokens = list(text) + [
        text[i:i + 2] for i in range(len(text) - 1)
    ]
    for token in tokens:
        h = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(h[:2], "big") % VECTOR_DIM
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return (vec / norm if norm > 0 else vec).tolist()


def split_text(text, size=None, overlap=None):
    """按字符切块，带重叠。"""
    size = size or RAG_CHUNK_SIZE
    overlap = overlap or RAG_CHUNK_OVERLAP
    text = text or ""
    if len(text) <= size:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def upload_document(title, content, source_type="text", trace_id=None):
    """上传文档并自动切块、向量化入库。返回 doc_id 和切块数。"""
    doc_id = f"DOC-{uuid.uuid4().hex[:12]}"
    chunks = split_text(content)
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sys_knowledge_docs
                (doc_id, title, source_type, content, chunk_count)
            VALUES (%s, %s, %s, %s, %s)
        """, (doc_id, title, source_type, content, len(chunks)))

        for i, chunk in enumerate(chunks):
            cursor.execute("""
                INSERT INTO sys_knowledge_chunks
                    (doc_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s)
            """, (
                doc_id, i, chunk,
                json.dumps(embed(chunk), ensure_ascii=False),
            ))
        conn.commit()

        write_audit(
            "entry", f"RAG 文档上传：{title}",
            trace_id=trace_id, actor="user",
            detail={"doc_id": doc_id, "chunks": len(chunks)},
            risk_level="L1",
        )
        logger.info("文档上传完成：%s，切块 %s", doc_id, len(chunks))
        return {"doc_id": doc_id, "chunk_count": len(chunks)}
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("文档上传失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def retrieve(query, top_k=None, trace_id=None):
    """向量检索：返回最相关的切块。"""
    top_k = top_k or RAG_TOP_K
    q_vec = np.array(embed(query))
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.chunk_index, c.content, c.embedding,
                   d.title, d.doc_id
            FROM sys_knowledge_chunks c
            JOIN sys_knowledge_docs d ON c.doc_id = d.doc_id
        """)
        rows = cursor.fetchall()

        scored = []
        for r in rows:
            try:
                vec = np.array(json.loads(r["embedding"]))
                score = float(np.dot(q_vec, vec))
            except (ValueError, TypeError):
                score = 0.0
            scored.append((score, r))

        scored.sort(key=lambda x: -x[0])
        results = []
        for score, r in scored[:top_k]:
            results.append({
                "doc_id": r["doc_id"],
                "title": r["title"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "score": round(score, 4),
            })

        write_audit(
            "execution", f"RAG 检索：{query[:40]}",
            trace_id=trace_id, actor="agent",
            detail={"top_k": top_k, "hits": len(results)},
            risk_level="L1",
        )
        logger.info("RAG 检索完成：命中 %s 块", len(results))
        return results
    except Exception:
        logger.exception("RAG 检索失败")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def list_documents():
    """列出已上传文档。"""
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT doc_id, title, source_type, chunk_count, created_at
            FROM sys_knowledge_docs ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        return rows
    except Exception:
        logger.exception("文档列表查询失败")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
