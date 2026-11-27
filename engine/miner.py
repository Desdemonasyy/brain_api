"""挖掘 agent 的候选 JSON schema 与校验。

LLM/人工只需产出符合本 schema 的 plan，`load` 会统一转成候选池记录。
"""

from __future__ import annotations

import json

PLAN_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "batch": {"type": "string"},
        "hypothesis": {"type": "string"},
        "defaults": {"type": "object"},
        "items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["expression"],
                "properties": {
                    "label": {"type": "string"},
                    "expression": {"type": "string"},
                    "settings": {"type": "object"},
                    "priority": {"type": "number"},
                },
            },
        },
    },
}


def validate_plan(payload) -> dict:
    if isinstance(payload, list):
        payload = {"items": payload}
    if not isinstance(payload, dict):
        raise ValueError("plan 必须是 JSON object 或 item 数组")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("plan.items 必须是非空数组")
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] 不是 object")
            continue
        expression = item.get("expression") or item.get("code")
        if not expression or not isinstance(expression, str):
            errors.append(f"items[{index}].expression 缺失")
        settings = item.get("settings")
        if settings is not None and not isinstance(settings, dict):
            errors.append(f"items[{index}].settings 必须是 object")
        priority = item.get("priority")
        if priority is not None and not isinstance(priority, (int, float)):
            errors.append(f"items[{index}].priority 必须是 number")
    if errors:
        raise ValueError("plan 校验失败: " + "; ".join(errors))
    return payload


def load_plan(path: str) -> dict:
    import sys
    from pathlib import Path

    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return validate_plan(json.loads(raw))
