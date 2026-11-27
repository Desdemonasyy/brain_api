"""家族聚类：把 PnL 相关 >= 阈值的候选合并，只保留一个代表。

规则：
- 已提交/已验证的 alpha 是锚点，永不改写状态。
- 一个簇里只要有锚点，所有未提交的同簇候选都被抑制。
- 没有锚点时，选 Sharpe/Fitness 最高的候选作为代表。
"""

from __future__ import annotations

import json

from .client import BrainClient
from .corr import series_correlation, sync_pnl
from .ledger import Ledger

TARGET_STATUSES = ["audited", "corr_pending", "corr_passed", "gate_passed", "family_suppressed"]
ANCHOR_STATUSES = ["verified", "submitted"]


def _find(parent: dict[str, str], node: str) -> str:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _union(parent: dict[str, str], a: str, b: str) -> None:
    root_a = _find(parent, a)
    root_b = _find(parent, b)
    if root_a != root_b:
        parent[root_b] = root_a


def _score(candidate: dict, alpha: dict | None) -> float:
    if not alpha:
        return -1.0
    sharpe = alpha.get("sharpe") or 0.0
    fitness = alpha.get("fitness") or 0.0
    return float(sharpe) * 100 + float(fitness) * 10 + float(candidate.get("priority") or 0.0)


def cluster_batch(
    ledger: Ledger,
    client: BrainClient | None = None,
    batch_id: str | None = None,
    threshold: float = 0.95,
    sync: bool = True,
    min_overlap: int = 250,
) -> dict:
    if sync and client:
        sync_pnl(ledger, client, batch_id=batch_id)
    targets = ledger.list_candidates(batch_id, TARGET_STATUSES)
    for candidate in targets:
        ledger.delete_gate(candidate["id"], "G6_FAMILY")
        if candidate["status"] == "family_suppressed":
            ledger.set_candidate_status(candidate["id"], "corr_pending")
            candidate["status"] = "corr_pending"
    anchors = ledger.list_candidates(statuses=ANCHOR_STATUSES)
    pool = {item["id"]: item for item in anchors + targets}
    alpha_by_candidate = {cid: ledger.alpha_for_candidate(cid) for cid in pool}
    pnl_cache = {
        cid: ledger.load_pnl(alpha["alpha_id"])
        for cid, alpha in alpha_by_candidate.items()
        if alpha
    }

    parent = {cid: cid for cid in pool}
    pair_details: dict[tuple[str, str], float] = {}
    ids = list(pool)
    for index, left_id in enumerate(ids):
        left_alpha = alpha_by_candidate.get(left_id)
        if not left_alpha:
            continue
        left_pnl = pnl_cache.get(left_id) or {}
        if not left_pnl:
            continue
        for right_id in ids[index + 1:]:
            right_alpha = alpha_by_candidate.get(right_id)
            if not right_alpha:
                continue
            right_pnl = pnl_cache.get(right_id) or {}
            if not right_pnl:
                continue
            correlation = series_correlation(left_pnl, right_pnl, min_overlap=min_overlap)
            if correlation is None:
                continue
            if correlation >= threshold:
                _union(parent, left_id, right_id)
                pair_details[(left_id, right_id)] = correlation

    clusters: dict[str, list[str]] = {}
    for cid in ids:
        clusters.setdefault(_find(parent, cid), []).append(cid)

    suppressed = 0
    representatives = 0
    for members in clusters.values():
        target_members = [cid for cid in members if pool[cid]["status"] in TARGET_STATUSES]
        if not target_members:
            continue
        anchor_members = [cid for cid in members if pool[cid]["status"] in ANCHOR_STATUSES]
        if anchor_members:
            representative = max(anchor_members, key=lambda cid: _score(pool[cid], alpha_by_candidate.get(cid)))
        else:
            representative = max(target_members, key=lambda cid: _score(pool[cid], alpha_by_candidate.get(cid)))

        for cid in target_members:
            candidate = pool[cid]
            alpha = alpha_by_candidate.get(cid)
            if cid == representative and not anchor_members:
                representatives += 1
                detail = {
                    "role": "representative",
                    "cluster_size": len(members),
                    "representative": candidate["label"],
                    "anchors": [pool[a]["label"] for a in anchor_members],
                }
                ledger.set_gate(cid, "G6_FAMILY", "PASS", None, threshold, json.dumps(detail, ensure_ascii=False))
                if candidate["status"] in ("audited", "corr_pending", "corr_passed", "gate_passed"):
                    ledger.log("family", cid, "family_representative", detail)
                continue

            if cid == representative and anchor_members:
                continue

            max_corr = 0.0
            for (left, right), value in pair_details.items():
                if {left, right} & {cid} and {left, right} & set(members):
                    max_corr = max(max_corr, value)
            detail = {
                "role": "suppressed",
                "representative": pool[representative]["label"],
                "representative_id": representative,
                "cluster_size": len(members),
                "max_corr": round(max_corr, 4),
                "threshold": threshold,
                "anchors": [pool[a]["label"] for a in anchor_members],
            }
            ledger.set_gate(
                cid,
                "G6_FAMILY",
                "FAIL",
                max_corr if max_corr else None,
                threshold,
                json.dumps(detail, ensure_ascii=False),
            )
            ledger.set_candidate_status(cid, "family_suppressed")
            ledger.log("family", cid, "family_suppressed", detail)
            suppressed += 1
            print(
                f"  SUPPRESS {candidate['label']:24s} -> {pool[representative]['label']} "
                f"corr={max_corr:.3f}",
                flush=True,
            )

    for candidate in targets:
        cid = candidate["id"]
        if cid not in pool:
            continue
        existing = next(
            (item for item in ledger.get_gates(cid) if item["gate"] == "G6_FAMILY"), None
        )
        if existing:
            continue
        if not pnl_cache.get(cid):
            detail = {"role": "pending", "reason": "缺少 PnL，无法做家族聚类"}
            ledger.set_gate(cid, "G6_FAMILY", "PENDING", None, threshold, json.dumps(detail, ensure_ascii=False))
            continue
        detail = {"role": "singleton", "cluster_size": 1}
        ledger.set_gate(cid, "G6_FAMILY", "PASS", None, threshold, json.dumps(detail, ensure_ascii=False))
        representatives += 1

    print(f"\n家族聚类：目标 {len(targets)} / 锚点 {len(anchors)} / 抑制 {suppressed} / 代表 {representatives}")
    return {"targets": len(targets), "anchors": len(anchors), "suppressed": suppressed, "representatives": representatives}
