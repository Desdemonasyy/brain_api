"""G7 闸门：额度、竞赛匹配、人工队列。

只负责把 corr_passed 的候选排进提交队列，不调用 submit。
"""

from __future__ import annotations

import json

from . import config
from .ledger import Ledger, today_utc
from .records import to_float


def _gate_map(ledger: Ledger, candidate_id: str) -> dict[str, dict]:
    return {row["gate"]: row for row in ledger.get_gates(candidate_id)}


def _find_check(checks: list[dict], name: str) -> dict | None:
    return next((item for item in checks if item.get("name") == name), None)


def _score(alpha: dict, g6_detail: dict, region_weight: float, threshold: float) -> float:
    sharpe = to_float(alpha.get("sharpe")) or 0.0
    fitness = to_float(alpha.get("fitness")) or 0.0
    self_corr = to_float(alpha.get("self_corr"))
    prod_corr = to_float(alpha.get("prod_corr"))
    values = [value for value in (self_corr, prod_corr) if value is not None]
    headroom = threshold - (max(values) if values else 0.0)
    return sharpe * 100 + fitness * 10 + headroom * 5 + region_weight * 0.05


def _evidence(ledger: Ledger, candidate: dict, alpha: dict) -> dict:
    checks = []
    try:
        checks = json.loads(alpha.get("checks_json") or "[]")
    except (TypeError, ValueError):
        checks = []
    return {
        "candidate_id": candidate["id"],
        "label": candidate["label"],
        "batch": candidate["batch_id"],
        "hypothesis": candidate["hypothesis_id"],
        "region": candidate["region"],
        "universe": candidate["universe"],
        "delay": candidate["delay"],
        "expression": candidate["expression"],
        "settings": json.loads(candidate["settings_json"]),
        "alpha_id": alpha["alpha_id"],
        "sharpe": alpha.get("sharpe"),
        "fitness": alpha.get("fitness"),
        "turnover": alpha.get("turnover"),
        "returns": alpha.get("returns"),
        "drawdown": alpha.get("drawdown"),
        "margin": alpha.get("margin"),
        "grade": alpha.get("grade"),
        "self_corr": alpha.get("self_corr"),
        "prod_corr": alpha.get("prod_corr"),
        "checks": checks,
        "gates": [
            {
                "gate": row["gate"],
                "result": row["result"],
                "value": row["value"],
                "limit": row["limit_value"],
                "detail": row["detail"],
            }
            for row in ledger.get_gates(candidate["id"])
        ],
    }


def gate_batch(
    ledger: Ledger,
    batch_id: str | None = None,
    limit: int | None = None,
) -> dict:
    gates = config.load_gates()
    g7 = gates.get("g7", {})
    daily_limit = int(g7.get("daily_submit_limit", 2))
    threshold = float(gates.get("g6", {}).get("corr_threshold", 0.7))
    regions = config.load_regions()
    region_weights = {
        region: float(profile.get("weight", 0.0))
        for region, profile in (regions.get("regions") or {}).items()
    }

    submitted_today = ledger.daily_submit_count(today_utc())
    remaining = max(0, daily_limit - submitted_today)
    candidates = ledger.list_candidates(batch_id, ["corr_passed"], limit=limit)
    print(
        f"G7 待排队 {len(candidates)} 条；今日已提交 {submitted_today}/{daily_limit}，剩余 {remaining}"
    )

    eligible: list[tuple[float, dict, dict]] = []
    counts: dict[str, int] = {}
    for candidate in candidates:
        alpha = ledger.alpha_for_candidate(candidate["id"])
        if not alpha:
            ledger.set_candidate_status(candidate["id"], "gate_error")
            counts["gate_error"] = counts.get("gate_error", 0) + 1
            continue
        gate_rows = _gate_map(ledger, candidate["id"])
        hard_fail = [
            name
            for name in ("G1_PRECHECK", "G2_PLATFORM_CHECKS", "G3_QUALITY", "G4_TURNOVER", "G5_ROBUSTNESS", "G6_CORRELATION")
            if gate_rows.get(name, {}).get("result") != "PASS"
        ]
        if hard_fail:
            ledger.set_gate(
                candidate["id"],
                "G7_QUOTA_COMPETITION",
                "FAIL",
                None,
                None,
                json.dumps({"reason": "前序闸门未全过", "failed": hard_fail}, ensure_ascii=False),
            )
            ledger.set_candidate_status(candidate["id"], "gate_error")
            counts["gate_error"] = counts.get("gate_error", 0) + 1
            print(f"  GATE_ERROR {candidate['label']:22s} failed={','.join(hard_fail)}", flush=True)
            continue

        checks = []
        try:
            checks = json.loads(alpha.get("checks_json") or "[]")
        except (TypeError, ValueError):
            checks = []
        competition = _find_check(checks, "MATCHES_COMPETITION")
        if competition and str(competition.get("result", "")).upper() == "FAIL":
            ledger.set_gate(
                candidate["id"],
                "G7_QUOTA_COMPETITION",
                "FAIL",
                None,
                None,
                json.dumps({"reason": "MATCHES_COMPETITION FAIL", "competition": competition}, ensure_ascii=False),
            )
            ledger.set_candidate_status(candidate["id"], "rejected_gate")
            counts["rejected_gate"] = counts.get("rejected_gate", 0) + 1
            print(f"  REJECTED   {candidate['label']:22s} MATCHES_COMPETITION FAIL", flush=True)
            continue
        if not competition and g7.get("require_competition_match", True):
            ledger.set_gate(
                candidate["id"],
                "G7_QUOTA_COMPETITION",
                "PENDING",
                None,
                None,
                json.dumps({"reason": "缺少 MATCHES_COMPETITION 检查"}, ensure_ascii=False),
            )
            ledger.set_candidate_status(candidate["id"], "gate_pending")
            counts["gate_pending"] = counts.get("gate_pending", 0) + 1
            print(f"  PENDING    {candidate['label']:22s} 缺 MATCHES_COMPETITION", flush=True)
            continue

        g6 = gate_rows["G6_CORRELATION"]
        try:
            g6_detail = json.loads(g6.get("detail") or "{}")
        except (TypeError, ValueError):
            g6_detail = {}
        score = _score(alpha, g6_detail, region_weights.get(candidate["region"], 0.0), threshold)
        eligible.append((score, candidate, alpha))

    if not eligible:
        print("\n没有可排队的候选")
        return {"queued": 0, "eligible": 0, "submitted_today": submitted_today}

    if remaining <= 0:
        for _, candidate, _ in eligible:
            ledger.set_gate(
                candidate["id"],
                "G7_QUOTA_COMPETITION",
                "FAIL",
                float(submitted_today),
                float(daily_limit),
                json.dumps({"reason": "今日提交额度已用完，顺延次日"}, ensure_ascii=False),
            )
        print("\n今日额度已用完，全部顺延")
        return {"queued": 0, "eligible": len(eligible), "submitted_today": submitted_today}

    eligible.sort(key=lambda item: item[0], reverse=True)
    selected = eligible[:remaining] if limit is None else eligible[: min(remaining, limit)]
    selected_ids = {item[1]["id"] for item in selected}

    for score, candidate, alpha in eligible:
        if candidate["id"] in selected_ids:
            evidence = _evidence(ledger, candidate, alpha)
            evidence["score"] = score
            ledger.upsert_submission(
                candidate["id"],
                alpha["alpha_id"],
                status="queued",
                queue_rank=score,
                evidence=evidence,
            )
            ledger.set_gate(
                candidate["id"],
                "G7_QUOTA_COMPETITION",
                "PASS",
                float(submitted_today),
                float(daily_limit),
                json.dumps(
                    {"reason": "已进入提交队列，等待人工批准", "score": round(score, 2)},
                    ensure_ascii=False,
                ),
            )
            ledger.set_candidate_status(candidate["id"], "awaiting_human")
            ledger.log("gate", candidate["id"], "queued", {"score": score})
            counts["queued"] = counts.get("queued", 0) + 1
            print(
                f"  QUEUE {candidate['label']:24s} S={alpha.get('sharpe')} "
                f"F={alpha.get('fitness')} score={score:.2f}",
                flush=True,
            )
        else:
            ledger.set_gate(
                candidate["id"],
                "G7_QUOTA_COMPETITION",
                "FAIL",
                float(submitted_today),
                float(daily_limit),
                json.dumps({"reason": "今日队列已满，优先级不足"}, ensure_ascii=False),
            )
            counts["deferred"] = counts.get("deferred", 0) + 1

    print("\nG7 汇总：" + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return {
        "queued": counts.get("queued", 0),
        "eligible": len(eligible),
        "submitted_today": submitted_today,
        "counts": counts,
    }
