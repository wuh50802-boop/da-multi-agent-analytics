"""电商数仓 ETL 入口：ODS → DWD → DWS → ADS。

既可手动执行（python main.py），也由调度器定时调用 run_etl()。
"""

import logging
from datetime import datetime

from src.logger import setup_logging
from config import LOG_DIR, LOG_FILE
from src.etl.api_client import fetch_data
from src.etl.data_storage import (
    save_to_ods,
    read_from_ods,
    save_to_dwd,
    save_to_dws,
    save_to_ads
)
from src.etl.data_processor import transform_ods_to_dwd

setup_logging()
logger = logging.getLogger(__name__)


def run_etl():
    """执行一次完整 ETL，返回统计信息；失败时抛出异常由调用方处理。"""
    started_at = datetime.now()
    logger.info("========== ETL 任务开始 ==========")

    raw_data = fetch_data()
    save_to_ods(raw_data)
    ods_rows = read_from_ods()
    dwd_records = transform_ods_to_dwd(ods_rows)
    save_to_dwd(dwd_records)
    save_to_dws()
    save_to_ads()

    elapsed = (datetime.now() - started_at).total_seconds()
    stats = {
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(elapsed, 2),
        "ods_rows": len(ods_rows),
        "dwd_rows": len(dwd_records),
    }
    logger.info("========== ETL 任务成功 | 耗时 %.2fs ==========", elapsed)
    return stats


def main():
    try:
        stats = run_etl()
        print("ETL 成功：", stats)
    except Exception:
        logger.exception("ETL 任务执行失败")
    finally:
        logger.info("========== ETL 任务结束 ==========")


if __name__ == "__main__":
    main()
