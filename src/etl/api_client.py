import json
import logging

from config import MOCK_ORDERS_FILE

logger = logging.getLogger(__name__)


def fetch_data():
    """从本地模拟数据文件读取原始订单。

    替代原 jsonplaceholder API，保持函数签名不变，主流程无需改动。
    """

    logger.info("读取模拟订单数据：%s", MOCK_ORDERS_FILE)

    try:
        with MOCK_ORDERS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info("读取成功，共 %s 条订单", len(data))
        return data

    except (OSError, ValueError):
        logger.exception("模拟订单数据读取失败，请先运行 src/etl/mock_data_generator.py")
        raise
