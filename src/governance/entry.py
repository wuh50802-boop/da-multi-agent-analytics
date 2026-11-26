"""入口治理：Webhook 校验、traceId、敏感词拦截、风控标签。

对应母版「企业级入口治理」：合法性校验 + 统一追踪 + 敏感词拦截 + 风控标记。
"""
import hashlib
import hmac
import logging

from config import SENSITIVE_KEYWORDS, WEBHOOK_SECRET
from src.governance.audit import write_audit

logger = logging.getLogger(__name__)


def validate_webhook(body: bytes, signature: str = "") -> bool:
    """校验 Webhook 签名；未配置密钥时跳过校验（演示模式）。"""
    if not WEBHOOK_SECRET:
        return True
    if not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def check_sensitive_input(text: str):
    """敏感词检测，返回 (是否命中, 命中的词, 风控等级)。

    命中破坏性操作/批量导出类敏感词时风险等级为 L3。
    """
    lowered = (text or "").lower()
    for keyword in SENSITIVE_KEYWORDS:
        if keyword.lower() in lowered:
            return True, keyword, "L3"
    return False, None, "L1"


def guard_entry(text: str, trace_id=None, task_id=None, actor="user"):
    """入口统一守卫：敏感词拦截 + 审计留痕。

    返回 (passed, risk_level, reason)。未通过时调用方应拒绝请求。
    """
    hit, keyword, risk = check_sensitive_input(text)

    if hit:
        write_audit(
            "entry", f"敏感词拦截：{keyword}",
            trace_id=trace_id, task_id=task_id, actor=actor,
            detail={"keyword": keyword, "input": text[:200]},
            risk_level="L3",
        )
        logger.warning("入口敏感词拦截：%s | 关键词：%s", trace_id, keyword)
        return False, risk, f"请求包含受限内容（{keyword}），已拦截"

    write_audit(
        "entry", "请求通过入口校验",
        trace_id=trace_id, task_id=task_id, actor=actor,
        detail={"input_length": len(text or "")},
        risk_level="L1",
    )
    return True, "L1", None
