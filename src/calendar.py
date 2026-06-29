"""发布日历 — 估算各指标未来发布日期。

设计思路：
1. 每个指标在 config 中配置一个默认 release_day（月频/季频）
2. 如果数据库中有历史 created_at，则用历史发布日的平均值修正
3. 根据最新数据期 + 频率，推算下一个数据期，再叠加上述 release_day
4. 为页面生成当月 + 次月的日历卡片数据

注意：created_at 是我们首次入库的时间，和真实发布日可能有偏差；
历史数据足够多时，平均值会逼近真实规律。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src.config import INDICATORS, IndicatorConfig


_WEEKDAY_HEADERS = ["一", "二", "三", "四", "五", "六", "日"]


def _parse_period_date(period_str: str, frequency: str) -> date:
    """把指标的数据期字符串解析为 date。

    - monthly: "2026-05" 或 "2026-06-22" → 2026-05-01 / 2026-06-01
    - quarterly: "2026-Q1" 或 "2026-03-22" → 2026-01-01 / 2026-03-01
    - daily: "2026-06-29" → 2026-06-29
    """
    period_str = str(period_str).strip()

    # 日频或月/季频里混入了完整日期，先按日解析再取月初/季初
    if len(period_str) == 10 and period_str.count("-") == 2:
        d = datetime.strptime(period_str, "%Y-%m-%d").date()
        if frequency == "daily":
            return d
        if frequency == "monthly":
            return date(d.year, d.month, 1)
        if frequency == "quarterly":
            quarter_month = ((d.month - 1) // 3) * 3 + 1
            return date(d.year, quarter_month, 1)

    if frequency == "daily":
        return datetime.strptime(period_str, "%Y-%m-%d").date()
    if frequency == "monthly":
        return datetime.strptime(period_str, "%Y-%m").date()
    if frequency == "quarterly":
        year, q = period_str.split("-Q")
        month = (int(q) - 1) * 3 + 1
        return date(int(year), month, 1)
    raise ValueError(f"不支持的频率: {frequency}")


def _add_one_period(d: date, frequency: str) -> date:
    """给 date 加一个频率周期。"""
    if frequency == "daily":
        return d + timedelta(days=1)
    if frequency == "monthly":
        if d.month == 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, d.month + 1, 1)
    if frequency == "quarterly":
        if d.month == 10:
            return date(d.year + 1, 1, 1)
        return date(d.year, d.month + 3, 1)
    raise ValueError(f"不支持的频率: {frequency}")


def _add_month(d: date) -> date:
    """返回下个月 1 日。"""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _date_with_day(d: date, day: int) -> date:
    """把 date 的日设置为指定值（自动处理月末越界）。"""
    max_day = _days_in_month(d.year, d.month)
    return date(d.year, d.month, min(day, max_day))


def _days_in_month(year: int, month: int) -> int:
    """返回某年某月的天数。"""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def _parse_created_at(created_at: str | None) -> date | None:
    """解析 created_at 字符串为 date。"""
    if not created_at:
        return None
    try:
        # 支持 "2026-06-29T06:07:00Z" 或 "2026-06-29 06:07:00"
        s = created_at.replace("Z", "+00:00")
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _effective_release_day(ind: IndicatorConfig, history: list[dict[str, Any]]) -> int | None:
    """计算有效发布日。

    - 日频指标不需要 release_day，返回 None
    - 只有当历史数据足够多（>=6 条）且 created_at 分布在至少 3 个不同日期时，
      才用历史发布日的平均值修正，避免新指标一次性入库导致预测失真
    - 否则使用 config 中的 release_day
    """
    if ind.frequency == "daily":
        return None

    days: list[int] = []
    distinct_dates: set[str] = set()
    for h in history:
        created = _parse_created_at(h.get("created_at"))
        if created:
            days.append(created.day)
            distinct_dates.add(created.isoformat())

    if len(days) >= 6 and len(distinct_dates) >= 3:
        avg_day = int(round(sum(days) / len(days)))
        if 1 <= avg_day <= 28:
            return avg_day

    return ind.release_day


def _next_release_date(
    ind: IndicatorConfig,
    latest_date: str,
    release_day: int | None,
    from_date: date,
) -> date | None:
    """计算下一个预计发布日期（>= from_date）。"""
    period_date = _parse_period_date(latest_date, ind.frequency)
    next_period = _add_one_period(period_date, ind.frequency)

    day = release_day or ind.release_day or 15
    candidate = _date_with_day(next_period, day)

    # 如果已经过期（数据延迟），继续往后推一个周期
    while candidate < from_date:
        next_period = _add_one_period(next_period, ind.frequency)
        candidate = _date_with_day(next_period, day)

    return candidate


def _append_event(
    events_by_date: dict[date, list[dict[str, Any]]],
    release_date: date,
    ind: IndicatorConfig,
    latest_date: str,
) -> None:
    """把一个指标事件追加到指定日期。"""
    events_by_date.setdefault(release_date, []).append(
        {
            "slug": ind.slug,
            "name": ind.name,
            "short_name": ind.short_name,
            "category": ind.category,
            "frequency": ind.frequency,
            "latest_date": latest_date,
        }
    )


def _build_month_grid(month_start: date, events_by_date: dict[date, list[dict[str, Any]]]) -> dict[str, Any]:
    """构建单个月份的日历格子。"""
    days_count = _days_in_month(month_start.year, month_start.month)
    first_weekday = month_start.weekday()  # 周一=0

    cells: list[dict[str, Any]] = []
    for _ in range(first_weekday):
        cells.append({"empty": True})

    for day in range(1, days_count + 1):
        current = date(month_start.year, month_start.month, day)
        indicators = events_by_date.get(current, [])
        cells.append(
            {
                "empty": False,
                "date": current.isoformat(),
                "day": day,
                "is_today": current == date.today(),
                "is_weekend": current.weekday() >= 5,
                "indicators": indicators,
            }
        )

    while len(cells) % 7 != 0:
        cells.append({"empty": True})

    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    return {
        "year": month_start.year,
        "month": month_start.month,
        "title": f"{month_start.year}年{month_start.month}月",
        "weekday_headers": _WEEKDAY_HEADERS,
        "weeks": weeks,
    }


def build_release_calendar(
    snapshot: dict[str, Any],
    from_date: date | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """兼容旧接口：返回未来 N 天事件列表。"""
    from_date = from_date or date.today()
    to_date = from_date + timedelta(days=days)

    events_by_date: dict[date, list[dict[str, Any]]] = {}

    for ind_data in snapshot.get("indicators", []):
        slug = ind_data["slug"]
        ind = next((i for i in INDICATORS if i.slug == slug), None)
        if not ind or ind.frequency == "daily":
            continue

        latest_date = ind_data.get("latest_date")
        if not latest_date:
            continue

        release_day = _effective_release_day(ind, ind_data.get("history", []))
        release_date = _next_release_date(ind, latest_date, release_day, from_date)
        if release_date and from_date <= release_date <= to_date:
            _append_event(events_by_date, release_date, ind, latest_date)

    return [
        {"date": d.isoformat(), "indicators": events_by_date[d]}
        for d in sorted(events_by_date)
    ]


def build_release_calendar_months(
    snapshot: dict[str, Any],
    from_date: date | None = None,
) -> dict[str, Any]:
    """构建当月 + 次月日历卡片数据。

    日频指标不铺满日历，只在说明中展示，避免日历被 USD/CNY 填满。
    """
    from_date = from_date or date.today()
    month_start = date(from_date.year, from_date.month, 1)
    next_month_start = _add_month(month_start)
    after_next_month_start = _add_month(next_month_start)

    events_by_date: dict[date, list[dict[str, Any]]] = {}
    daily_indicators: list[dict[str, Any]] = []

    for ind_data in snapshot.get("indicators", []):
        slug = ind_data["slug"]
        ind = next((i for i in INDICATORS if i.slug == slug), None)
        if not ind:
            continue

        latest_date = ind_data.get("latest_date")
        if not latest_date:
            continue

        if ind.frequency == "daily":
            daily_indicators.append(
                {
                    "slug": slug,
                    "name": ind.name,
                    "short_name": ind.short_name,
                    "category": ind.category,
                    "frequency": ind.frequency,
                    "latest_date": latest_date,
                }
            )
            continue

        release_day = _effective_release_day(ind, ind_data.get("history", []))
        release_date = _next_release_date(ind, latest_date, release_day, month_start)
        if release_date and month_start <= release_date < after_next_month_start:
            _append_event(events_by_date, release_date, ind, latest_date)

    return {
        "months": [
            _build_month_grid(month_start, events_by_date),
            _build_month_grid(next_month_start, events_by_date),
        ],
        "daily_indicators": daily_indicators,
    }
