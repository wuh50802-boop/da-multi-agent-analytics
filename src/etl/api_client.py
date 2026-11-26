"""数据采集统一入口。

根据 config.DATA_SOURCE 选择采集器：
    - mock_api：调用本地模拟开放平台 API（鉴权 + 分页 + 重试）
    - doudian：真实抖店 API（需凭证）

保持 fetch_data() 签名不变，ETL 主流程无需改动。
"""

import logging

from config import DATA_SOURCE, MOCK_API_HOST, MOCK_API_PORT
from src.etl.collector import get_collector

logger = logging.getLogger(__name__)


def fetch_data(platform=None, start_time=None, end_time=None):
    """通过采集器拉取原始订单，返回统一格式的订单字典列表。"""
    base_url = f"http://{MOCK_API_HOST}:{MOCK_API_PORT}"
    logger.info("数据源：%s | API 地址：%s", DATA_SOURCE, base_url)

    collector = get_collector(data_source=DATA_SOURCE, base_url=base_url)
    return collector.fetch_orders(
        platform=platform,
        start_time=start_time,
        end_time=end_time,
    )
