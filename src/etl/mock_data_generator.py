"""模拟电商订单数据生成器。

生成 1000 条覆盖抖店 / 微信 / 小红书三平台的订单，字段与 schema.sql
的 dwd_orders 一一对应。数据自带勾稽关系（GMV = 实付 + 优惠，净 GMV = GMV - 退款），
并植入少量脏数据（未支付、退款、缺失字段），供后续 ODS->DWD 清洗演示。

用法：
    python src/mock_data_generator.py
    python src/mock_data_generator.py --count 2000 --seed 42
"""

import argparse
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "mock_orders.csv"

PLATFORMS = ["抖店", "微信", "小红书"]

KOLS = [
    ("K001", "兰心好物"), ("K002", "小满妈妈"), ("K003", "阿哲严选"),
    ("K004", "安安的小窝"), ("K005", "硅谷憨爸"), ("K006", "小板牙"),
    ("K007", "三娃小厨"), ("K008", "粥悦悦"), ("K009", "丹妈童书"),
    ("K010", "修养生息"), ("K011", "雯小雯"), ("K012", "二重奏宝妈"),
]

PRODUCTS = [
    ("P001", "儿童绘本套装", 89.0),
    ("P002", "厨房收纳置物架", 129.0),
    ("P003", "女士纯棉T恤", 79.0),
    ("P004", "便携榨汁杯", 159.0),
    ("P005", "学生护眼台灯", 199.0),
    ("P006", "家用清洁套装", 69.0),
    ("P007", "宝宝辅食机", 299.0),
    ("P008", "运动保温水壶", 119.0),
]

PROVINCES = ["广东", "浙江", "江苏", "四川", "山东", "河南", "湖北", "福建"]
CITIES = {
    "广东": ["广州", "深圳", "东莞"], "浙江": ["杭州", "宁波", "温州"],
    "江苏": ["南京", "苏州", "无锡"], "四川": ["成都", "绵阳"],
    "山东": ["济南", "青岛"], "河南": ["郑州", "洛阳"],
    "湖北": ["武汉", "宜昌"], "福建": ["福州", "厦门"],
}
PAY_METHODS = ["微信支付", "支付宝", "银行卡", "货到付款"]
ORDER_STATUS = ["已完成", "已发货", "待发货", "已关闭"]
AFTERSALE_STATUS = ["无售后", "全额退款", "部分退款", "售后关闭"]

FIELDS = [
    "订单ID", "子订单ID", "平台", "店铺ID", "用户ID", "商品ID", "SKU",
    "商品名称", "达人UID", "达人名称", "订单状态", "售后状态", "支付方式",
    "提交时间", "支付时间", "收件省份", "收件城市", "数据来源",
    "购买数量", "订单总额", "商家实收", "买家实付", "退款金额", "结算金额",
    "达人佣金", "平台佣金", "运费", "优惠金额",
]


def money(value):
    return round(float(value), 2)


def make_order(idx, rng, start_date):
    platform = rng.choice(PLATFORMS)
    kol_uid, kol_name = rng.choice(KOLS)
    product_id, product_name, price = rng.choice(PRODUCTS)
    qty = rng.randint(1, 3)
    province = rng.choice(PROVINCES)
    city = rng.choice(CITIES[province])

    submit_dt = start_date + timedelta(
        days=rng.randint(0, 29),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
    )

    discount = money(rng.uniform(0, 20))
    freight = money(rng.choice([0, 0, 8, 12]))
    order_amount = money(price * qty + freight)
    buyer_paid = money(max(order_amount - discount, 0))

    # 10% 未支付：支付时间为空、金额为 0，制造脏数据
    unpaid = rng.random() < 0.10
    if unpaid:
        pay_time = ""
        status = "已关闭"
        buyer_paid = 0.0
        merchant_income = 0.0
        settlement = 0.0
    else:
        pay_time = (submit_dt + timedelta(minutes=rng.randint(1, 180))).strftime("%Y-%m-%d %H:%M:%S")
        status = rng.choice(ORDER_STATUS[:-1])
        merchant_income = money(buyer_paid * rng.uniform(0.80, 0.95))
        settlement = merchant_income

    # 12% 退款：产生退款金额与售后状态
    refunded = (not unpaid) and rng.random() < 0.12
    if refunded:
        aftersale = rng.choice(["全额退款", "部分退款"])
        refund_amount = money(buyer_paid if aftersale == "全额退款" else buyer_paid * 0.4)
        settlement = money(settlement - refund_amount)
    else:
        aftersale = "无售后"
        refund_amount = 0.0

    kol_commission = money(buyer_paid * 0.15) if not unpaid else 0.0
    platform_commission = money(buyer_paid * 0.05) if not unpaid else 0.0

    return {
        "订单ID": f"{platform[:2]}{submit_dt.strftime('%Y%m%d')}{idx:06d}",
        "子订单ID": f"S{idx:06d}" if rng.random() < 0.3 else "",
        "平台": platform,
        "店铺ID": f"SHOP{PLATFORMS.index(platform) + 1:03d}",
        "用户ID": f"U{rng.randint(1, 400):05d}",
        "商品ID": product_id,
        "SKU": f"{product_id}-SK{rng.randint(1, 5):02d}",
        "商品名称": product_name,
        "达人UID": kol_uid,
        "达人名称": kol_name,
        "订单状态": status,
        "售后状态": aftersale,
        "支付方式": rng.choice(PAY_METHODS),
        "提交时间": submit_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "支付时间": pay_time,
        "收件省份": province,
        "收件城市": city,
        "数据来源": "mock_generator",
        "购买数量": qty,
        "订单总额": order_amount,
        "商家实收": merchant_income,
        "买家实付": buyer_paid,
        "退款金额": refund_amount,
        "结算金额": settlement,
        "达人佣金": kol_commission,
        "平台佣金": platform_commission,
        "运费": freight,
        "优惠金额": discount,
    }


def generate(count=1000, seed=2026):
    rng = random.Random(seed)
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=29)
    return [make_order(i + 1, rng, start_date) for i in range(count)]


def save_csv(orders, path=OUTPUT_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(orders)
    return path


def save_json(orders, path=None):
    path = path or DATA_DIR / "mock_orders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="生成模拟电商订单数据")
    parser.add_argument("--count", type=int, default=1000, help="生成条数，默认 1000")
    parser.add_argument("--seed", type=int, default=2026, help="随机种子，默认 2026")
    args = parser.parse_args()

    orders = generate(args.count, args.seed)
    csv_path = save_csv(orders)
    json_path = save_json(orders)

    paid = sum(1 for o in orders if o["支付时间"])
    refunded = sum(1 for o in orders if o["退款金额"] > 0)
    total_gmv = money(sum(o["订单总额"] for o in orders if o["支付时间"]))
    platforms = {p: sum(1 for o in orders if o["平台"] == p) for p in PLATFORMS}

    print(f"生成完成：{len(orders)} 条")
    print(f"  CSV  -> {csv_path}")
    print(f"  JSON -> {json_path}")
    print(f"  已支付 {paid} / 未支付 {len(orders) - paid} / 有退款 {refunded}")
    print(f"  支付订单 GMV 合计：{total_gmv:,.2f} 元")
    print(f"  平台分布：{platforms}")


if __name__ == "__main__":
    main()
