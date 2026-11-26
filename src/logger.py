
import logging

from config import LOG_DIR, LOG_FILE


def setup_logging():
    """统一初始化项目日志"""

    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 同时输出到终端和日志文件
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
        handlers=[
            logging.FileHandler(
                LOG_FILE,
                encoding="utf-8"
            ),
            logging.StreamHandler()
        ],
        force=True
    )
