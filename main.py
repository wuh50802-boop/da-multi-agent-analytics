
import logging
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


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler()
        ],
        force=True
    )


def main():
    setup_logging()

    logger = logging.getLogger(__name__)

    try:
        logger.info("========== ETL 任务开始 ==========")

        # 1. 读取模拟订单原始数据
        raw_data = fetch_data()

        # 2. 保存到 ODS
        save_to_ods(raw_data)

        # 3. 从 ODS 读取原始数据
        ods_rows = read_from_ods()

        # 4. 转换为 DWD 数据
        dwd_records = transform_ods_to_dwd(ods_rows)

        # 5. 保存到 DWD
        save_to_dwd(dwd_records)

        # 6. 生成 DWS 汇总数据  
        save_to_dws()
        
        # 7. 生成 ADS 分析数据
        save_to_ads()

        logger.info("========== ETL 任务成功 ==========")

    except Exception:
        logger.exception("ETL 任务执行失败")

    finally:
        logger.info("========== ETL 任务结束 ==========")


if __name__ == "__main__":
    main()
