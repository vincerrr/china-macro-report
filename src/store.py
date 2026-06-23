"""SQLite 存储层 — 数据库初始化、数据点 CRUD、分析记录管理。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import DB_PATH, LATEST_JSON_PATH, IndicatorConfig, INDICATORS

# 模块级连接（简单场景下够用）
_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    """获取数据库连接（懒初始化）。"""
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH))
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
    """初始化数据库表结构。"""
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS indicators (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            category    TEXT NOT NULL,
            unit        TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS data_points (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_id    INTEGER NOT NULL REFERENCES indicators(id),
            value           REAL NOT NULL,
            date            TEXT NOT NULL,
            period          TEXT NOT NULL,
            created_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(indicator_id, date)
        );

        CREATE TABLE IF NOT EXISTS analyses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_id    INTEGER NOT NULL REFERENCES indicators(id),
            data_point_id   INTEGER NOT NULL REFERENCES data_points(id),
            analysis_text   TEXT NOT NULL,
            model           TEXT NOT NULL,
            generated_at    TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()


def ensure_indicator(ind: IndicatorConfig) -> int:
    """确保指标记录存在，返回其 id。"""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO indicators (slug, name, category, unit, source_name, source_url)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            category=excluded.category,
            unit=excluded.unit,
            source_name=excluded.source_name,
            source_url=excluded.source_url
        """,
        (ind.slug, ind.name, ind.category, ind.unit, ind.source_name, ind.source_url),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM indicators WHERE slug = ?", (ind.slug,)).fetchone()
    assert row is not None
    return row["id"]


def get_latest_data(indicator_id: int) -> dict[str, Any] | None:
    """获取某个指标的最新数据点。"""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT id, indicator_id, value, date, period, created_at
        FROM data_points
        WHERE indicator_id = ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (indicator_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def save_data_point(indicator_id: int, date: str, value: float, period: str) -> int:
    """插入或更新数据点，返回数据点 id。"""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO data_points (indicator_id, value, date, period)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(indicator_id, date) DO UPDATE SET
            value=excluded.value,
            period=excluded.period
        """,
        (indicator_id, value, date, period),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM data_points WHERE indicator_id = ? AND date = ?",
        (indicator_id, date),
    ).fetchone()
    assert row is not None
    return row["id"]


def save_analysis(indicator_id: int, data_point_id: int, analysis_text: str, model: str) -> int:
    """保存一条 LLM 分析记录。"""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO analyses (indicator_id, data_point_id, analysis_text, model)
        VALUES (?, ?, ?, ?)
        """,
        (indicator_id, data_point_id, analysis_text, model),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_analysis_for_data_point(data_point_id: int) -> dict[str, Any] | None:
    """获取某个数据点对应的分析记录。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM analyses WHERE data_point_id = ? ORDER BY generated_at DESC LIMIT 1",
        (data_point_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_historical_data(indicator_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """获取某个指标最近 N 条历史数据（按 date 升序）。"""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, indicator_id, value, date, period, created_at
        FROM data_points
        WHERE indicator_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (indicator_id, limit),
    ).fetchall()
    # 翻转回升序
    return [dict(r) for r in reversed(rows)]


def get_full_record(indicator_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """获取指标的最新数据点及其分析（按 date 降序，limit 条）。"""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT dp.id, dp.value, dp.date, dp.period,
               a.analysis_text, a.model, a.generated_at
        FROM data_points dp
        LEFT JOIN analyses a ON a.data_point_id = dp.id
        WHERE dp.indicator_id = ?
        ORDER BY dp.date DESC
        LIMIT ?
        """,
        (indicator_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def export_snapshot() -> dict[str, Any]:
    """导出当前数据快照为字典，供 reporter 使用。"""
    snapshot: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "indicators": [],
    }
    for ind in INDICATORS:
        ind_id = ensure_indicator(ind)
        latest = get_latest_data(ind_id)
        history = get_historical_data(ind_id, limit=30)

        # 上期值
        prev_value = history[-2]["value"] if len(history) >= 2 else None

        # 分析
        analysis = None
        if latest:
            analysis = get_analysis_for_data_point(latest["id"])

        snapshot["indicators"].append(
            {
                "slug": ind.slug,
                "name": ind.name,
                "short_name": ind.short_name,
                "category": ind.category,
                "unit": ind.unit,
                "frequency": ind.frequency,
                "source_name": ind.source_name,
                "source_url": ind.source_url,
                "value_type": ind.value_type,
                "value_type_label": ind.value_type_label,
                "delta_unit": ind.delta_unit,
                "chart_baseline": ind.chart_baseline,
                "latest_value": latest["value"] if latest else None,
                "latest_date": latest["date"] if latest else None,
                "prev_value": prev_value,
                "analysis_text": analysis["analysis_text"] if analysis else None,
                "history": [
                    {"date": h["date"], "value": h["value"]} for h in history
                ],
            }
        )
    return snapshot


def export_snapshot_json() -> None:
    """导出快照为 JSON 文件。"""
    snapshot = export_snapshot()
    LATEST_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LATEST_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)