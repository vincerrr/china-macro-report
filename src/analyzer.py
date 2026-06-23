"""LLM 分析器 — 调用火山方舟（Volcengine Ark）GLM-5.2 API 生成宏观数据解读。

API 端点（OpenAI 兼容协议）：
    POST {GLM_API_BASE}/chat/completions
    Authorization: Bearer {GLM_API_KEY}
"""
from __future__ import annotations

import json
from typing import Any

import requests

from src.config import GLM_API_BASE, GLM_API_KEY, GLM_MODEL, IndicatorConfig


SYSTEM_PROMPT = """你是一位专业的中国宏观经济分析师，擅长用简洁、专业、客观的语言解读经济数据。
你的解读应遵循以下原则：
1. 用 100-180 字精炼表达，避免冗余
2. 优先呈现数据事实，再做解读，最后给出关注点
3. 避免过度推测，对不确定的因素使用"可能""或"等词
4. 不使用 Markdown 格式，输出纯文本段落"""


USER_PROMPT_TEMPLATE = """请解读以下中国宏观经济数据：

【指标】{name}
【指标说明】{description}
【最新值】{latest_value} {unit}（数据期：{latest_date}）
【上期值】{prev_value} {unit}{prev_date_part}
【环比变化】{delta_str}

请生成一段简明分析，包括：
（1）本期数值水平的含义；
（2）与上期比较的变化方向与幅度；
（3）背后可能的原因或宏观背景；
（4）后续值得关注的方向。"""


def _build_user_prompt(
    ind: IndicatorConfig,
    latest_value: float,
    latest_date: str,
    prev_value: float | None,
    prev_date: str | None,
) -> str:
    """构造用户 prompt。"""
    if prev_value is None:
        prev_str = "（暂无）"
        delta_str = "无可比数据"
        prev_date_part = ""
    else:
        prev_str = f"{prev_value}"
        delta = latest_value - prev_value
        sign = "+" if delta > 0 else ("" if delta == 0 else "")
        delta_str = f"{sign}{delta:.2f} {ind.unit}"
        prev_date_part = f"（数据期：{prev_date}）" if prev_date else ""

    return USER_PROMPT_TEMPLATE.format(
        name=ind.name,
        description=ind.description,
        latest_value=latest_value,
        unit=ind.unit,
        latest_date=latest_date,
        prev_value=prev_str,
        prev_date_part=prev_date_part,
        delta_str=delta_str,
    )


def analyze(
    ind: IndicatorConfig,
    latest_value: float,
    latest_date: str,
    prev_value: float | None = None,
    prev_date: str | None = None,
    timeout: int = 60,
) -> str:
    """调用 LLM 生成单个指标的解读文本。

    返回：纯文本段落（已去除前后空白）。
    抛出：requests.RequestException / RuntimeError（API 错误时）。
    """
    if not GLM_API_KEY:
        raise RuntimeError("GLM_API_KEY 未配置，请检查 .env 文件")

    user_prompt = _build_user_prompt(ind, latest_value, latest_date, prev_value, prev_date)

    url = GLM_API_BASE.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": GLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 600,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(
            f"LLM API 请求失败 (HTTP {resp.status_code}): {resp.text[:500]}"
        )

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(
            f"LLM 响应格式异常: {json.dumps(data, ensure_ascii=False)[:500]}"
        ) from e

    return text.strip()


def get_model_name() -> str:
    """返回当前使用的模型名（用于落库记录）。"""
    return GLM_MODEL
