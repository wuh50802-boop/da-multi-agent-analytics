import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DWD_FIELDS = [
    "订单ID", "子订单ID", "平台", "店铺ID", "用户ID", "商品ID", "SKU",
    "商品名称", "达人UID", "达人名称", "订单状态", "售后状态", "支付方式",
    "提交时间", "支付时间", "收件省份", "收件城市", "数据来源",
    "购买数量", "订单总额", "商家实收", "买家实付", "退款金额", "结算金额",
    "达人佣金", "平台佣金", "运费", "优惠金额",
]

REQUIRED_FIELDS = ["订单ID", "平台", "提交时间"]


def _to_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def transform_ods_to_dwd(ods_rows):
    """将 ODS 原始订单清洗为 DWD 明细元组。

    清洗规则：
    1. 必需字段缺失 -> 跳过
    2. 金额字段非法（负数/非数字）-> 归零
    3. 未支付订单（支付时间为空）-> 金额字段强制归零，避免脏数据污染 GMV
    4. 勾稽校验：订单总额 != 买家实付 + 优惠金额 -> 记录告警但保留原值
    """

    dwd_records = []
    skipped = 0
    unpaid = 0
    inconsistent = 0

    for row in ods_rows:
        try:
            raw = row.get("原始数据", row.get("raw_data"))
            data = json.loads(raw) if isinstance(raw, str) else raw

            if any(not data.get(f) for f in REQUIRED_FIELDS):
                skipped += 1
                continue

            submit_dt = _to_datetime(data.get("提交时间"))
            if submit_dt is None:
                skipped += 1
                continue

            pay_dt = _to_datetime(data.get("支付时间"))
            is_unpaid = pay_dt is None
            if is_unpaid:
                unpaid += 1

            def amount(field):
                value = data.get(field, 0) or 0
                try:
                    result = float(value)
                except (ValueError, TypeError):
                    return 0.0
                if result < 0 or is_unpaid:
                    return 0.0
                return round(result, 2)

            order_amount = amount("订单总额")
            buyer_paid = amount("买家实付")
            discount = amount("优惠金额")
            if not is_unpaid and abs(order_amount - (buyer_paid + discount)) > 0.01:
                inconsistent += 1
                logger.warning("金额勾稽异常，订单：%s", data.get("订单ID"))

            values = []
            for field in DWD_FIELDS:
                value = data.get(field, "")
                if field in ("提交时间", "支付时间"):
                    dt = submit_dt if field == "提交时间" else pay_dt
                    value = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None
                elif field in ("订单总额", "商家实收", "买家实付", "退款金额", "结算金额",
                               "达人佣金", "平台佣金", "运费", "优惠金额"):
                    value = amount(field)
                elif field == "购买数量":
                    try:
                        value = int(value or 0)
                    except (ValueError, TypeError):
                        value = 0
                else:
                    value = str(value or "").strip()
                values.append(value)

            dwd_records.append(tuple(values))

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            logger.exception("ODS 数据转换失败：%s", row.get("源记录ID"))
            skipped += 1

    logger.info(
        "DWD 转换完成：原始 %s 条，成功 %s 条，跳过 %s 条，未支付 %s 条，勾稽异常 %s 条",
        len(ods_rows), len(dwd_records), skipped, unpaid, inconsistent
    )
    return dwd_records
