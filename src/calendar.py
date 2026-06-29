"""发布日历 — 估算各指标未来发布日期。

设计思路：
1. 每个指标在 config 中配置一个默认 release_day（月频/季频）
2. 如果数据库中有历史 created_at，则用历史发布日的平均值修正
3. 根据最新数据期 + 频率，推算下一个数据期，再叠加上述 release_day
4. 过滤出未来 N 天内的预计发布事件

注意：created_at 是我们首次入库的时间，和真实发布日可能有偏差；
历史数据足够多时，平均值会逼近真实规律。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src.config import INDICATORS, IndicatorConfig


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
    if ind.frequency == "daily":
        # 日频：下一个工作日（简单处理，不考虑节假日）
        candidate = _parse_period_date(latest_date, ind.frequency) + timedelta(days=1)
        while candidate < from_date:
            candidate += timedelta(days=1)
        return candidate

    # 月频/季频
    period_date = _parse_period_date(latest_date, ind.frequency)
    next_period = _add_one_period(period_date, ind.frequency)

    day = release_day or ind.release_day or 15
    candidate = _date_with_day(next_period, day)

    # 如果已经过期（数据延迟），继续往后推一个周期
    while candidate < from_date:
        next_period = _add_one_period(next_period, ind.frequency)
        candidate = _date_with_day(next_period, day)

    return candidate


def build_release_calendar(
    snapshot: dict[str, Any],
    from_date: date | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """根据快照数据构建未来 N 天的发布日历。

    返回按日期排序的事件列表，每个事件包含：
    - date: 预计发布日期（YYYY-MM-DD）
    - indicators: 该日期预计发布的指标列表
    """
    from_date = from_date or date.today()
    to_date = from_date + timedelta(days=days)

    events_by_date: dict[date, dict[str, Any]] = {}

    for ind_data in snapshot.get("indicators", []):
        slug = ind_data["slug"]
        ind = next((i for i in INDICATORS if i.slug == slug), None)
        if not ind:
            continue

        latest_date = ind_data.get("latest_date")
        if not latest_date:
            continue

        history = ind_data.get("history", [])
        release_day = _effective_release_day(ind, history)

        release_date = _next_release_date(ind, latest_date, release_day, from_date)
        if not release_date:
            continue

        if from_date <= release_date <= to_date:
            if release_date not in events_by_date:
                events_by_date[release_date] = {
                    "date": release_date.isoformat(),
                    "indicators": [],
                }
            events_by_date[release_date]["indicators"].append(
                {
                    "slug": slug,
                    "name": ind.name,
                    "short_name": ind.short_name,
                    "category": ind.category,
                    "frequency": ind.frequency,
                    "latest_date": latest_date,
                }
            )

    # 按日期排序
    return [events_by_date[d] for d in sorted(events_by_date)]
