from src.storage.usage_storage import get_dashboard_usage_trend

print("========== 全部历史 Token 趋势 ==========")

all_trend = get_dashboard_usage_trend()

for item in all_trend:
    print(item)


print("\n========== 最近 7 天 Token 趋势 ==========")

week_trend = get_dashboard_usage_trend(
    start_time="2026-11-18 00:00:00",
    end_time="2026-11-25 00:00:00"
)

for item in week_trend:
    print(item)