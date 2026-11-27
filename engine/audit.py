"""G2–G5 稳健审计：平台 checks、收益质量、换手成本、分年/子池稳健性。

只读平台已有结果，不再额外消耗模拟配额。
"""

from __future__ import annotations

import json

from . import config
from .client import BrainClient
from .ledger import Ledger
from .records import parse_records, to_float


def _find_check(checks: list[dict], name: str) -> dict | None:
    for check in checks:
        if check.get("name") == name:
            return check
    return None


G2_DEFERRED_CHECKS = {
    # 相关性属于 G6，竞赛匹配属于 G7，不阻塞 G2
    "SELF_CORRELATION",
    "PROD_CORRELATION",
    "MATCHES_COMPETITION",
    "MATCHES_PYRAMID",
}


def _g2_platform_checks(checks: list[dict]) -> dict:
    hard_checks = [c for c in checks if c.get("name") not in G2_DEFERRED_CHECKS]
    deferred = [c for c in checks if c.get("name") in G2_DEFERRED_CHECKS]
    if not hard_checks:
        return {
            "gate": "G2_PLATFORM_CHECKS",
            "result": "PENDING",
            "value": None,
            "limit": None,
            "detail": json.dumps(
                {"reason": "alpha.is.checks 中没有硬检查项", "deferred": deferred},
                ensure_ascii=False,
            ),
        }
    fails = [c for c in hard_checks if str(c.get("result", "")).upper() == "FAIL"]
    pending = [c for c in hard_checks if str(c.get("result", "")).upper() == "PENDING"]
    result = "FAIL" if fails else ("PENDING" if pending else "PASS")
    notable = fails + pending
    return {
        "gate": "G2_PLATFORM_CHECKS",
        "result": result,
        "value": float(len(fails)),
        "limit": 0.0,
        "detail": json.dumps(
            {
                "failed": notable,
                "total_checks": len(hard_checks),
                "check_names": [c.get("name") for c in hard_checks],
                "deferred": deferred,
                "deferred_names": [c.get("name") for c in deferred],
            },
            ensure_ascii=False,
        ),
    }


def _g3_quality(stats: dict, region: str, delay: int, gates: dict) -> dict:
    cfg = config.region_g3(gates, region)
    g3 = gates.get("g3", {})
    sharpe = to_float(stats.get("sharpe"))
    fitness = to_float(stats.get("fitness"))
    min_sharpe = float(cfg.get("min_sharpe", 1.25))
    min_fitness = float(cfg.get("min_fitness", 1.0))
    if int(delay) == 0:
        min_sharpe = max(min_sharpe, float(g3.get("delay0_min_sharpe", 2.0)))
        min_fitness = max(min_fitness, float(g3.get("delay0_min_fitness", 1.3)))

    if sharpe is None or fitness is None:
        result = "PENDING"
    else:
        result = "PASS" if sharpe >= min_sharpe and fitness >= min_fitness else "FAIL"

    sprint = bool(
        sharpe is not None
        and fitness is not None
        and sharpe >= float(cfg.get("sprint_sharpe", 1.8))
        and fitness >= float(cfg.get("sprint_fitness", 1.5))
    )

    returns = to_float(stats.get("returns"))
    drawdown = to_float(stats.get("drawdown"))
    long_count = to_float(stats.get("longCount"))
    short_count = to_float(stats.get("shortCount"))
    min_returns = float(g3.get("min_returns", 0.10))
    drawdown_warn = float(g3.get("drawdown_warn", 0.15))
    min_long = float(g3.get("min_long_count", 100))
    min_short = float(g3.get("min_short_count", 100))

    warnings: list[str] = []
    if returns is not None and returns < min_returns:
        warnings.append("RETURNS_BELOW_10PCT")
    if drawdown is not None and drawdown > drawdown_warn:
        warnings.append("DRAWDOWN_ABOVE_WARN")
    if long_count is not None and long_count < min_long:
        warnings.append("LONG_COUNT_LOW")
    if short_count is not None and short_count < min_short:
        warnings.append("SHORT_COUNT_LOW")

    long_short_ratio = None
    if long_count is not None and short_count is not None and max(long_count, short_count) > 0:
        long_short_ratio = min(long_count, short_count) / max(long_count, short_count)

    return {
        "gate": "G3_QUALITY",
        "result": result,
        "value": sharpe,
        "limit": min_sharpe,
        "detail": json.dumps(
            {
                "sharpe": sharpe,
                "min_sharpe": min_sharpe,
                "fitness": fitness,
                "min_fitness": min_fitness,
                "delay": int(delay),
                "delay0_thresholds": int(delay) == 0,
                "returns": returns,
                "min_returns": min_returns,
                "returns_ok": None if returns is None else returns >= min_returns,
                "drawdown": drawdown,
                "drawdown_warn": drawdown_warn,
                "drawdown_ok": None if drawdown is None else drawdown <= drawdown_warn,
                "long_count": long_count,
                "short_count": short_count,
                "long_short_ratio": long_short_ratio,
                "breadth_ok": (
                    None
                    if long_count is None or short_count is None
                    else long_count >= min_long and short_count >= min_short
                ),
                "warnings": warnings,
                "sprint": sprint,
            },
            ensure_ascii=False,
        ),
    }


def _turnover_band(turnover: float | None) -> str | None:
    if turnover is None:
        return None
    if turnover < 0.01:
        return "too_low"
    if turnover <= 0.20:
        return "low"
    if turnover <= 0.50:
        return "medium"
    if turnover <= 0.70:
        return "high"
    return "too_high"


def _g4_turnover(stats: dict, gates: dict) -> dict:
    cfg = gates.get("g4", {})
    turnover = to_float(stats.get("turnover"))
    margin = to_float(stats.get("margin"))
    min_turnover = float(cfg.get("min_turnover", 0.01))
    max_turnover = float(cfg.get("max_turnover", 0.70))
    min_margin = cfg.get("min_margin_bps")
    margin_bps = margin * 10000 if margin is not None else None
    if turnover is None:
        result = "PENDING"
    else:
        result = "PASS" if min_turnover <= turnover <= max_turnover else "FAIL"
        if result == "PASS" and min_margin is not None and margin_bps is not None:
            if margin_bps < float(min_margin):
                result = "FAIL"
    preferred = float(cfg.get("preferred_max_turnover", 0.125))
    return {
        "gate": "G4_TURNOVER",
        "result": result,
        "value": turnover,
        "limit": max_turnover,
        "detail": json.dumps(
            {
                "turnover": turnover,
                "range": [min_turnover, max_turnover],
                "band": _turnover_band(turnover),
                "preferred_max": preferred,
                "below_preferred": bool(turnover is not None and turnover <= preferred),
                "margin": margin,
                "margin_bps": margin_bps,
                "min_margin_bps": min_margin,
            },
            ensure_ascii=False,
        ),
    }


def _g5_robustness(yearly: list[dict], checks: list[dict], gates: dict) -> dict:
    cfg = gates.get("g5", {})
    min_years = int(cfg.get("min_years", 3))
    ratio_limit = float(cfg.get("positive_year_ratio", 0.8))
    worst_limit = float(cfg.get("worst_year_sharpe", -0.5))
    buffer = float(cfg.get("sub_universe_buffer", 1.05))

    years: list[dict] = []
    for row in yearly:
        sharpe = to_float(row.get("sharpe"))
        if sharpe is None:
            continue
        years.append({"year": row.get("year"), "sharpe": sharpe})
    if len(years) < min_years:
        return {
            "gate": "G5_ROBUSTNESS",
            "result": "PENDING",
            "value": float(len(years)),
            "limit": float(min_years),
            "detail": json.dumps({"reason": "年度统计不足", "years": years}, ensure_ascii=False),
        }

    positive = sum(1 for item in years if item["sharpe"] > 0)
    positive_ratio = positive / len(years)
    worst = min(item["sharpe"] for item in years)

    sub_formula = "sub_sharpe >= 0.75 * sqrt(sub_size / alpha_size) * alpha_sharpe"
    sub_check = _find_check(checks, "LOW_SUB_UNIVERSE_SHARPE")
    sub_detail = {"check_name": "LOW_SUB_UNIVERSE_SHARPE", "formula": sub_formula}
    sub_ok = True
    if sub_check:
        sub_value = to_float(sub_check.get("value"))
        sub_limit = to_float(sub_check.get("limit"))
        if sub_value is not None and sub_limit is not None:
            sub_ok = sub_value >= sub_limit * buffer
            sub_detail.update(
                {
                    "platform_result": sub_check.get("result"),
                    "value": sub_value,
                    "limit": sub_limit,
                    "buffer": buffer,
                }
            )
        else:
            sub_ok = str(sub_check.get("result", "")).upper() != "FAIL"
            sub_detail.update(
                {
                    "platform_result": sub_check.get("result"),
                    "value": sub_value,
                    "limit": sub_limit,
                }
            )

    ok = positive_ratio >= ratio_limit and worst >= worst_limit and sub_ok
    return {
        "gate": "G5_ROBUSTNESS",
        "result": "PASS" if ok else "FAIL",
        "value": positive_ratio,
        "limit": ratio_limit,
        "detail": json.dumps(
            {
                "years": years,
                "positive_years": positive,
                "total_years": len(years),
                "positive_ratio": positive_ratio,
                "worst_year_sharpe": worst,
                "worst_limit": worst_limit,
                "sub_universe": sub_detail,
                "sub_universe_formula": sub_formula,
            },
            ensure_ascii=False,
        ),
    }


def audit_candidate(
    client: BrainClient,
    ledger: Ledger,
    candidate: dict,
    gates: dict,
) -> dict:
    alpha_row = ledger.alpha_for_candidate(candidate["id"])
    if not alpha_row:
        return {"gate_results": [], "status": "sim_error", "reason": "台账里没有 alpha"}
    alpha_id = alpha_row["alpha_id"]

    payload = client.get_alpha(alpha_id)
    stats = payload.get("is") or {}
    checks = stats.get("checks") or payload.get("checks") or []

    yearly_payload = client.get_yearly_stats(alpha_id)
    if yearly_payload is None and alpha_row.get("yearly_json"):
        try:
            yearly_payload = json.loads(alpha_row["yearly_json"])
        except (TypeError, ValueError):
            yearly_payload = None
    yearly_rows = parse_records(yearly_payload)

    ledger.record_alpha(candidate["id"], payload, yearly=yearly_payload)

    gate_results = [
        _g2_platform_checks(checks),
        _g3_quality(stats, candidate["region"], int(candidate.get("delay", 1)), gates),
        _g4_turnover(stats, gates),
        _g5_robustness(yearly_rows, checks, gates),
    ]
    for item in gate_results:
        ledger.set_gate(
            candidate["id"],
            item["gate"],
            item["result"],
            item.get("value"),
            item.get("limit"),
            item.get("detail", ""),
        )

    results = [item["result"] for item in gate_results]
    if "FAIL" in results:
        status = "rejected_audit"
    elif "PENDING" in results:
        status = "audit_pending"
    else:
        status = "audited"
    ledger.set_candidate_status(candidate["id"], status)
    ledger.log(
        "audit",
        candidate["id"],
        "audit",
        {"alpha_id": alpha_id, "status": status, "gates": {g["gate"]: g["result"] for g in gate_results}},
    )
    return {"gate_results": gate_results, "status": status, "alpha_id": alpha_id, "stats": stats}


def audit_batch(
    ledger: Ledger,
    client: BrainClient,
    batch_id: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> dict:
    gates = config.load_gates()
    statuses = ["simulated", "audit_pending", "audit_error"]
    if force:
        statuses += ["rejected_audit", "audited", "corr_pending"]
    candidates = ledger.list_candidates(
        batch_id=batch_id, statuses=statuses, limit=limit
    )
    counts: dict[str, int] = {}
    print(f"待审计 {len(candidates)} 条（batch={batch_id or '*'}）")
    for candidate in candidates:
        try:
            result = audit_candidate(client, ledger, candidate, gates)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {candidate['label']:24s} {str(exc)[:180]}", flush=True)
            ledger.set_candidate_status(candidate["id"], "audit_error")
            ledger.log("audit", candidate["id"], "audit_error", {"error": str(exc)})
            counts["audit_error"] = counts.get("audit_error", 0) + 1
            continue
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
        stats = result.get("stats") or {}
        sharpe = stats.get("sharpe")
        fitness = stats.get("fitness")
        returns = stats.get("returns")
        drawdown = stats.get("drawdown")
        sh = f"{sharpe:.2f}" if isinstance(sharpe, (int, float)) else "-"
        ft = f"{fitness:.2f}" if isinstance(fitness, (int, float)) else "-"
        rt = f"{returns:.2%}" if isinstance(returns, (int, float)) else "-"
        dd = f"{drawdown:.2%}" if isinstance(drawdown, (int, float)) else "-"
        g3_detail: dict = {}
        for item in result["gate_results"]:
            if item["gate"] == "G3_QUALITY":
                try:
                    g3_detail = json.loads(item.get("detail") or "{}")
                except (TypeError, ValueError):
                    g3_detail = {}
        warnings = ",".join(g3_detail.get("warnings") or []) or "-"
        marks = " ".join(f"{item['gate'].split('_')[0]}={item['result']}" for item in result["gate_results"])
        print(
            f"  {status:15s} {candidate['label']:24s} S={sh} F={ft} R={rt} DD={dd} "
            f"warn={warnings}  {marks}",
            flush=True,
        )
    print("\n审计汇总：" + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return counts
