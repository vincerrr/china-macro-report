"""HTML 报告生成器 — 用 Jinja2 模板将快照渲染为静态 HTML 页面。

样式：Tailwind CSS v3（CDN）
图表：ECharts v5（CDN）
数据：直接内嵌到 HTML 的 <script> 标签，无需额外请求
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

from src.config import OUTPUT_DIR


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>中国宏观经济数据报告</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
  .indicator-card { transition: box-shadow 0.2s ease-in-out; }
  .indicator-card:hover { box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08); }
  .chart-box { width: 100%; height: 280px; }
</style>
</head>
<body class="bg-slate-50 text-slate-800">

<div class="max-w-5xl mx-auto px-4 sm:px-6 py-10">

  <!-- Header -->
  <header class="mb-10 border-b border-slate-200 pb-6">
    <h1 class="text-3xl font-bold text-slate-900 mb-2">📊 中国宏观经济数据报告</h1>
    <p class="text-sm text-slate-500">
      更新于 <span class="font-mono">{{ generated_at_local }}</span>
      · 共 {{ indicators|length }} 个指标
    </p>
  </header>

  {% if upcoming_releases %}
  <!-- Upcoming Releases Calendar -->
  <section class="mb-10">
    <h2 class="text-xl font-semibold text-slate-700 mb-5 flex items-center">
      <span class="inline-block w-1 h-5 bg-amber-500 mr-3"></span>
      📅 未来 30 天发布预告
    </h2>

    <div class="bg-white rounded-lg border border-slate-200 p-6">
      <div class="space-y-4">
        {% for event in upcoming_releases %}
        <div class="flex items-start gap-4 pb-4 border-b border-slate-100 last:border-0 last:pb-0">
          <div class="flex-shrink-0 w-20 text-center">
            <div class="text-xs text-slate-500">{{ event.month }}</div>
            <div class="text-2xl font-bold text-slate-900">{{ event.day }}</div>
            <div class="text-xs text-slate-400">{{ event.weekday }}</div>
          </div>
          <div class="flex-1">
            {% for ind in event.indicators %}
            <div class="inline-flex items-center bg-slate-50 rounded-full px-3 py-1 mr-2 mb-2 text-sm">
              <span class="w-2 h-2 rounded-full mr-2" style="background-color: {{ ind.category_color }}"></span>
              <span class="text-slate-700">{{ ind.short_name }}</span>
              <span class="text-xs text-slate-400 ml-2">{{ ind.frequency_zh }}</span>
            </div>
            {% endfor %}
          </div>
        </div>
        {% endfor %}
      </div>
      <p class="text-xs text-slate-400 mt-4">
        * 日期根据历史发布规律估算，实际发布时间可能因节假日或官方调整而变化。
      </p>
    </div>
  </section>
  {% endif %}

  {% for category, items in grouped_indicators %}
  <!-- Category: {{ category }} -->
  <section class="mb-10">
    <h2 class="text-xl font-semibold text-slate-700 mb-5 flex items-center">
      <span class="inline-block w-1 h-5 bg-blue-500 mr-3"></span>
      {{ category }}篇
    </h2>

    {% for ind in items %}
    <article class="indicator-card bg-white rounded-lg border border-slate-200 p-6 mb-5">

      <!-- Top: name + value + change -->
      <div class="flex items-start justify-between mb-4 flex-wrap gap-3">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">{{ ind.name }}</h3>
          <p class="text-xs text-slate-500 mt-1">
            数据期：{{ ind.latest_date }} · 频率：{{ ind.frequency_zh }}
          </p>
        </div>
        <div class="text-right">
          {% if ind.latest_value is not none %}
          <div class="text-3xl font-bold text-slate-900 font-mono">
            {{ ind.latest_value_display }}<span class="text-base text-slate-500 ml-1">{{ ind.unit }}</span>
          </div>
          <div class="text-xs text-slate-400 mt-0.5">{{ ind.value_type_label }}</div>
          {% if ind.delta_display %}
          <div class="text-sm mt-1 {{ ind.delta_class }}">
            {{ ind.delta_arrow }} {{ ind.delta_display }}
            <span class="text-xs text-slate-400 ml-1">较上期</span>
          </div>
          {% endif %}
          {% else %}
          <div class="text-slate-400">暂无数据</div>
          {% endif %}
        </div>
      </div>

      <!-- Chart -->
      {% if ind.history %}
      <div id="chart-{{ ind.slug }}" class="chart-box mb-4"></div>
      {% endif %}

      <!-- Analysis -->
      {% if ind.analysis_text %}
      <div class="bg-slate-50 rounded p-4 mt-3">
        <div class="text-xs font-semibold text-slate-500 mb-2 flex items-center">
          <span class="mr-1">💬</span> AI 解读
        </div>
        <p class="text-sm text-slate-700 leading-relaxed">{{ ind.analysis_text }}</p>
      </div>
      {% endif %}

      <!-- Footer: source link -->
      <div class="mt-4 pt-3 border-t border-slate-100 text-xs text-slate-500 flex items-center justify-between">
        <span>数据来源：{{ ind.source_name }}</span>
        <a href="{{ ind.source_url }}" target="_blank" rel="noopener"
           class="text-blue-600 hover:text-blue-700 hover:underline">
          查看官方页面 →
        </a>
      </div>

    </article>
    {% endfor %}
  </section>
  {% endfor %}

  <!-- Footer -->
  <footer class="mt-12 pt-6 border-t border-slate-200 text-xs text-slate-500 text-center space-y-1">
    <p>数据由 AKShare 从官方渠道汇集，AI 解读由火山方舟（豆包）模型生成，仅供参考</p>
    <p>本报告非投资建议</p>
  </footer>

</div>

<script>
  const snapshotData = {{ snapshot_json | safe }};

  function renderChart(ind, color) {
    const dom = document.getElementById('chart-' + ind.slug);
    if (!dom || !ind.history || ind.history.length === 0) return;
    const chart = echarts.init(dom);
    const unit = ind.unit;

    // 参考线（如 PMI 的荣枯线 50、同比指标的 0）
    const markLines = [];
    if (ind.chart_baseline !== null && ind.chart_baseline !== undefined) {
      markLines.push({
        yAxis: ind.chart_baseline,
        label: {
          formatter: (ind.value_type === 'level_index' ? '荣枯线 ' : '基准 ') + ind.chart_baseline,
          color: '#94a3b8',
          fontSize: 10,
          position: 'start'
        },
        lineStyle: { color: '#94a3b8', type: 'dashed', width: 1 }
      });
    }

    chart.setOption({
      grid: { left: 55, right: 20, top: 20, bottom: 30 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line' },
        formatter: (params) => {
          const p = params[0];
          return `${p.axisValueLabel}<br/>` +
                 `<span style="color:${color}">●</span> ${ind.short_name}: <b>${p.value}</b> ${unit}`;
        }
      },
      xAxis: {
        type: 'category',
        data: ind.history.map(p => p.date),
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { color: '#64748b', fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: unit,
        nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#e2e8f0' } },
        axisLabel: { color: '#64748b', fontSize: 11 }
      },
      series: [{
        type: 'line',
        data: ind.history.map(p => p.value),
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: color, width: 2 },
        itemStyle: { color: color },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: color + '40' },
              { offset: 1, color: color + '00' }
            ]
          }
        },
        markLine: markLines.length > 0 ? {
          symbol: 'none',
          data: markLines
        } : undefined
      }]
    });
    window.addEventListener('resize', () => chart.resize());
  }

  // Category color mapping
  const COLORS = {
    '物价': '#3b82f6',  // blue
    '货币': '#8b5cf6',  // violet
    '增长': '#10b981',  // emerald
    '就业': '#f59e0b',  // amber
  };

  snapshotData.indicators.forEach(ind => {
    const color = COLORS[ind.category] || '#64748b';
    renderChart(ind, color);
  });
</script>

</body>
</html>
"""


# 频率中文映射
FREQUENCY_ZH = {
    "daily": "每日",
    "monthly": "月度",
    "quarterly": "季度",
    "yearly": "年度",
}


def _format_value(value: float, unit: str) -> str:
    """根据数值大小和单位格式化显示。"""
    if abs(value) >= 100:
        return f"{value:,.2f}"
    elif abs(value) >= 10:
        return f"{value:.2f}"
    else:
        return f"{value:.2f}"


def _format_delta(delta: float, value_type: str, delta_unit: str) -> str:
    """格式化环比差值显示。

    LPR 单位是 %，但差值要用"个基点"（1bp = 0.01%）显示，所以要乘 100。
    其他同比指标的差值要用"个百分点"。
    """
    sign = "+" if delta > 0 else ""

    # LPR 等利率水平：差值要乘 100 转成基点
    if value_type == "level_rate":
        bp = delta * 100
        return f"{sign}{bp:.0f} {delta_unit}"
    # 同比/绝对值/汇率/PMI：直接显示差值
    return f"{sign}{delta:.2f} {delta_unit}"


def _enrich_indicator(ind: dict[str, Any]) -> dict[str, Any]:
    """为模板渲染补齐显示字段。"""
    enriched = dict(ind)

    enriched["frequency_zh"] = FREQUENCY_ZH.get(ind["frequency"], ind["frequency"])

    if ind["latest_value"] is not None:
        enriched["latest_value_display"] = _format_value(ind["latest_value"], ind["unit"])
    else:
        enriched["latest_value_display"] = "—"

    # 变化箭头与颜色
    enriched["delta_display"] = ""
    enriched["delta_class"] = "text-slate-500"
    enriched["delta_arrow"] = ""

    if ind["latest_value"] is not None and ind["prev_value"] is not None:
        delta = ind["latest_value"] - ind["prev_value"]
        delta_unit = ind.get("delta_unit", ind["unit"])
        value_type = ind.get("value_type", "yoy")

        # 判断"持平"的阈值：rate 类 < 1bp 算持平，其他 < 0.005 算持平
        threshold = 1e-5 if value_type == "level_rate" else 0.005

        if delta > threshold:
            enriched["delta_arrow"] = "↑"
            enriched["delta_class"] = "text-red-600"  # 中国习惯：红涨绿跌
            enriched["delta_display"] = _format_delta(delta, value_type, delta_unit)
        elif delta < -threshold:
            enriched["delta_arrow"] = "↓"
            enriched["delta_class"] = "text-emerald-600"
            enriched["delta_display"] = _format_delta(delta, value_type, delta_unit)
        else:
            enriched["delta_arrow"] = "→"
            enriched["delta_class"] = "text-slate-500"
            enriched["delta_display"] = "持平"

    return enriched


def _group_by_category(indicators: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """按 category 分组，保持出现顺序。"""
    order: list[str] = []
    bucket: dict[str, list[dict[str, Any]]] = {}
    for ind in indicators:
        cat = ind["category"]
        if cat not in bucket:
            bucket[cat] = []
            order.append(cat)
        bucket[cat].append(ind)
    return [(cat, bucket[cat]) for cat in order]


def _utc_to_local_str(utc_str: str) -> str:
    """简单格式化 UTC 时间为可读字符串（保留 UTC 标记，不做时区换算）。"""
    # 输入形如 "2026-06-22T09:00:00Z"
    if "T" in utc_str:
        date_part, time_part = utc_str.split("T")
        time_part = time_part.rstrip("Z")
        return f"{date_part} {time_part} UTC"
    return utc_str


# 分类颜色（与 JS 中的 COLORS 保持一致）
CATEGORY_COLORS = {
    "物价": "#3b82f6",
    "货币": "#8b5cf6",
    "增长": "#10b981",
    "就业": "#f59e0b",
}

_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _enrich_upcoming_releases(releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为发布日历补充显示字段。"""
    enriched = []
    for event in releases:
        release_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        indicators = []
        for ind in event["indicators"]:
            indicators.append(
                {
                    **ind,
                    "frequency_zh": FREQUENCY_ZH.get(ind["frequency"], ind["frequency"]),
                    "category_color": CATEGORY_COLORS.get(ind["category"], "#64748b"),
                }
            )
        enriched.append(
            {
                "date": event["date"],
                "month": f"{release_date.month}月",
                "day": f"{release_date.day:02d}",
                "weekday": _WEEKDAY_ZH[release_date.weekday()],
                "indicators": indicators,
            }
        )
    return enriched


def generate_html(snapshot: dict[str, Any], output_path: Path | None = None) -> Path:
    """生成 HTML 报告。"""
    output_path = output_path or (OUTPUT_DIR / "index.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    enriched_indicators = [_enrich_indicator(ind) for ind in snapshot["indicators"]]
    grouped = _group_by_category(enriched_indicators)
    upcoming_releases = _enrich_upcoming_releases(snapshot.get("upcoming_releases", []))

    template = Template(HTML_TEMPLATE)
    html = template.render(
        generated_at_local=_utc_to_local_str(snapshot["generated_at"]),
        indicators=enriched_indicators,
        grouped_indicators=grouped,
        upcoming_releases=upcoming_releases,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path