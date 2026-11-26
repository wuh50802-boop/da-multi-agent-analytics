"""可插拔数据采集器。

设计意图（产品视角）：
    采集层的职责是「把不同平台的数据源，转换成统一的订单字典列表」。
    上层 ETL 只依赖 BaseCollector 接口，不关心数据来自模拟 API 还是真实平台。
    这样换数据源 = 换一个采集器实现，ETL 和 Agent 层完全不用动。

当前实现：
    - MockAPICollector：调用本地模拟开放平台 API（鉴权 + 分页 + 重试）
    - DouDianCollector：真实抖店采集器骨架（需配置 app_key/app_secret）
"""

import logging
import time
from abc import ABC, abstractmethod

import requests

from config import (
    COLLECT_PAGE_SIZE,
    COLLECT_MAX_RETRIES,
    MOCK_API_TOKEN,
    DOUDIAN_APP_KEY,
    DOUDIAN_APP_SECRET,
)

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """采集器抽象基类：所有平台采集器必须实现 fetch_orders()"""

    @abstractmethod
    def fetch_orders(self, platform=None, start_time=None, end_time=None):
        """返回统一格式的订单字典列表"""
        raise NotImplementedError


class MockAPICollector(BaseCollector):
    """通过 HTTP 调用本地模拟开放平台 API 拉取订单。

    走的是真实采集链路：鉴权 → 分页 → 重试 → 聚合，
    而不是直接读 JSON 文件。
    """

    def __init__(self, base_url, token=None, page_size=None, max_retries=None):
        self.base_url = base_url.rstrip("/")
        self.token = token or MOCK_API_TOKEN
        self.page_size = page_size or COLLECT_PAGE_SIZE
        self.max_retries = max_retries or COLLECT_MAX_RETRIES
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _get_page(self, page, platform, start_time, end_time):
        """带指数退避重试的单页请求"""
        params = {
            "page": page,
            "page_size": self.page_size,
        }
        if platform:
            params["platform"] = platform
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        url = f"{self.base_url}/openapi/orders"

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                payload = resp.json()

                if payload.get("code") != 0:
                    raise ValueError(f"API 返回错误：{payload.get('message')}")

                return payload["data"]

            except Exception as e:
                if attempt >= self.max_retries:
                    logger.error("采集第 %s 页失败（已重试 %s 次）：%s", page, attempt, e)
                    raise
                wait = 2 ** (attempt - 1)
                logger.warning("采集第 %s 页失败，%ss 后重试：%s", page, wait, e)
                time.sleep(wait)

    def fetch_orders(self, platform=None, start_time=None, end_time=None):
        """分页拉取全量订单"""
        all_orders = []
        page = 1
        total = None

        logger.info(
            "开始采集订单 | 平台：%s | 时间范围：%s ~ %s",
            platform or "全部", start_time or "不限", end_time or "不限",
        )

        while True:
            data = self._get_page(page, platform, start_time, end_time)
            orders = data.get("orders", [])

            if total is None:
                total = data.get("total", 0)
                logger.info("API 报告订单总数：%s", total)

            all_orders.extend(orders)
            logger.info("采集第 %s 页：%s 条，累计 %s/%s", page, len(orders), len(all_orders), total)

            if not orders or len(all_orders) >= total:
                break
            page += 1

        logger.info("采集完成，共 %s 条订单", len(all_orders))
        return all_orders


class DouDianCollector(BaseCollector):
    """真实抖店采集器骨架。

    母版实现位于 reference/API_data_collect/order_D，
    依赖抖店开放平台 SDK（token 刷新、订单/售后/结算三个服务）。
    此处预留接口：配置凭证并提供 SDK 后，实现 fetch_orders() 即可切换。
    """

    def __init__(self, app_key=None, app_secret=None):
        self.app_key = app_key or DOUDIAN_APP_KEY
        self.app_secret = app_secret or DOUDIAN_APP_SECRET

    def fetch_orders(self, platform=None, start_time=None, end_time=None):
        if not self.app_key or not self.app_secret:
            raise RuntimeError(
                "未配置抖店凭证（DOUDIAN_APP_KEY / DOUDIAN_APP_SECRET），"
                "请在 .env 中填写，或改用 DATA_SOURCE=mock_api"
            )
        raise NotImplementedError(
            "真实抖店采集需要移植母版 SDK（doudian 包），当前项目尚未接入"
        )


def get_collector(data_source, base_url=None):
    """采集器工厂：根据配置返回对应实现"""
    if data_source == "mock_api":
        if not base_url:
            raise ValueError("mock_api 数据源需要提供 base_url")
        return MockAPICollector(base_url=base_url)

    if data_source == "doudian":
        return DouDianCollector()

    raise ValueError(f"未知数据源：{data_source}，可选 mock_api / doudian")
