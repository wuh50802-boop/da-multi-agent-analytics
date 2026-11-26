
import logging
import time

from openai import (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)

logger = logging.getLogger(__name__)

# 只对这些临时性 API 错误进行重试
RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)


def retry_call(func, *args, max_retries=3, delay=2, **kwargs):
    """
    执行函数，遇到临时性 API 错误时自动重试。

    max_retries：最多重试次数，不包括第一次执行
    delay：第一次重试前的等待秒数
    """

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)

        except RETRYABLE_ERRORS:
            if attempt == max_retries:
                logger.exception(
                    "任务重试次数已用完，停止执行"
                )
                raise

            wait_time = delay * (2 ** attempt)

            logger.warning(
                "遇到临时 API 错误，第 %s 次重试，等待 %s 秒",
                attempt + 1,
                wait_time
            )

            time.sleep(wait_time)
