"""G6 相关性与家族聚类：本地 PnL 预筛 + 平台 self/prod 确认。

平台 self correlation 端点和 alpha.is.selfCorrelation 可用；
prod correlation 端点在当前账号返回 403，因此以 alpha.is.prodCorrelation 为准，
缺失时 G6 置 PENDING，必须人工在平台确认后用 `corr set-prod` 写回。
"""

from __future__ import annotations

import json
import math

from . import config
from .client import BrainClient
from .ledger import Ledger
from .records import to_float

CORR_STATUSES = ["audited", "corr_pending", "corr_passed", "gate_passed"]
BENCHMARK_STATUSES = ["verified", "submitted"]


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 3:
        return None
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a <= 0 or var_b <= 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def series_correlation(
    a: dict[str, float],
    b: dict[str, float],
    min_overlap: int = 250,
) -> float | None:
    """按平台口径计算相关性。

    alpha_pnl 存的是累计 PnL；平台 self/prod correlation 用的是日 PnL
    变化（等价于日收益相关）。直接对累计值做相关会显著高估，因此这里
    统一先做一阶差分。
    """
    common = sorted(set(a) & set(b))
    if len(common) < min_overlap:
        return None
    av = [a[d] for d in common]
    bv = [b[d] for d in common]
    da = [av[i] - av[i - 1] for i in range(1, len(av))]
    db = [bv[i] - bv[i - 1] for i in range(1, len(bv))]
    return _pearson(da, db)


def local_correlation(
    ledger: Ledger,
    alpha_id: str,
    benchmark_ids: list[str] | None = None,
    min_overlap: int = 250,
) -> list[dict]:
    target = ledger.load_pnl(alpha_id)
    if not target:
        return []
    results: list[dict] = []
    for benchmark_id in benchmark_ids or []:
        if benchmark_id == alpha_id:
            continue
        series = ledger.load_pnl(benchmark_id)
        if not series:
            continue
        value = series_correlation(target, series, min_overlap)
        if value is None:
            continue
        common_count = len(set(target) & set(series))
        results.append({"benchmark_id": benchmark_id, "correlation": value, "overlap": common_count})
    results.sort(key=lambda item: item["correlation"], reverse=True)
    return results


def _benchmark_ids(ledger: Ledger, region: str | None = None) -> list[str]:
    ids: list[str] = []
    for candidate in ledger.list_candidates(statuses=BENCHMARK_STATUSES):
        if region and candidate["region"] != region:
            continue
        alpha = ledger.alpha_for_candidate(candidate["id"])
        if alpha:
            ids.append(alpha["alpha_id"])
    return list(dict.fromkeys(ids))


def _target_alpha_ids(ledger: Ledger, batch_id: str | None) -> list[str]:
    ids: list[str] = []
    for candidate in ledger.list_candidates(batch_id, CORR_STATUSES):
        alpha = ledger.alpha_for_candidate(candidate["id"])
        if alpha:
            ids.append(alpha["alpha_id"])
    return list(dict.fromkeys(ids))


def sync_pnl(
    ledger: Ledger,
    client: BrainClient,
    batch_id: str | None = None,
    force: bool = False,
    include_benchmarks: bool = True,
) -> dict:
    ids = _target_alpha_ids(ledger, batch_id)
    if include_benchmarks:
        ids.extend(_benchmark_ids(ledger))
    ids = list(dict.fromkeys(ids))
    fetched = 0
    skipped = 0
    failed: list[str] = []
    for alpha_id in ids:
        if not force and ledger.pnl_count(alpha_id) > 0:
            skipped += 1
            continue
        rows = client.get_pnl_records(alpha_id)
        if not rows:
            failed.append(alpha_id)
            continue
        ledger.record_pnl(alpha_id, rows)
        fetched += 1
        print(f"  PnL {alpha_id:12s} {len(rows)} rows", flush=True)
    print(f"\nPnL 同步：新增 {fetched} / 跳过 {skipped} / 失败 {len(failed)}")
    return {"fetched": fetched, "skipped": skipped, "failed": failed}


def _store_platform_self(ledger: Ledger, alpha_id: str, rows: list[dict]) -> list[dict]:
    mapped = []
    for row in rows:
        correlation = to_float(row.get("correlation"))
        if correlation is None:
            continue
        mapped.append(
            {
                "benchmark_id": row.get("id") or row.get("benchmark_id") or "",
                "correlation": correlation,
                "sharpe": to_float(row.get("sharpe")),
                "returns": to_float(row.get("returns")),
                "turnover": to_float(row.get("turnover")),
                "fitness": to_float(row.get("fitness")),
                "margin": to_float(row.get("margin")),
            }
        )
    if mapped:
        ledger.replace_correlations(alpha_id, "self", mapped, "platform_endpoint")
    return mapped


def _store_local_self(ledger: Ledger, alpha_id: str, region: str) -> list[dict]:
    rows = local_correlation(ledger, alpha_id, _benchmark_ids(ledger, region))[:10]
    mapped = []
    for row in rows:
        benchmark = ledger.get_alpha(row["benchmark_id"]) or {}
        mapped.append(
            {
                "benchmark_id": row["benchmark_id"],
                "correlation": row["correlation"],
                "sharpe": to_float(benchmark.get("sharpe")),
                "returns": to_float(benchmark.get("returns")),
                "turnover": to_float(benchmark.get("turnover")),
                "fitness": to_float(benchmark.get("fitness")),
                "margin": to_float(benchmark.get("margin")),
            }
        )
    if mapped:
        ledger.replace_correlations(alpha_id, "self", mapped, "local_pnl")
    return mapped


def _store_prod(ledger: Ledger, alpha_id: str, value: float | None, trusted: bool) -> None:
    if value is None or not trusted:
        return
    ledger.replace_correlations(
        alpha_id,
        "prod",
        [{"benchmark_id": "PRODUCTION", "correlation": value}],
        "alpha_detail",
    )


def evaluate_g6(ledger: Ledger, candidate: dict, alpha_row: dict, gates: dict) -> dict:
    alpha_id = alpha_row["alpha_id"]
    threshold = float(gates.get("g6", {}).get("corr_threshold", 0.7))
    exemption = float(gates.get("g6", {}).get("self_exemption_multiplier", 1.1))

    self_rows = ledger.get_correlations(alpha_id, "self")
    prod_rows = ledger.get_correlations(alpha_id, "prod")
    self_max = self_rows[0] if self_rows else None
    prod_max = prod_rows[0] if prod_rows else None

    sharpe = to_float(alpha_row.get("sharpe"))
    benchmark_sharpe = to_float(self_max.get("sharpe")) if self_max else None
    exempt = bool(
        self_max
        and benchmark_sharpe is not None
        and sharpe is not None
        and sharpe >= benchmark_sharpe * exemption
    )

    if self_max is None:
        self_pass: bool | None = None
    else:
        self_pass = float(self_max["correlation"]) < threshold or exempt

    if prod_max is None:
        prod_pass: bool | None = None
    else:
        prod_pass = float(prod_max["correlation"]) < threshold

    family_gate = next(
        (item for item in ledger.get_gates(candidate["id"]) if item["gate"] == "G6_FAMILY"),
        None,
    )
    family_pass: bool | None = None
    if family_gate:
        family_pass = family_gate["result"] == "PASS"

    if family_pass is False:
        result = "FAIL"
    elif self_pass is False or prod_pass is False:
        result = "FAIL"
    elif self_pass is None or prod_pass is None or family_pass is None:
        result = "PENDING"
    else:
        result = "PASS"

    detail = {
        "alpha_id": alpha_id,
        "threshold": threshold,
        "self_max": self_max,
        "self_pass": self_pass,
        "self_exempt": exempt,
        "exemption_multiplier": exemption,
        "prod_max": prod_max,
        "prod_pass": prod_pass,
        "family_pass": family_pass,
    }
    values: list[float] = []
    if self_max:
        values.append(float(self_max["correlation"]))
    if prod_max:
        values.append(float(prod_max["correlation"]))
    return {
        "gate": "G6_CORRELATION",
        "result": result,
        "value": max(values) if values else None,
        "limit": threshold,
        "detail": json.dumps(detail, ensure_ascii=False),
    }


def check_candidate(ledger: Ledger, client: BrainClient, candidate: dict, gates: dict) -> dict:
    alpha_row = ledger.alpha_for_candidate(candidate["id"])
    if not alpha_row:
        return {"result": "PENDING", "reason": "台账里没有 alpha"}

    alpha_id = alpha_row["alpha_id"]
    payload = client.get_alpha(alpha_id)
    ledger.record_alpha(candidate["id"], payload, yearly=None)
    stats = payload.get("is") or {}

    platform_rows = client.get_self_correlation(alpha_id)
    if platform_rows:
        stored = _store_platform_self(ledger, alpha_id, platform_rows)
        self_source = "platform_endpoint"
    else:
        detail_self = to_float(stats.get("selfCorrelation"))
        if detail_self is not None:
            ledger.replace_correlations(
                alpha_id,
                "self",
                [{"benchmark_id": "PLATFORM", "correlation": detail_self}],
                "alpha_detail",
            )
            stored = [{"benchmark_id": "PLATFORM", "correlation": detail_self}]
            self_source = "alpha_detail"
        else:
            stored = _store_local_self(ledger, alpha_id, candidate["region"])
            self_source = "local_pnl"

    prod_value = to_float(stats.get("prodCorrelation"))
    prod_trusted = bool(
        prod_value is not None
        and (prod_value > 0 or str(payload.get("status", "")).upper() in ("ACTIVE", "SUBMITTED"))
    )
    _store_prod(ledger, alpha_id, prod_value, prod_trusted)

    alpha_row = ledger.alpha_for_candidate(candidate["id"]) or alpha_row
    gate = evaluate_g6(ledger, candidate, alpha_row, gates)
    gate["detail"] = json.dumps(
        {**json.loads(gate["detail"]), "self_source": self_source, "prod_source": "alpha_detail" if prod_trusted else "unavailable"},
        ensure_ascii=False,
    )
    ledger.set_gate(
        candidate["id"],
        gate["gate"],
        gate["result"],
        gate.get("value"),
        gate.get("limit"),
        gate["detail"],
    )
    if gate["result"] == "PASS":
        status = "corr_passed"
    elif gate["result"] == "FAIL":
        status = "rejected_corr"
    else:
        status = "corr_pending"
    ledger.set_candidate_status(candidate["id"], status)
    ledger.log(
        "corr",
        candidate["id"],
        "corr_check",
        {"alpha_id": alpha_id, "result": gate["result"], "self_source": self_source},
    )
    return {**gate, "status": status, "alpha_id": alpha_id}


def set_prod_corr(
    ledger: Ledger,
    candidate_id: str,
    value: float,
    note: str = "",
    gates: dict | None = None,
) -> dict:
    candidate = ledger.get_candidate(candidate_id)
    if not candidate:
        raise ValueError("候选不存在")
    alpha_row = ledger.alpha_for_candidate(candidate_id)
    if not alpha_row:
        raise ValueError("候选没有 alpha")
    ledger.replace_correlations(
        alpha_row["alpha_id"],
        "prod",
        [{"benchmark_id": "MANUAL", "correlation": float(value)}],
        "manual",
    )
    ledger.set_alpha_corr(alpha_row["alpha_id"], prod_corr=float(value))
    ledger.log(
        "corr",
        candidate_id,
        "set_prod_corr",
        {"value": float(value), "note": note},
    )
    gate = evaluate_g6(ledger, candidate, ledger.alpha_for_candidate(candidate_id), gates or config.load_gates())
    ledger.set_gate(
        candidate_id,
        gate["gate"],
        gate["result"],
        gate.get("value"),
        gate.get("limit"),
        gate["detail"],
    )
    status = "corr_passed" if gate["result"] == "PASS" else ("rejected_corr" if gate["result"] == "FAIL" else "corr_pending")
    ledger.set_candidate_status(candidate_id, status)
    return {**gate, "status": status}


def check_batch(
    ledger: Ledger,
    client: BrainClient,
    batch_id: str | None = None,
    limit: int | None = None,
    sync: bool = True,
) -> dict:
    gates = config.load_gates()
    if sync:
        sync_pnl(ledger, client, batch_id=batch_id)
    candidates = ledger.list_candidates(batch_id, CORR_STATUSES, limit=limit)
    counts: dict[str, int] = {}
    print(f"待相关性检查 {len(candidates)} 条（batch={batch_id or '*'}）")
    for candidate in candidates:
        try:
            result = check_candidate(ledger, client, candidate, gates)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {candidate['label']:24s} {str(exc)[:160]}", flush=True)
            ledger.set_candidate_status(candidate["id"], "corr_error")
            ledger.log("corr", candidate["id"], "corr_error", {"error": str(exc)})
            counts["corr_error"] = counts.get("corr_error", 0) + 1
            continue
        status = result.get("status", "corr_pending")
        counts[status] = counts.get(status, 0) + 1
        detail = json.loads(result["detail"])
        self_max = detail.get("self_max") or {}
        prod_max = detail.get("prod_max") or {}
        print(
            f"  {status:14s} {candidate['label']:24s} "
            f"self={self_max.get('correlation')} prod={prod_max.get('correlation')} "
            f"family={detail.get('family_pass')}",
            flush=True,
        )
    print("\n相关性汇总：" + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return counts
