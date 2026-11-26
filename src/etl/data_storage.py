import json
import logging

import mysql.connector

from config import DB_CONFIG
from src.etl.data_processor import DWD_FIELDS

logger = logging.getLogger(__name__)


def _connect():
    return mysql.connector.connect(**DB_CONFIG)


def save_to_ods(raw_data):
    """原始订单 JSON 写入 ODS 层。"""
    connection = None
    cursor = None
    try:
        connection = _connect()
        cursor = connection.cursor()
        sql = """
        INSERT INTO ods_orders_raw (`数据来源`, `源记录ID`, `原始数据`)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            `原始数据` = VALUES(`原始数据`),
            `摄入时间` = CURRENT_TIMESTAMP
        """
        records = [
            (item.get("平台", ""), item["订单ID"], json.dumps(item, ensure_ascii=False))
            for item in raw_data
        ]
        cursor.executemany(sql, records)
        connection.commit()
        logger.info("ODS 数据写入成功：%s 条", len(records))
    except Exception:
        if connection:
            connection.rollback()
        logger.exception("ODS 数据写入失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def read_from_ods():
    """从 ODS 层读取原始订单。"""
    connection = None
    cursor = None
    try:
        connection = _connect()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT `数据来源`, `源记录ID`, `原始数据`
            FROM ods_orders_raw
        """)
        rows = cursor.fetchall()
        logger.info("从 ODS 读取数据：%s 条", len(rows))
        return rows
    except mysql.connector.Error:
        logger.exception("ODS 数据读取失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def save_to_dwd(records):
    """清洗后的订单明细写入 DWD 层。"""
    connection = None
    cursor = None
    try:
        connection = _connect()
        cursor = connection.cursor()
        cols = ", ".join(f"`{f}`" for f in DWD_FIELDS)
        placeholders = ", ".join(["%s"] * len(DWD_FIELDS))
        sql = f"""
        INSERT INTO dwd_orders ({cols})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
            `商家实收` = VALUES(`商家实收`),
            `买家实付` = VALUES(`买家实付`),
            `退款金额` = VALUES(`退款金额`),
            `结算金额` = VALUES(`结算金额`),
            `更新时间` = CURRENT_TIMESTAMP
        """
        cursor.executemany(sql, records)
        connection.commit()
        logger.info("DWD 数据写入成功：%s 条", len(records))
    except mysql.connector.Error:
        if connection:
            connection.rollback()
        logger.exception("DWD 数据写入失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def save_to_dws():
    """按 达人 x 日期 x 平台 聚合，生成 DWS 日汇总。"""
    connection = None
    cursor = None
    try:
        connection = _connect()
        cursor = connection.cursor()
        sql = """
        INSERT INTO dws_kol_daily (
            `统计日期`, `平台`, `达人UID`, `达人名称`,
            `支付订单数`, `销量`, `GMV`, `实付金额`,
            `退款金额`, `净GMV`, `达人佣金`
        )
        SELECT
            DATE(`支付时间`), `平台`, `达人UID`,
            MAX(`达人名称`),
            COUNT(*),
            SUM(`购买数量`),
            SUM(`订单总额`),
            SUM(`买家实付`),
            SUM(`退款金额`),
            SUM(`订单总额` - `退款金额`),
            SUM(`达人佣金`)
        FROM dwd_orders
        WHERE `支付时间` IS NOT NULL
        GROUP BY DATE(`支付时间`), `平台`, `达人UID`
        ON DUPLICATE KEY UPDATE
            `达人名称` = VALUES(`达人名称`),
            `支付订单数` = VALUES(`支付订单数`),
            `销量` = VALUES(`销量`),
            `GMV` = VALUES(`GMV`),
            `实付金额` = VALUES(`实付金额`),
            `退款金额` = VALUES(`退款金额`),
            `净GMV` = VALUES(`净GMV`),
            `达人佣金` = VALUES(`达人佣金`),
            `更新时间` = CURRENT_TIMESTAMP
        """
        cursor.execute(sql)
        connection.commit()
        # rowcount 在 ON DUPLICATE KEY UPDATE 下会把更新算作 2 行，
        # 用实际表行数更能反映结果（幂等覆盖后行数稳定）
        cursor.execute("SELECT COUNT(*) FROM dws_kol_daily")
        total_rows = cursor.fetchone()[0]
        logger.info("DWS 达人日汇总生成成功，表内共 %s 行", total_rows)
    except mysql.connector.Error:
        if connection:
            connection.rollback()
        logger.exception("DWS 数据生成失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def save_to_ads():
    """按 达人 x 月份 x 平台 聚合，生成 ADS 月榜（含排名）。"""
    connection = None
    cursor = None
    try:
        connection = _connect()
        cursor = connection.cursor()
        sql = """
        INSERT INTO ads_kol_rank (
            `统计月份`, `平台`, `达人UID`, `达人名称`,
            `月度GMV`, `支付订单数`, `退货率`, `排名`
        )
        SELECT
            `统计月份`, `平台`, `达人UID`, `达人名称`,
            `月度GMV`, `支付订单数`, `退货率`,
            RANK() OVER (
                PARTITION BY `统计月份`, `平台`
                ORDER BY `月度GMV` DESC
            )
        FROM (
            SELECT
                DATE_FORMAT(`统计日期`, '%Y-%m') AS `统计月份`,
                `平台`, `达人UID`, MAX(`达人名称`) AS `达人名称`,
                SUM(`GMV`) AS `月度GMV`,
                SUM(`支付订单数`) AS `支付订单数`,
                CASE WHEN SUM(`支付订单数`) = 0 THEN 0
                     ELSE ROUND(SUM(`退款金额` > 0) / SUM(`支付订单数`), 4)
                END AS `退货率`
            FROM dws_kol_daily
            GROUP BY DATE_FORMAT(`统计日期`, '%Y-%m'), `平台`, `达人UID`
        ) agg
        ON DUPLICATE KEY UPDATE
            `达人名称` = VALUES(`达人名称`),
            `月度GMV` = VALUES(`月度GMV`),
            `支付订单数` = VALUES(`支付订单数`),
            `退货率` = VALUES(`退货率`),
            `排名` = VALUES(`排名`),
            `更新时间` = CURRENT_TIMESTAMP
        """
        cursor.execute(sql)
        connection.commit()
        cursor.execute("SELECT COUNT(*) FROM ads_kol_rank")
        total_rows = cursor.fetchone()[0]
        logger.info("ADS 达人月榜生成成功，表内共 %s 行", total_rows)
    except mysql.connector.Error:
        if connection:
            connection.rollback()
        logger.exception("ADS 数据生成失败")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
