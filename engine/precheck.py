"""G1 预检：表达式语法、算子、字段、设置、反模式、去重。

目标是在消耗模拟配额之前拦掉确定会报错或已被证伪的候选。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .ledger import Ledger, make_family_key

IDENT_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)")
CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
STRING_RE = re.compile(r'"[^"]*"|\'[^\']*\'')


def strip_strings(expression: str) -> str:
    return STRING_RE.sub(" ", expression)


def extract_operators(expression: str) -> list[str]:
    return CALL_RE.findall(strip_strings(expression))


def extract_fields(expression: str) -> list[str]:
    text = strip_strings(expression)
    fields: list[str] = []
    for match in IDENT_RE.finditer(text):
        name = match.group(1)
        tail = text[match.end():]
        if tail.lstrip().startswith("("):
            continue  # 函数名，不是字段
        if name in config.RESERVED_WORDS or name in config.GROUP_NAMES:
            continue
        fields.append(name)
    # 去重但保留顺序
    return list(dict.fromkeys(fields))


def _balanced_parentheses(expression: str) -> bool:
    depth = 0
    for char in strip_strings(expression):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _balanced_quotes(expression: str) -> bool:
    return expression.count('"') % 2 == 0 and expression.count("'") % 2 == 0


class FieldIndex:
    """读取 .state/fields_*.json，按 region/delay/universe 索引字段类型与覆盖率。"""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = Path(state_dir or config.STATE_DIR)
        self._by_key: dict[tuple[str, int, str], dict[str, tuple[str, float | None]]] = {}
        self._global: dict[str, tuple[str, float | None]] = {}
        self._load()

    def _load(self) -> None:
        for path in sorted(self.state_dir.glob("fields_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items = payload.get("results") if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                continue
            for item in items:
                field_id = item.get("id")
                if not field_id:
                    continue
                field_type = item.get("type") or "MATRIX"
                coverage = item.get("coverage")
                region = item.get("region") or "*"
                delay = item.get("delay")
                universe = item.get("universe") or "*"
                try:
                    delay = int(delay) if delay is not None else -1
                except (TypeError, ValueError):
                    delay = -1
                value = (field_type, coverage)
                self._global.setdefault(field_id, value)
                self._by_key.setdefault((region, delay, universe), {})[field_id] = value
                self._by_key.setdefault((region, delay, "*"), {})[field_id] = value

    def lookup(self, field_id: str, region: str, delay: int, universe: str):
        for key in (
            (region, delay, universe),
            (region, delay, "*"),
            ("*", delay, "*"),
        ):
            found = self._by_key.get(key, {}).get(field_id)
            if found:
                return found
        return self._global.get(field_id)


@dataclass
class PrecheckResult:
    ok: bool
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    family_key: str = ""

    def detail_json(self) -> str:
        return json.dumps(
            {
                "fails": self.fails,
                "warns": self.warns,
                "fields": self.fields,
                "operators": self.operators,
            },
            ensure_ascii=False,
        )


def inspect_candidate(
    candidate: dict,
    field_index: FieldIndex,
    gates: dict,
    allow_unknown: bool = False,
) -> PrecheckResult:
    expression = candidate["expression"]
    settings = json.loads(candidate["settings_json"])
    expression_lower = expression.lower()
    region = candidate["region"]
    delay = int(candidate.get("delay", 1))
    universe = candidate.get("universe", "")

    operators = extract_operators(expression)
    fields = extract_fields(expression)
    fails: list[str] = []
    warns: list[str] = []

    # 语法
    if not expression.strip():
        fails.append("表达式为空")
    if not _balanced_parentheses(expression):
        fails.append("括号不配对")
    if not _balanced_quotes(expression):
        fails.append("引号不配对")

    # 算子
    for operator in sorted(set(operators)):
        if operator in config.FORBIDDEN_OPERATORS:
            fails.append(f"算子 {operator} 不可用：{config.FORBIDDEN_OPERATORS[operator]}")
        elif operator not in config.KNOWN_OPERATORS and not allow_unknown:
            fails.append(f"未知算子 {operator}（确认平台存在可加 --allow-unknown）")

    # 字段
    vector_fields: list[str] = []
    min_coverage = float(gates.get("precheck", {}).get("min_field_coverage", 0.5))
    for name in fields:
        meta = field_index.lookup(name, region, delay, universe)
        if meta is None and name not in config.BASE_FIELDS:
            if not allow_unknown:
                fails.append(f"字段 {name} 未在缓存目录中找到（可加 --allow-unknown 跳过）")
            else:
                warns.append(f"字段 {name} 未在缓存目录中找到")
            continue
        if meta is None:
            continue
        field_type, coverage = meta
        if field_type == "VECTOR":
            vector_fields.append(name)
        if coverage is not None and coverage < min_coverage:
            warns.append(f"字段 {name} 覆盖率 {coverage:.2f} < {min_coverage:.2f}")
    if vector_fields and "vec_" not in expression_lower:
        fails.append(f"VECTOR 字段 {','.join(vector_fields)} 必须用 vec_* 聚合")

    # 设置
    precheck_cfg = gates.get("precheck", {})
    if region not in config.REGIONS:
        fails.append(f"region={region} 不在允许列表")
    if not str(settings.get("universe", "")).strip():
        fails.append("universe 为空")
    if settings.get("delay") not in (0, 1):
        fails.append(f"delay={settings.get('delay')} 必须为 0 或 1")
    neutralization = str(settings.get("neutralization", "")).upper()
    if neutralization not in config.NEUTRALIZATIONS:
        fails.append(f"neutralization={neutralization} 不在允许列表")
    decay = settings.get("decay")
    if not isinstance(decay, int) or decay < 0 or decay > int(precheck_cfg.get("max_decay", 512)):
        fails.append(f"decay={decay} 非法")
    truncation = settings.get("truncation")
    if not isinstance(truncation, (int, float)) or not 0 <= float(truncation) <= 1:
        fails.append(f"truncation={truncation} 非法")
    test_period = str(settings.get("testPeriod", "0Y0M")).replace(" ", "")
    if precheck_cfg.get("require_test_period_zero", True) and test_period not in ("0Y0M", "0Y", "0M", "0", "0Y0M0D"):
        fails.append(f"testPeriod={test_period} 必须为 0Y0M")

    profile = config.region_profile(region)
    allowed_universes = profile.get("universes")
    if allowed_universes and universe not in allowed_universes:
        warns.append(f"universe={universe} 不在 {region} 配置列表 {allowed_universes}")
    allowed_neuts = profile.get("neutralizations")
    if allowed_neuts and neutralization not in allowed_neuts:
        warns.append(f"neutralization={neutralization} 不在 {region} 配置列表")
    allowed_delays = profile.get("delays")
    if allowed_delays and settings.get("delay") not in allowed_delays:
        warns.append(f"delay={settings.get('delay')} 不在 {region} 配置列表 {allowed_delays}")

    # 双重中性化：表达式已 group_*，设置层再行业中性的会抹平信号
    has_group = any(token in expression_lower for token in ("group_rank(", "group_zscore(", "group_neutralize("))
    if has_group and neutralization not in ("NONE", "MARKET"):
        message = f"表达式含 group_* 且 neutralization={neutralization}，语义上构成双重中性化"
        if precheck_cfg.get("fail_on_double_neutralization", False):
            fails.append(message)
        else:
            warns.append(message)

    # 已证伪反模式
    if re.search(r"\bclose\s*/\s*vwap\s*-\s*1\b", expression_lower):
        fails.append("反模式 close/vwap-1 已被证伪")
    if re.search(r"\bclose\s*-\s*open\b", expression_lower) and not re.search(
        r"\(\s*close\s*-\s*open\s*\)\s*/", expression_lower
    ):
        fails.append("反模式裸差分 close-open，成本会吃掉收益")
    if re.search(r"/\s*volume\b", expression_lower):
        fails.append("反模式 x/volume，单位不一致且换手易爆")
    if re.search(r"ts_std_dev\s*\(\s*scl12_buzz", expression_lower):
        fails.append("反模式 ts_std_dev(scl12_buzz) 已证伪")

    family_key = make_family_key(fields, operators, neutralization)
    return PrecheckResult(
        ok=not fails,
        fails=fails,
        warns=warns,
        fields=fields,
        operators=sorted(set(operators)),
        family_key=family_key,
    )


def precheck_batch(
    ledger: Ledger,
    batch_id: str | None = None,
    allow_unknown: bool = False,
) -> dict:
    gates = config.load_gates()
    field_index = FieldIndex()
    candidates = ledger.list_candidates(
        batch_id=batch_id, statuses=["draft", "precheck_failed", "prechecked"]
    )
    passed = 0
    failed = 0
    for candidate in candidates:
        result = inspect_candidate(candidate, field_index, gates, allow_unknown=allow_unknown)
        conflicts = ledger.family_conflicts(result.family_key, candidate["id"])
        if conflicts:
            result.warns.append(
                "同族已提交/已通过："
                + ", ".join(f"{c['label']}({c['status']})" for c in conflicts[:5])
            )
            ledger.set_candidate_priority(candidate["id"], float(candidate["priority"]) - 0.20)
        ledger.set_gate(
            candidate["id"],
            "G1_PRECHECK",
            "PASS" if result.ok else "FAIL",
            None,
            None,
            result.detail_json(),
        )
        ledger.set_candidate_status(candidate["id"], "prechecked" if result.ok else "precheck_failed")
        ledger.log(
            "precheck",
            candidate["id"],
            "precheck_pass" if result.ok else "precheck_fail",
            {"fails": result.fails, "warns": result.warns},
        )
        if result.ok:
            passed += 1
            print(f"  PASS {candidate['label']:24s} fields={len(result.fields)} ops={len(result.operators)}")
        else:
            failed += 1
            print(f"  FAIL {candidate['label']:24s} " + " | ".join(result.fails))
    print(f"\n预检完成：PASS {passed} / FAIL {failed} / 总计 {len(candidates)}")
    return {"passed": passed, "failed": failed, "total": len(candidates)}
