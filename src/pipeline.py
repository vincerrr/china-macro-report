"""主流程编排 — fetch → 变化检测 → analyze → store → report。

每日运行的入口点。逻辑：
1. 对每个配置的指标，从 AKShare 拉取最新数据
2. 与 DB 中的最新记录比对，决定是否需要重新调用 LLM
3. 有新数据或数据变化 → 调 LLM 生成解读 → 落库
4. 导出 JSON 快照
5. 生成 HTML 报告
"""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from src.analyzer import analyze, get_model_name
from src.config import INDICATORS, ensure_dirs, LATEST_JSON_PATH
from src.fetcher import fetch_indicator
from src.reporter import generate_html
from src.store import (
    ensure_indicator,
    export_snapshot,
    export_snapshot_json,
    get_analysis_for_data_point,
    get_latest_data,
    init_db,
    save_analysis,
    save_data_point,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pipeline")


def _is_data_changed(old: dict | None, new_date: str, new_value: float) -> tuple[bool, str]:
    """判断数据是否发生变化。

    返回 (是否变化, 变化原因)。
    """
    if old is None:
        return True, "首次入库"
    if old["date"] != new_date:
        return True, f"新增数据点（{old['date']} → {new_date}）"
    if abs(old["value"] - new_value) > 1e-9:
        return True, f"同期数据修订（{old['value']} → {new_value}）"
    return False, "无变化"


def process_indicator(ind) -> dict:
    """处理单个指标。返回处理结果摘要。"""
    summary = {
        "slug": ind.slug,
        "name": ind.short_name,
        "fetched_latest": None,
        "changed": False,
        "reason": "",
        "analyzed": False,
        "analysis_chars": 0,
        "error": None,
    }

    try:
        log.info(f"[{ind.short_name}] 开始拉取数据 ...")
        result = fetch_indicator(ind.fetcher_key)
        summary["fetched_latest"] = f"{result.latest.date}={result.latest.value}"

        # 注册/更新指标元信息
        ind_id = ensure_indicator(ind)

        # 写入全部历史（已有的会被 UNIQUE 约束跳过）
        for dp in result.history:
            save_data_point(ind_id, dp.date, dp.value, dp.period)

        # 检测最新值是否变化
        latest_in_db_before = None  # 我们已经写入了，所以另存一份判断逻辑
        # 重新查 latest（写入后的）
        latest_now = get_latest_data(ind_id)
        assert latest_now is not None

        # 是否已对当前 latest 数据点做过分析？
        existing_analysis = get_analysis_for_data_point(latest_now["id"])

        if existing_analysis:
            summary["changed"] = False
            summary["reason"] = "已有分析，跳过 LLM 调用"
            log.info(f"[{ind.short_name}] 跳过 LLM：{summary['reason']}")
        else:
            # 取上期数据点用于 LLM 对比
            from src.store import get_historical_data
            history = get_historical_data(ind_id, limit=2)
            prev_value = history[0]["value"] if len(history) >= 2 else None
            prev_date = history[0]["date"] if len(history) >= 2 else None

            log.info(f"[{ind.short_name}] 调用 LLM 生成解读 ...")
            text = analyze(
                ind=ind,
                latest_value=latest_now["value"],
                latest_date=latest_now["date"],
                prev_value=prev_value,
                prev_date=prev_date,
            )
            save_analysis(ind_id, latest_now["id"], text, get_model_name())
            summary["changed"] = True
            summary["analyzed"] = True
            summary["analysis_chars"] = len(text)
            summary["reason"] = "新数据，已生成分析"
            log.info(f"[{ind.short_name}] LLM 解读完成（{len(text)} 字）")

    except Exception as e:
        log.error(f"[{ind.short_name}] 处理失败: {e}")
        log.debug(traceback.format_exc())
        summary["error"] = str(e)

    return summary


def run() -> int:
    """执行完整流水线，返回 exit code（0 = 成功）。"""
    log.info("=" * 60)
    log.info("中国宏观经济数据报告 — 每日流水线")
    log.info("=" * 60)

    ensure_dirs()
    init_db()

    summaries = []
    for ind in INDICATORS:
        summary = process_indicator(ind)
        summaries.append(summary)

    # 导出快照 + 生成 HTML
    log.info("导出 JSON 快照 ...")
    export_snapshot_json()
    log.info(f"  已写入 {LATEST_JSON_PATH}")

    log.info("生成 HTML 报告 ...")
    snapshot = export_snapshot()
    html_path = generate_html(snapshot)
    log.info(f"  已写入 {html_path}")

    # 汇总
    log.info("=" * 60)
    log.info("流水线执行汇总：")
    has_error = False
    for s in summaries:
        if s["error"]:
            log.info(f"  ❌ {s['name']}: {s['error']}")
            has_error = True
        elif s["analyzed"]:
            log.info(f"  ✅ {s['name']}: 拉取 {s['fetched_latest']}，已生成分析 {s['analysis_chars']} 字")
        else:
            log.info(f"  ⏭️  {s['name']}: 拉取 {s['fetched_latest']}，{s['reason']}")

    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(run())
