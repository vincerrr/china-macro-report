"""配置管理 — 指标定义、路径、API 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 从 .env 加载（如果存在）
load_dotenv(PROJECT_ROOT / ".env")

# 路径配置
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DB_PATH = DATA_DIR / "macro.db"
LATEST_JSON_PATH = DATA_DIR / "latest.json"

# GLM API 配置
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-5.2")
GLM_API_BASE = os.getenv("GLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4/")


@dataclass(frozen=True)
class IndicatorConfig:
    """单个指标的配置。"""

    slug: str            # 内部唯一标识，如 "cpi"
    name: str            # 显示名称，如 "居民消费价格指数 (CPI)"
    short_name: str      # 卡片标题用的短名，如 "CPI"
    category: str        # 分类：增长 / 物价 / 货币 / 就业
    unit: str            # 单位
    frequency: str       # monthly / daily / quarterly
    source_name: str     # 数据来源
    source_url: str      # 官方数据页面（供校验）
    fetcher_key: str     # fetcher.py 中对应的函数键
    description: str     # 指标说明（用于 LLM prompt 上下文）
    # ── 显示语义字段（影响卡片副标签、环比差值单位、图表参考线）──
    value_type: str = "yoy"           # yoy | level_index | level_rate | level_fx | absolute
    value_type_label: str = "同比"     # 卡片大数下方的小字标签
    delta_unit: str = "个百分点"       # 环比变化的单位（不是数据本身的 unit）
    chart_baseline: float | None = None  # 图表参考线（如 PMI 的荣枯线 50，同比指标的 0）
    release_day: int | None = None       # 预计发布日（日频指标可不填）：月频/季频指标通常在下月的第几天发布


# 页面展示顺序（按分类）
INDICATORS: list[IndicatorConfig] = [
    # ═══════ 增长篇 ═══════
    IndicatorConfig(
        slug="gdp",
        name="国内生产总值 (GDP) 同比",
        short_name="GDP",
        category="增长",
        unit="%",
        frequency="quarterly",
        source_name="国家统计局",
        source_url="https://www.stats.gov.cn/sj/zxfb/",
        fetcher_key="gdp",
        description="GDP 同比增速衡量经济总体增长水平。中国季度 GDP 数据由国家统计局发布，一般在季后 15-20 天公布。",
        value_type="yoy",
        value_type_label="季度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=15,
    ),
    IndicatorConfig(
        slug="pmi",
        name="制造业采购经理指数 (PMI)",
        short_name="PMI",
        category="增长",
        unit="指数",
        frequency="monthly",
        source_name="国家统计局",
        source_url="https://www.stats.gov.cn/sj/zxfb/",
        fetcher_key="pmi",
        description="PMI 反映制造业景气程度。50 为荣枯线，>50 表示扩张，<50 表示收缩，是经济走势的先行指标。",
        value_type="level_index",
        value_type_label="指数水平（荣枯线 50）",
        delta_unit="点",
        chart_baseline=50,
        release_day=1,
    ),
    IndicatorConfig(
        slug="industrial_production",
        name="规模以上工业增加值 同比",
        short_name="工业增加值",
        category="增长",
        unit="%",
        frequency="monthly",
        source_name="国家统计局",
        source_url="https://www.stats.gov.cn/sj/zxfb/",
        fetcher_key="industrial_production",
        description="规模以上工业增加值是衡量工业产出增长的核心指标。统计口径为年主营业务收入 2000 万元及以上的工业企业。",
        value_type="yoy",
        value_type_label="月度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=15,
    ),
    IndicatorConfig(
        slug="retail_sales",
        name="社会消费品零售总额 同比",
        short_name="社零总额",
        category="增长",
        unit="%",
        frequency="monthly",
        source_name="国家统计局",
        source_url="https://www.stats.gov.cn/sj/zxfb/",
        fetcher_key="retail_sales",
        description="社会消费品零售总额反映居民消费支出水平，是衡量内需和消费市场活跃度的关键指标。",
        value_type="yoy",
        value_type_label="月度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=15,
    ),

    # ═══════ 物价篇 ═══════
    IndicatorConfig(
        slug="cpi",
        name="居民消费价格指数 (CPI) 同比",
        short_name="CPI",
        category="物价",
        unit="%",
        frequency="monthly",
        source_name="国家统计局",
        source_url="https://www.stats.gov.cn/sj/zxfb/",
        fetcher_key="cpi",
        description="CPI 同比反映居民消费品和服务价格水平的同比变动。一般认为 2%-3% 为温和通胀，<0 为通缩，>5% 为高通胀。",
        value_type="yoy",
        value_type_label="月度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=10,
    ),
    IndicatorConfig(
        slug="ppi",
        name="工业生产者出厂价格指数 (PPI) 同比",
        short_name="PPI",
        category="物价",
        unit="%",
        frequency="monthly",
        source_name="国家统计局",
        source_url="https://www.stats.gov.cn/sj/zxfb/",
        fetcher_key="ppi",
        description="PPI 反映工业品出厂价格变动，对 CPI 有传导作用。PPI 同比<0 表示工业通缩，可能预示企业利润承压。",
        value_type="yoy",
        value_type_label="月度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=10,
    ),

    # ═══════ 货币篇 ═══════
    IndicatorConfig(
        slug="usd_cny",
        name="美元/人民币汇率（中间价）",
        short_name="USD/CNY",
        category="货币",
        unit="CNY/100USD",
        frequency="daily",
        source_name="国家外汇管理局",
        source_url="https://www.safe.gov.cn/safe/rmbhlzjj/index.html",
        fetcher_key="usd_cny",
        description="人民币对美元汇率中间价（每 100 美元兑人民币），由外汇管理局每日公布。数值上升表示人民币贬值，下降表示升值。",
        value_type="level_fx",
        value_type_label="每日中间价",
        delta_unit="CNY/100USD",
        chart_baseline=None,
    ),
    IndicatorConfig(
        slug="lpr_1y",
        name="贷款市场报价利率 (LPR) 1年期",
        short_name="LPR 1Y",
        category="货币",
        unit="%",
        frequency="monthly",
        source_name="中国人民银行",
        source_url="https://www.chinamoney.com.cn/chinese/bklpr/",
        fetcher_key="lpr_1y",
        description="LPR 是商业银行对其最优质客户执行的贷款利率，是市场基准利率。1年期 LPR 影响短期借贷成本，是货币政策传导的关键变量。",
        value_type="level_rate",
        value_type_label="利率水平",
        delta_unit="个基点",  # bp，1 个基点 = 0.01%
        chart_baseline=None,
        release_day=20,
    ),
    IndicatorConfig(
        slug="m2",
        name="货币供应量 (M2) 同比",
        short_name="M2",
        category="货币",
        unit="%",
        frequency="monthly",
        source_name="中国人民银行",
        source_url="http://www.pbc.gov.cn/diaochatongjisi/116219/index.html",
        fetcher_key="m2",
        description="M2 同比增速反映货币总量扩张速度，是衡量流动性和货币政策松紧的核心指标。M2 增速高意味着市场流动性充裕。",
        value_type="yoy",
        value_type_label="月度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=12,
    ),
    IndicatorConfig(
        slug="m1",
        name="货币供应量 (M1) 同比",
        short_name="M1",
        category="货币",
        unit="%",
        frequency="monthly",
        source_name="中国人民银行",
        source_url="http://www.pbc.gov.cn/diaochatongjisi/116219/index.html",
        fetcher_key="m1",
        description="M1 同比增速反映经济体中活期存款和现金的增长，是衡量经济活跃度和企业交易意愿的重要指标。M1 增速高于 M2 通常意味着资金活化、经济景气度提升。",
        value_type="yoy",
        value_type_label="月度同比",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=12,
    ),
    IndicatorConfig(
        slug="m1_m2_scissor",
        name="M1-M2 剪刀差",
        short_name="M1-M2 剪刀差",
        category="货币",
        unit="个百分点",
        frequency="monthly",
        source_name="中国人民银行",
        source_url="http://www.pbc.gov.cn/diaochatongjisi/116219/index.html",
        fetcher_key="m1_m2_scissor",
        description="M1-M2 剪刀差 = M1 同比增速 - M2 同比增速。差值扩大（M1 相对 M2 走强）反映资金活化、企业投资意愿增强；差值收窄或转负则反映资金沉淀、经济活跃度下降。",
        value_type="yoy",
        value_type_label="剪刀差（M1同比 - M2同比）",
        delta_unit="个百分点",
        chart_baseline=0,
        release_day=12,
    ),
    IndicatorConfig(
        slug="new_loan",
        name="新增人民币贷款（当月）",
        short_name="新增贷款",
        category="货币",
        unit="亿元",
        frequency="monthly",
        source_name="中国人民银行",
        source_url="http://www.pbc.gov.cn/diaochatongjisi/116219/index.html",
        fetcher_key="new_loan",
        description="新增人民币贷款反映信贷投放规模，是社融总量的重要组成部分。贷款增长快表示信贷需求旺盛，经济活跃度高。",
        value_type="absolute",
        value_type_label="当月绝对值",
        delta_unit="亿元",
        chart_baseline=0,
        release_day=12,
    ),

    # ═══════ 就业篇 ═══════
    # 注：失业率、新增就业的 AKShare 接口当前不可用（NBS 接口 404），
    # 待上游修复后补充。暂用占位说明。
]

# 暂不可用指标说明（用于 LLM 上下文和页面提示）
UNAVAILABLE_NOTES: dict[str, str] = {
    "core_cpi": "核心 CPI（扣除食品和能源）—— AKShare 无此函数，需从其他数据源获取",
    "unemployment": "城镇调查失业率 —— AKShare 的 macro_china_urban_unemployment 接口当前 NBS 服务器 404",
    "new_employment": "城镇新增就业 —— AKShare 无此函数，数据以人社部新闻稿形式发布",
    "aggregate_financing": "社会融资规模总量 —— AKShare 的 macro_china_shrzgm 接口 MOFCOM 服务器 TLS 握手失败，暂用新增贷款替代",
}


def get_indicator(slug: str) -> IndicatorConfig | None:
    """按 slug 查找指标配置。"""
    for ind in INDICATORS:
        if ind.slug == slug:
            return ind
    return None


def ensure_dirs() -> None:
    """确保必要的目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)