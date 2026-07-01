"""AKShare 数据拉取 — 从 AKShare 获取宏观经济指标数据。

设计要点：
1. 中文列名在 PowerShell 终端会乱码，但 Python 内部读取无问题，按位置取列更稳定
2. 每个指标的拉取函数返回 FetchResult(latest, history)，统一接口
3. 不同指标的日期格式各异，归一化为标准 ISO 字符串：
   - 月度数据：YYYY-MM
   - 日度数据：YYYY-MM-DD
   - 季度数据：YYYY-Qn（如 2026-Q1）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import akshare as ak
import pandas as pd


@dataclass
class IndicatorData:
    """单个数据点。"""

    slug: str
    date: str
    value: float
    period: str  # monthly / daily / quarterly


@dataclass
class FetchResult:
    """拉取结果：最新数据点，以及全部历史数据。"""

    latest: IndicatorData
    history: list[IndicatorData]


# ════════════════════ 日期归一化函数 ════════════════════

def _normalize_year_month(raw: str) -> str:
    """归一化 "2026年05月份" → "2026-05"。"""
    raw = str(raw).replace("年", "-").replace("月份", "").replace("月", "").strip()
    parts = raw.split("-")
    if len(parts) == 2:
        return f"{parts[0]}-{parts[1].zfill(2)}"
    return raw


def _normalize_iso_date(raw: Any) -> str:
    """日期对象或 ISO 字符串 → "YYYY-MM-DD"。"""
    if hasattr(raw, "strftime"):
        return raw.strftime("%Y-%m-%d")
    return str(raw).strip()[:10]


def _normalize_gdp_period(raw: str) -> str:
    """归一化 GDP 期间。

    "2026年第1季度" / "2026年1-2季度" / "2025年1-4季度" → "2026-Q1" 等
    取最右侧的季度数字作为期末。
    """
    s = str(raw).strip()
    # 提取年份
    year = s.split("年")[0]
    # 提取季度（取 "-" 后或单个数字）
    quarter_part = s.split("年")[1] if "年" in s else s
    # 形如 "1-4季度" → 4，"第1季度" → 1，"1季度" → 1
    quarter_part = quarter_part.replace("季度", "").replace("第", "").strip()
    if "-" in quarter_part:
        q = quarter_part.split("-")[-1]
    else:
        q = quarter_part
    return f"{year}-Q{q.strip()}"


# ════════════════════ 通用拉取构造器 ════════════════════

def _build_history(
    df: pd.DataFrame,
    *,
    slug: str,
    period: str,
    date_col_idx: int,
    value_col_idx: int,
    date_normalizer,
    tail_n: int | None = None,
) -> FetchResult:
    """通用：按列位置从 DataFrame 抽取 (date, value) 序列。"""
    if tail_n is not None:
        df = df.tail(tail_n)

    date_col = df.columns[date_col_idx]
    value_col = df.columns[value_col_idx]

    history: list[IndicatorData] = []
    for _, row in df.iterrows():
        raw_value = row[value_col]
        if pd.isna(raw_value):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue

        date_str = date_normalizer(row[date_col])
        history.append(IndicatorData(slug=slug, date=date_str, value=value, period=period))

    # 按日期排序（字符串排序对 ISO 格式有效）
    history.sort(key=lambda x: x.date)

    if not history:
        raise RuntimeError(f"{slug}: 未拉取到任何有效数据点")

    return FetchResult(latest=history[-1], history=history)


# ════════════════════ 增长篇 ════════════════════

# GDP 表在一次运行内会被同比 fetcher 与绝对值 secondary 共用，缓存避免重复调用。
_gdp_df: pd.DataFrame | None = None


def _get_gdp_df() -> pd.DataFrame:
    """获取 GDP 表（带一次运行周期内的缓存）。"""
    global _gdp_df
    if _gdp_df is None:
        _gdp_df = ak.macro_china_gdp()
    return _gdp_df


def _fetch_gdp() -> FetchResult:
    """GDP 同比增速（季度），数据源：国家统计局。

    AKShare `macro_china_gdp` 返回累计同比数据。列结构：
        季度 | 国内生产总值-绝对值 | 国内生产总值-同比增长 | ...
    """
    df = _get_gdp_df()
    return _build_history(
        df,
        slug="gdp",
        period="quarterly",
        date_col_idx=0,
        value_col_idx=2,  # 国内生产总值-同比增长
        date_normalizer=_normalize_gdp_period,
    )


def _fetch_gdp_absolute() -> FetchResult:
    """GDP 绝对值（季度，累计值，单位亿元），数据源：国家统计局。

    与 `_fetch_gdp` 同源，取「国内生产总值-绝对值」列。
    """
    df = _get_gdp_df()
    return _build_history(
        df,
        slug="gdp_absolute",
        period="quarterly",
        date_col_idx=0,
        value_col_idx=1,  # 国内生产总值-绝对值
        date_normalizer=_normalize_gdp_period,
    )


def _fetch_pmi() -> FetchResult:
    """PMI 制造业指数（月度），数据源：国家统计局。

    AKShare `macro_china_pmi` 列结构：
        月份 | 制造业-指数 | 制造业-同比增长 | 非制造业-指数 | 非制造业-同比增长
    """
    df = ak.macro_china_pmi()
    return _build_history(
        df,
        slug="pmi",
        period="monthly",
        date_col_idx=0,
        value_col_idx=1,  # 制造业-指数
        date_normalizer=_normalize_year_month,
    )


def _fetch_industrial_production() -> FetchResult:
    """规模以上工业增加值同比（月度），数据源：国家统计局。

    AKShare `macro_china_gyzjz` 列结构：
        月份 | 同比增长 | 累计增长 | 发布时间
    （旧源 `macro_china_industrial_production_yoy` 走金十中转，已停更在 2025-08，
      改用统计局口径的 `macro_china_gyzjz`，数据更及时。）
    """
    df = ak.macro_china_gyzjz()
    return _build_history(
        df,
        slug="industrial_production",
        period="monthly",
        date_col_idx=0,
        value_col_idx=1,  # 同比增长
        date_normalizer=_normalize_year_month,
    )


def _fetch_retail_sales() -> FetchResult:
    """社会消费品零售总额同比（月度），数据源：国家统计局。

    AKShare `macro_china_consumer_goods_retail` 列结构：
        月份 | 当月 | 同比增长 | 环比增长 | 累计 | 累计-同比增长
    """
    df = ak.macro_china_consumer_goods_retail()
    return _build_history(
        df,
        slug="retail_sales",
        period="monthly",
        date_col_idx=0,
        value_col_idx=2,  # 同比增长
        date_normalizer=_normalize_year_month,
    )


# ════════════════════ 物价篇 ════════════════════

# CPI 表在一次运行内会被同比 fetcher 与环比 secondary 共用，缓存避免重复调用。
_cpi_df: pd.DataFrame | None = None


def _get_cpi_df() -> pd.DataFrame:
    """获取 CPI 表（带一次运行周期内的缓存）。"""
    global _cpi_df
    if _cpi_df is None:
        _cpi_df = ak.macro_china_cpi()
    return _cpi_df


def _fetch_cpi() -> FetchResult:
    """CPI 同比（月度），数据源：国家统计局。"""
    df = _get_cpi_df()
    return _build_history(
        df,
        slug="cpi",
        period="monthly",
        date_col_idx=0,
        value_col_idx=2,  # 全国-同比增长
        date_normalizer=_normalize_year_month,
    )


def _fetch_cpi_mom() -> FetchResult:
    """CPI 环比（月度），数据源：国家统计局。

    与 `_fetch_cpi` 同源，取「全国-环比增长」列（idx 3）。
    """
    df = _get_cpi_df()
    return _build_history(
        df,
        slug="cpi_mom",
        period="monthly",
        date_col_idx=0,
        value_col_idx=3,  # 全国-环比增长
        date_normalizer=_normalize_year_month,
    )


def _fetch_ppi() -> FetchResult:
    """PPI 同比（月度），数据源：国家统计局。

    AKShare `macro_china_ppi` 列结构：
        月份 | 当月 | 当月同比增长 | 累计
    """
    df = ak.macro_china_ppi()
    return _build_history(
        df,
        slug="ppi",
        period="monthly",
        date_col_idx=0,
        value_col_idx=2,  # 当月同比增长
        date_normalizer=_normalize_year_month,
    )


def _fetch_ppi_mom() -> FetchResult | None:
    """PPI 环比（月度）—— 预留接口。

    AKShare 的 `macro_china_ppi` 及东财 PPI 接口均只提供同比，不含环比；
    免费结构化源普遍缺 PPI 环比。此处先返回 None，图表仅展示同比。
    待接入可靠源（统计局新闻稿抓取 / 手动 JSON / 付费源）后在此实现即可，
    上层会自动开始展示环比曲线。
    """
    return None


# ════════════════════ 货币篇 ════════════════════

# 同一次 pipeline 运行中，M2 / M1 / M1-M2 剪刀差共用同一份数据源，
# 避免对 AKShare 的 `macro_china_money_supply` 重复调用 3 次。
_money_supply_df: pd.DataFrame | None = None


def _get_money_supply_df() -> pd.DataFrame:
    """获取货币供应量表（带一次运行周期内的缓存）。"""
    global _money_supply_df
    if _money_supply_df is None:
        _money_supply_df = ak.macro_china_money_supply()
    return _money_supply_df


def _fetch_usd_cny() -> FetchResult:
    """美元/人民币汇率中间价（每日），数据源：国家外汇管理局。

    AKShare `currency_boc_safe` 列结构：日期 | 美元 | 欧元 | 日元 | ...
    数据单位：每 100 单位外币兑人民币。
    """
    df = ak.currency_boc_safe()
    return _build_history(
        df,
        slug="usd_cny",
        period="daily",
        date_col_idx=0,
        value_col_idx=1,  # 美元（每100美元兑人民币）
        date_normalizer=_normalize_iso_date,
        tail_n=365,
    )


def _fetch_lpr_1y() -> FetchResult:
    """LPR 1年期（月度公布），数据源：全国银行间同业拆借中心。

    AKShare `macro_china_lpr` 列结构：
        TRADE_DATE | LPR1Y | LPR5Y | RATE_1 | RATE_2
    """
    df = ak.macro_china_lpr()
    return _build_history(
        df,
        slug="lpr_1y",
        period="monthly",
        date_col_idx=0,
        value_col_idx=1,  # LPR1Y
        date_normalizer=_normalize_iso_date,
    )


def _fetch_m2() -> FetchResult:
    """M2 货币供应量同比（月度），数据源：中国人民银行。

    AKShare `macro_china_money_supply` 列结构（10列）：
        月份 | M2-数量 | M2-同比增长 | M2-环比增长 | M1-数量 | M1-同比增长 | ... | M0-...
    """
    df = _get_money_supply_df()
    return _build_history(
        df,
        slug="m2",
        period="monthly",
        date_col_idx=0,
        value_col_idx=2,  # M2-同比增长
        date_normalizer=_normalize_year_month,
    )


def _fetch_m1() -> FetchResult:
    """M1 货币供应量同比（月度），数据源：中国人民银行。

    与 M2 同源，取 `macro_china_money_supply` 的 M1-同比增长列。
    """
    df = _get_money_supply_df()
    return _build_history(
        df,
        slug="m1",
        period="monthly",
        date_col_idx=0,
        value_col_idx=5,  # M1-同比增长
        date_normalizer=_normalize_year_month,
    )


def _fetch_m1_m2_scissor() -> FetchResult:
    """M1-M2 剪刀差（月度），数据源：中国人民银行。

    剪刀差 = M1 同比增速 - M2 同比增速。直接从同一张表中提取两列计算，
    保证与独立拉取的 M1、M2 数值一致。
    """
    df = _get_money_supply_df()
    date_col = df.columns[0]
    m2_col = df.columns[2]   # M2-同比增长
    m1_col = df.columns[5]   # M1-同比增长

    history: list[IndicatorData] = []
    for _, row in df.iterrows():
        m2_val = row[m2_col]
        m1_val = row[m1_col]
        if pd.isna(m2_val) or pd.isna(m1_val):
            continue
        try:
            diff = float(m1_val) - float(m2_val)
        except (TypeError, ValueError):
            continue
        date_str = _normalize_year_month(row[date_col])
        history.append(
            IndicatorData(slug="m1_m2_scissor", date=date_str, value=round(diff, 2), period="monthly")
        )

    history.sort(key=lambda x: x.date)
    if not history:
        raise RuntimeError("m1_m2_scissor: 未拉取到任何有效数据点")
    return FetchResult(latest=history[-1], history=history)


def _fetch_new_loan() -> FetchResult:
    """新增人民币贷款（月度），数据源：中国人民银行。

    AKShare `macro_china_new_financial_credit` 列结构：
        月份 | 当月 | 当月-同比增长 | 当月-环比增长 | 累计 | 累计-同比增长
    """
    df = ak.macro_china_new_financial_credit()
    return _build_history(
        df,
        slug="new_loan",
        period="monthly",
        date_col_idx=0,
        value_col_idx=1,  # 当月
        date_normalizer=_normalize_year_month,
    )


# ════════════════════ 注册表 ════════════════════

FETCHERS: dict[str, Any] = {
    "gdp": _fetch_gdp,
    "pmi": _fetch_pmi,
    "industrial_production": _fetch_industrial_production,
    "retail_sales": _fetch_retail_sales,
    "cpi": _fetch_cpi,
    "ppi": _fetch_ppi,
    "usd_cny": _fetch_usd_cny,
    "lpr_1y": _fetch_lpr_1y,
    "m2": _fetch_m2,
    "m1": _fetch_m1,
    "m1_m2_scissor": _fetch_m1_m2_scissor,
    "new_loan": _fetch_new_loan,
}


def fetch_indicator(fetcher_key: str) -> FetchResult:
    """按配置键拉取指标数据。"""
    fetcher = FETCHERS.get(fetcher_key)
    if fetcher is None:
        raise ValueError(f"未找到数据拉取函数: {fetcher_key}")
    return fetcher()


# ════════════════════ 辅助序列（卡片补充展示 / 图表叠加线）════════════════════
#
# 有些指标除了主值外，还想展示一个附加序列：
#   - GDP：主值=累计同比，附加=绝对值（文字补充）
#   - CPI：主值=同比，附加=环比（图表叠加线）
#   - PPI：主值=同比，附加=环比（源缺失，暂不展示）
# 每个 builder 返回 (label, unit, display, FetchResult|None)，由上层组装成 secondary。

SECONDARY_FETCHERS: dict[str, Any] = {
    "gdp": {"label": "绝对值", "unit": "亿元", "display": "text", "fetch": _fetch_gdp_absolute},
    "cpi": {"label": "环比", "unit": "%", "display": "chart_line", "fetch": _fetch_cpi_mom},
    "ppi": {"label": "环比", "unit": "%", "display": "chart_line", "fetch": _fetch_ppi_mom},
}


def fetch_secondary(slug: str) -> dict[str, Any] | None:
    """拉取某指标的辅助序列；无配置或源缺失时返回 None。"""
    spec = SECONDARY_FETCHERS.get(slug)
    if spec is None:
        return None
    try:
        result = spec["fetch"]()
    except Exception:
        return None
    if result is None:
        return None
    return {
        "label": spec["label"],
        "unit": spec["unit"],
        "display": spec["display"],
        "latest_value": result.latest.value,
        "latest_date": result.latest.date,
        "history": [{"date": d.date, "value": d.value} for d in result.history],
    }