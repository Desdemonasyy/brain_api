"""平台 recordset 解析工具：pnl / yearly-stats / correlations 通用。"""

from __future__ import annotations


def parse_records(payload: dict | list | None) -> list[dict]:
    if not payload:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    records = payload.get("records")
    if not records:
        return []
    schema = payload.get("schema") or {}
    properties = schema.get("properties") or []
    names = [item.get("name") for item in properties]
    if names and isinstance(records[0], (list, tuple)):
        return [dict(zip(names, record)) for record in records]
    if isinstance(records[0], dict):
        return records
    return []


def to_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
