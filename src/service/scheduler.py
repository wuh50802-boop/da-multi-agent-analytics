"""定时调度器：对齐母版 n8n 的 Schedule Trigger（每天 02:00）。

职责：
1. 每天 02:00 自动执行 ETL（ODS → DWD → DWS → ADS）
2. 任务失败时记录状态与异常（对应母版 Error Trigger）
3. 通过 get_scheduler_status() 对外暴露运行快照
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from main import run_etl

logger = logging.getLogger(__name__)

# 母版 Schedule Trigger 配置：triggerAtHour = 2
ETL_HOUR = 2
ETL_MINUTE = 0

_scheduler = None
_last_run = None


def scheduled_etl():
    """定时任务入口：执行 ETL 并记录结果，异常不外抛（避免调度器停止）。"""
    global _last_run
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        stats = run_etl()
        _last_run = {
            "status": "success",
            "started_at": started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stats": stats,
            "error": None,
        }
        logger.info("定时 ETL 执行成功 | 时间：%s", started_at)
    except Exception as e:
        _last_run = {
            "status": "failed",
            "started_at": started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stats": None,
            "error": str(e),
        }
        logger.exception("定时 ETL 执行失败 | 时间：%s", started_at)


def start_scheduler():
    """启动后台调度器（幂等，重复调用不会创建多个实例）。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("调度器已在运行，跳过重复启动")
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        scheduled_etl,
        trigger=CronTrigger(hour=ETL_HOUR, minute=ETL_MINUTE),
        id="daily_etl",
        name="每日电商数仓 ETL",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "定时调度器已启动 | 每日 %02d:%02d 执行 ETL",
        ETL_HOUR,
        ETL_MINUTE,
    )
    return _scheduler


def shutdown_scheduler():
    """关闭调度器（FastAPI 关闭时调用）。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("定时调度器已关闭")


def get_scheduler_status():
    """返回调度器状态快照，供健康检查接口使用。"""
    job = None
    if _scheduler is not None:
        jobs = _scheduler.get_jobs()
        if jobs:
            j = jobs[0]
            job = {
                "id": j.id,
                "name": j.name,
                "next_run_time": (
                    j.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                    if j.next_run_time else None
                ),
            }
    return {
        "running": bool(_scheduler and _scheduler.running),
        "schedule": f"每天 {ETL_HOUR:02d}:{ETL_MINUTE:02d} (Asia/Shanghai)",
        "job": job,
        "last_run": _last_run,
    }
