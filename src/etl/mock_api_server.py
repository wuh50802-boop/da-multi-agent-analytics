"""本地模拟电商开放平台 API。

模拟真实平台 API 的核心特征：Bearer token 鉴权、分页、时间/平台过滤。
底层数据来自 data/mock_orders.json，但对外暴露的是标准 HTTP 接口，
让采集器走和真实平台一样的调用链路（而非直接读文件）。
"""

import json
import logging
import threading
import time

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query

from config import MOCK_ORDERS_FILE, MOCK_API_TOKEN

logger = logging.getLogger(__name__)

app = FastAPI(title="Mock E-commerce Open API", version="1.0.0")
_orders_cache = None
_server = None
_server_thread = None


def _load_orders():
    """加载模拟订单（进程内缓存）"""
    global _orders_cache
    if _orders_cache is None:
        with open(MOCK_ORDERS_FILE, encoding="utf-8") as f:
            _orders_cache = json.load(f)
        logger.info("模拟 API 加载订单数据：%s 条", len(_orders_cache))
    return _orders_cache


def _verify_token(authorization):
    """校验 Bearer token，模拟真实平台鉴权"""
    expected = f"Bearer {MOCK_API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


@app.get("/openapi/orders")
def list_orders(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(200, ge=1, le=1000, description="每页条数"),
    platform: str = Query(None, description="平台过滤：抖店/微信/小红书"),
    start_time: str = Query(None, description="提交时间起始 YYYY-MM-DD HH:MM:SS"),
    end_time: str = Query(None, description="提交时间截止 YYYY-MM-DD HH:MM:SS"),
    authorization: str = Header(None, alias="Authorization"),
):
    """分页查询订单列表 —— 模拟电商开放平台订单查询接口"""
    _verify_token(authorization)

    orders = _load_orders()

    # 平台过滤
    if platform:
        orders = [o for o in orders if o.get("平台") == platform]

    # 时间过滤
    if start_time:
        orders = [o for o in orders if (o.get("提交时间") or "") >= start_time]
    if end_time:
        orders = [o for o in orders if (o.get("提交时间") or "") <= end_time]

    total = len(orders)
    start = (page - 1) * page_size
    items = orders[start:start + page_size]

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "orders": items,
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "orders": len(_load_orders())}


def start_mock_server(host, port):
    """在后台线程启动模拟 API 服务（幂等）"""
    global _server, _server_thread

    if _server is not None:
        return

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    _server = uvicorn.Server(config)
    _server_thread = threading.Thread(
        target=_server.run,
        name="mock-api-server",
        daemon=True,
    )
    _server_thread.start()

    # 等待服务就绪
    for _ in range(30):
        if _server.started:
            logger.info("模拟开放平台 API 已启动：http://%s:%s", host, port)
            return
        time.sleep(0.1)

    raise RuntimeError("模拟 API 服务启动超时")


def stop_mock_server():
    """关闭模拟 API 服务"""
    global _server, _server_thread

    if _server is not None:
        _server.should_exit = True
        if _server_thread and _server_thread.is_alive():
            _server_thread.join(timeout=5)
        _server = None
        _server_thread = None
        logger.info("模拟开放平台 API 已关闭")
