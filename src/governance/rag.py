"""RAG 知识库：文档上传、切块、BM25 + Chroma 向量数据库混合检索。

MySQL 保存文档与切块的权威内容；Chroma 保存语义向量；BM25 负责关键词召回。
"""
import json
import logging
import re
import uuid

import jieba
import mysql.connector
from rank_bm25 import BM25Okapi

from config import (
    DB_CONFIG, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP, RAG_TOP_K,
    RAG_DEFAULT_MODE, RAG_RRF_K,
)
from src.governance.audit import write_audit
from src.governance.embedding import embed_texts, embed_query, hash_embed
from src.governance import vector_db

logger = logging.getLogger(__name__)


def _connect():
    return mysql.connector.connect(**DB_CONFIG)


def embed(text):
    """兼容旧调用：返回哈希向量（新逻辑请使用 embedding.embed_texts）。"""
    return hash_embed(text)


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


def _tokenize(text):
    """中文分词 + 英文/数字词，供 BM25 使用。"""
    text = text or ""
    tokens = [t.strip() for t in jieba.lcut(text) if t.strip()]
    tokens.extend(re.findall(r"[a-zA-Z0-9_]+", text))
    return tokens


def _fetch_chunks():
    """从 MySQL 读取全部切块（BM25 与向量库重建共用）。"""
    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.doc_id, d.title, c.chunk_index, c.content,
                   c.embedding, c.embedding_model
            FROM sys_knowledge_chunks c
            JOIN sys_knowledge_docs d ON c.doc_id = d.doc_id
            ORDER BY c.doc_id, c.chunk_index
        """)
        return cursor.fetchall()
    except Exception:
        logger.exception("RAG 切块读取失败")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _result(doc_id, title, chunk_index, content, score, source):
    return {
        "doc_id": doc_id,
        "title": title,
        "chunk_index": chunk_index,
        "content": content,
        "score": round(float(score), 6),
        "source": source,
    }


def _from_vector_row(row):
    meta = row.get("metadata") or {}
    return _result(
        meta.get("doc_id", ""),
        meta.get("title", ""),
        meta.get("chunk_index", 0),
        row.get("content", ""),
        row.get("score", 0.0),
        "vector",
    )


def bm25_retrieve(query, top_k=None, trace_id=None):
    """BM25 关键词检索：精确命中指标名、表名、平台名。"""
    top_k = top_k or RAG_TOP_K
    rows = _fetch_chunks()
    if not rows:
        return []

    corpus = [_tokenize(r["content"]) for r in rows]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]

    results = []
    for index, score in ranked:
        r = rows[index]
        results.append(_result(
            r["doc_id"], r["title"], r["chunk_index"],
            r["content"], score, "bm25",
        ))
    return results


def rebuild_vector_db():
    """从 MySQL 重建 Chroma 向量库，并把旧哈希向量升级为语义向量。"""
    rows = _fetch_chunks()
    if not rows:
        logger.warning("向量库重建跳过：MySQL 中没有切块")
        return 0

    vectors, model = embed_texts([r["content"] for r in rows])
    if model == "hash":
        logger.warning("语义模型不可用，跳过向量库重建")
        return 0

    conn = None
    cursor = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.executemany("""
            UPDATE sys_knowledge_chunks
            SET embedding = %s, embedding_model = %s
            WHERE doc_id = %s AND chunk_index = %s
        """, [
            (json.dumps(vec, ensure_ascii=False), model,
             r["doc_id"], r["chunk_index"])
            for vec, r in zip(vectors, rows)
        ])
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("向量库重建时回写 MySQL 失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    vector_db.reset()
    items = [{
        "id": f"{r['doc_id']}:{r['chunk_index']}",
        "content": r["content"],
        "embedding": vec,
        "metadata": {
            "doc_id": r["doc_id"],
            "title": r["title"],
            "chunk_index": r["chunk_index"],
            "embedding_model": model,
        },
    } for vec, r in zip(vectors, rows)]
    vector_db.upsert_chunks(items)
    logger.info("向量库重建完成：%s 条切块，模型 %s", len(items), model)
    return len(items)


def vector_retrieve(query, top_k=None, trace_id=None):
    """Chroma 向量数据库语义检索。"""
    top_k = top_k or RAG_TOP_K
    q_vec, model = embed_query(query)
    if q_vec is None:
        return []

    if vector_db.count() == 0:
        logger.info("向量库为空，触发从 MySQL 自动重建")
        rebuild_vector_db()

    rows = vector_db.query(q_vec, top_k)
    return [_from_vector_row(r) for r in rows]


def hybrid_retrieve(query, top_k=None, trace_id=None):
    """RRF 融合 BM25 与向量检索排名。"""
    top_k = top_k or RAG_TOP_K
    vector_hits = vector_retrieve(query, top_k, trace_id=trace_id)
    bm25_hits = bm25_retrieve(query, top_k, trace_id=trace_id)

    scores = {}
    details = {}
    for hits in (vector_hits, bm25_hits):
        for rank, hit in enumerate(hits, start=1):
            key = (hit["doc_id"], hit["chunk_index"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (RAG_RRF_K + rank)
            details.setdefault(key, hit)

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
    results = []
    for key, score in ranked:
        hit = dict(details[key])
        hit["score"] = round(score, 6)
        hit["source"] = "hybrid"
        results.append(hit)
    return results


def retrieve(query, top_k=None, mode=None, trace_id=None):
    """统一检索入口：bm25 / vector / hybrid（默认 hybrid）。"""
    top_k = top_k or RAG_TOP_K
    mode = (mode or RAG_DEFAULT_MODE).lower()

    if mode == "bm25":
        results = bm25_retrieve(query, top_k, trace_id=trace_id)
    elif mode == "vector":
        results = vector_retrieve(query, top_k, trace_id=trace_id)
    elif mode == "hybrid":
        results = hybrid_retrieve(query, top_k, trace_id=trace_id)
    else:
        raise ValueError(f"未知 RAG 检索模式：{mode}")

    write_audit(
        "execution", f"RAG 检索：{query[:40]}",
        trace_id=trace_id, actor="agent",
        detail={"mode": mode, "top_k": top_k, "hits": len(results)},
        risk_level="L1",
    )
    logger.info("RAG 检索完成：mode=%s，命中 %s 块", mode, len(results))
    return results


def upload_document(title, content, source_type="text", trace_id=None):
    """上传文档：MySQL 写原文与向量，Chroma 写语义向量。"""
    doc_id = f"DOC-{uuid.uuid4().hex[:12]}"
    chunks = split_text(content)
    vectors, model = embed_texts(chunks)

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
                    (doc_id, chunk_index, content, embedding, embedding_model)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                doc_id, i, chunk,
                json.dumps(vectors[i], ensure_ascii=False),
                model,
            ))
        conn.commit()
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

    if model != "hash":
        try:
            vector_db.upsert_chunks([{
                "id": f"{doc_id}:{i}",
                "content": chunk,
                "embedding": vectors[i],
                "metadata": {
                    "doc_id": doc_id,
                    "title": title,
                    "chunk_index": i,
                    "embedding_model": model,
                },
            } for i, chunk in enumerate(chunks)])
        except Exception:
            logger.exception("向量数据库写入失败，检索时将自动重建")
    else:
        logger.warning("语义模型不可用，本次仅写入 MySQL 哈希向量")

    write_audit(
        "entry", f"RAG 文档上传：{title}",
        trace_id=trace_id, actor="user",
        detail={
            "doc_id": doc_id, "chunks": len(chunks),
            "embedding_model": model,
        },
        risk_level="L1",
    )
    logger.info("文档上传完成：%s，切块 %s，模型 %s", doc_id, len(chunks), model)
    return {
        "doc_id": doc_id,
        "chunk_count": len(chunks),
        "embedding_model": model,
    }


def list_documents():
    """列出已上传文档（只读 MySQL）。"""
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
