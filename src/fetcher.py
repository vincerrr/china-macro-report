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

def _fetch_gdp() -> FetchResult:
    """GDP 同比增速（季度），数据源：国家统计局。

    AKShare `macro_china_gdp` 返回累计同比数据。列结构：
        季度 | 国内生产总值-绝对值 | 国内生产总值-同比增长 | ...
    """
    df = ak.macro_china_gdp()
    return _build_history(
        df,
        slug="gdp",
        period="quarterly",
        date_col_idx=0,
        value_col_idx=2,  # 国内生产总值-同比增长
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
    """规模以上工业增加值同比（月度），数据源：国家统计局（金十数据中转）。

    AKShare `macro_china_industrial_production_yoy` 列结构：
        商品 | 日期 | 今值 | 预测值 | 前值
    """
    df = ak.macro_china_industrial_production_yoy()
    return _build_history(
        df,
        slug="industrial_production",
        period="monthly",
        date_col_idx=1,
        value_col_idx=2,  # 今值
        date_normalizer=lambda d: _normalize_iso_date(d)[:7],  # 转月度 YYYY-MM
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

def _fetch_cpi() -> FetchResult:
    """CPI 同比（月度），数据源：国家统计局。"""
    df = ak.macro_china_cpi()
    return _build_history(
        df,
        slug="cpi",
        period="monthly",
        date_col_idx=0,
        value_col_idx=2,  # 全国-同比增长
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


# ════════════════════ 货币篇 ════════════════════

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
        月份 | M2-数量 | M2-同比增长 | M2-环比增长 | M1-数量 | ... | M0-...
    """
    df = ak.macro_china_money_supply()
    return _build_history(
        df,
        slug="m2",
        period="monthly",
        date_col_idx=0,
        value_col_idx=2,  # M2-同比增长
        date_normalizer=_normalize_year_month,
    )


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
    "new_loan": _fetch_new_loan,
}


def fetch_indicator(fetcher_key: str) -> FetchResult:
    """按配置键拉取指标数据。"""
    fetcher = FETCHERS.get(fetcher_key)
    if fetcher is None:
        raise ValueError(f"未找到数据拉取函数: {fetcher_key}")
    return fetcher()