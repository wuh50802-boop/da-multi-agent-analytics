"""输出治理：查询结果结构化导出（CSV，Excel 可直接打开）。

母版用图表/Excel 智能分离，这里用零依赖 CSV 方案实现数据分离交付。
"""
import csv
import io
import logging

logger = logging.getLogger(__name__)


def export_results_csv(query_results):
    """把查询结果为 CSV 字符串（带 BOM，Excel 中文不乱码）。"""
    if not query_results:
        return ""

    keys = list(query_results[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys)
    writer.writeheader()
    for row in query_results:
        writer.writerow({
            k: ("" if v is None else v) for k, v in row.items()
        })
    # UTF-8 BOM 让 Excel 正确识别中文
    return "\ufeff" + buf.getvalue()


def split_report_and_data(report, query_results):
    """输出分离：文字报告 + 结构化数据两部分。"""
    return {
        "report": report,
        "data": query_results or [],
        "data_csv": export_results_csv(query_results),
        "data_count": len(query_results or []),
    }
