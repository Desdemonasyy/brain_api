"""提交队列与人工审批：approve 生成哈希，submit 校验哈希后才调用平台。

agent 不得自动调用 submit；approve/submit 都是人类命令。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import config
from .client import BrainClient
from .ledger import Ledger, today_utc, utcnow

REQUIRED_GATES = [
    "G1_PRECHECK",
    "G2_PLATFORM_CHECKS",
    "G3_QUALITY",
    "G4_TURNOVER",
    "G5_ROBUSTNESS",
    "G6_CORRELATION",
    "G6_FAMILY",
    "G7_QUOTA_COMPETITION",
]


def resolve_candidate(ledger: Ledger, key: str, batch_id: str | None = None) -> dict | None:
    if batch_id:
        c = ledger.get_candidate(key)
        if c and c.get("batch_id") == batch_id:
            return c
        for row in ledger.list_candidates(limit=None, batch_id=batch_id):
            if row["label"] == key or row["id"].startswith(key):
                return row
        return None
    candidate = ledger.get_candidate(key)
    if candidate:
        return candidate
    for row in ledger.list_candidates(limit=None):
        if row["label"] == key or row["id"].startswith(key):
            return row
    return None


def show_queue(ledger: Ledger, batch_id: str | None = None, include_done: bool = False) -> list[dict]:
    statuses = ["queued", "approved", "submitted", "verified"] if include_done else ["queued", "approved"]
    rows = ledger.list_queue(batch_id, statuses)
    print(
        f"{'status':10s} {'label':24s} {'alpha':10s} {'S':>5s} {'F':>5s} {'T':>7s} "
        f"{'self':>6s} {'prod':>6s} {'score':>7s} {'approved_by':>12s}"
    )
    for row in rows:
        def fmt(value, digits=2):
            return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"

        print(
            f"{row['status']:10s} {row['label'][:24]:24s} {str(row['alpha_id'] or ''):10s} "
            f"{fmt(row.get('sharpe')):>5s} {fmt(row.get('fitness')):>5s} {fmt(row.get('turnover'), 4):>7s} "
            f"{fmt(row.get('self_corr')):>6s} {fmt(row.get('prod_corr')):>6s} "
            f"{fmt(row.get('queue_rank')):>7s} {str(row.get('approved_by') or '-'):>12s}"
        )
    if not rows:
        print("队列为空")
    return rows


def approve(ledger: Ledger, candidate_key: str, approved_by: str, *, batch_id: str | None = None) -> dict:
    candidate = resolve_candidate(ledger, candidate_key, batch_id=batch_id)
    if not candidate:
        raise ValueError("候选不存在")
    submission = ledger.get_submission(candidate["id"])
    if not submission or submission["status"] != "queued":
        raise ValueError(f"候选不在待批准队列（当前 {submission['status'] if submission else '无记录'}）")
    alpha = ledger.alpha_for_candidate(candidate["id"])
    if not alpha:
        raise ValueError("候选没有 alpha")

    gates = config.load_gates()
    ttl_hours = int(gates.get("g7", {}).get("approval_ttl_hours", 24))
    issued_at = utcnow()
    raw = f"{candidate['id']}|{alpha['alpha_id']}|{candidate['expression']}|{issued_at}"
    approval_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(timespec="seconds")

    ledger.update_submission(
        candidate["id"],
        status="approved",
        approved_by=approved_by,
        approved_at=issued_at,
        approval_hash=approval_hash,
        expires_at=expires_at,
    )
    ledger.set_candidate_status(candidate["id"], "approved")
    ledger.log(
        "human",
        candidate["id"],
        "approve",
        {"by": approved_by, "hash": approval_hash, "expires_at": expires_at},
    )
    print(f"已批准 {candidate['label']} ({alpha['alpha_id']})")
    print(f"approval_hash: {approval_hash}")
    print(f"有效期至: {expires_at}")
    return {"candidate_id": candidate["id"], "approval_hash": approval_hash, "expires_at": expires_at}


def _check_approval(ledger: Ledger, candidate: dict, submission: dict, approval_hash: str) -> None:
    if submission.get("status") != "approved":
        raise ValueError(f"提交状态不是 approved（当前 {submission.get('status')}）")
    if submission.get("approval_hash") != approval_hash:
        raise ValueError("approval_hash 不匹配")
    expires_at = submission.get("expires_at")
    if not expires_at:
        raise ValueError("审批缺少有效期")
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expiry:
        raise ValueError("审批已过期，请重新 approve")
    if candidate["status"] != "approved":
        raise ValueError(f"候选状态不是 approved（当前 {candidate['status']}）")


def _check_gates(ledger: Ledger, candidate_id: str) -> None:
    rows = {row["gate"]: row for row in ledger.get_gates(candidate_id)}
    problems = []
    for name in REQUIRED_GATES:
        row = rows.get(name)
        if not row:
            problems.append(f"{name}=缺失")
        elif row["result"] != "PASS":
            problems.append(f"{name}={row['result']}")
    if problems:
        raise ValueError("闸门未全过: " + ", ".join(problems))


def verify_submission(ledger: Ledger, client: BrainClient, candidate_key: str, *, batch_id: str | None = None) -> dict:
    candidate = resolve_candidate(ledger, candidate_key, batch_id=batch_id)
    if not candidate:
        raise ValueError("候选不存在")
    alpha = ledger.alpha_for_candidate(candidate["id"])
    if not alpha:
        raise ValueError("候选没有 alpha")
    payload = client.get_alpha(alpha["alpha_id"])
    ledger.record_alpha(candidate["id"], payload)
    date_submitted = payload.get("dateSubmitted")
    if date_submitted:
        ledger.update_submission(
            candidate["id"],
            status="verified",
            platform_status=payload.get("status"),
            submitted_at=utcnow(),
        )
        ledger.set_candidate_status(candidate["id"], "verified")
        print(f"已确认提交 {candidate['label']} ({alpha['alpha_id']}) dateSubmitted={date_submitted}")
    else:
        ledger.update_submission(
            candidate["id"],
            status="submitted",
            platform_status=payload.get("status"),
        )
        ledger.set_candidate_status(candidate["id"], "submitted")
        print(f"平台尚未返回 dateSubmitted，保留 submitted：{candidate['label']}")
    return {"candidate_id": candidate["id"], "date_submitted": date_submitted, "status": payload.get("status")}


def submit_candidate(
    ledger: Ledger,
    client: BrainClient,
    candidate_key: str,
    approval_hash: str,
    dry_run: bool = False,
    *,
    batch_id: str | None = None,
) -> dict:
    candidate = resolve_candidate(ledger, candidate_key, batch_id=batch_id)
    if not candidate:
        raise ValueError("候选不存在")
    submission = ledger.get_submission(candidate["id"])
    if not submission:
        raise ValueError("没有提交队列记录，先运行 gate")
    _check_approval(ledger, candidate, submission, approval_hash)
    _check_gates(ledger, candidate["id"])

    gates = config.load_gates()
    daily_limit = int(gates.get("g7", {}).get("daily_submit_limit", 2))
    submitted_today = ledger.daily_submit_count(today_utc())
    if submitted_today >= daily_limit:
        raise ValueError(f"今日已提交 {submitted_today}/{daily_limit}，不能再提交")

    alpha = ledger.alpha_for_candidate(candidate["id"])
    if not alpha:
        raise ValueError("候选没有 alpha")
    payload = client.get_alpha(alpha["alpha_id"])
    checks = (payload.get("is") or {}).get("checks") or []
    fails = [item.get("name") for item in checks if str(item.get("result", "")).upper() == "FAIL"]
    if fails:
        ledger.update_submission(candidate["id"], status="rejected", note=f"checks failed: {fails}")
        ledger.set_candidate_status(candidate["id"], "rejected_gate")
        raise ValueError(f"提交前复查失败: {fails}")

    if dry_run:
        print(f"[dry-run] 将提交 {candidate['label']} ({alpha['alpha_id']})")
        print(f"表达式: {candidate['expression']}")
        print(f"S={alpha.get('sharpe')} F={alpha.get('fitness')} T={alpha.get('turnover')}")
        print(f"approval_hash={approval_hash}")
        return {"dry_run": True, "candidate_id": candidate["id"], "alpha_id": alpha["alpha_id"]}

    result = client.submit_alpha(alpha["alpha_id"])
    ledger.update_submission(
        candidate["id"],
        status="submitted",
        submitted_at=utcnow(),
        platform_status="SUBMITTED",
        note=json.dumps(result, ensure_ascii=False)[:500],
    )
    ledger.set_candidate_status(candidate["id"], "submitted")
    ledger.quota_add(today_utc(), "submit")
    ledger.log(
        "human",
        candidate["id"],
        "submit",
        {"alpha_id": alpha["alpha_id"], "response": result},
    )
    print(f"已提交 {candidate['label']} ({alpha['alpha_id']})")
    return verify_submission(ledger, client, candidate["id"])
