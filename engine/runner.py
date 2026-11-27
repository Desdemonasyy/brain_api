"""批量回测 runner：并发槽、限速、错误分类、断点续跑。

槽位 = worker 数，一个 worker 持有一个平台模拟名额直到轮询结束。
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from .client import (
    AmbiguousSubmit,
    AuthError,
    BrainClient,
    ConcurrencyLimit,
    SimulationFailed,
    SimulationRejected,
    SimulationTimeout,
)
from .ledger import Ledger, today_utc


def _fetch_alpha(client: BrainClient, alpha_id: str, attempts: int = 5) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return client.get_alpha(alpha_id)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"拉取 alpha {alpha_id} 失败: {last_error}")


def _record_summary(ledger: Ledger, candidate: dict, status: str, message: str = "", **extra) -> dict:
    summary = {
        "candidate_id": candidate["id"],
        "label": candidate.get("label", ""),
        "status": status,
        "message": message,
    }
    summary.update(extra)
    ledger.log("runner", candidate["id"], f"sim_{status}", summary)
    return summary


def _poll_and_record(
    client: BrainClient,
    ledger: Ledger,
    sim_row_id: int,
    sim_id: str,
    candidate: dict,
    timeout: int,
    poll_interval: float,
) -> dict:
    try:
        data = client.wait_simulation(sim_id, timeout=timeout, interval=poll_interval)
    except SimulationFailed as exc:
        ledger.finish_simulation(sim_row_id, "error", str(exc))
        ledger.set_candidate_status(candidate["id"], "sim_error")
        print(f"  ERROR {candidate['label']:24s} {str(exc)[:180]}", flush=True)
        return _record_summary(ledger, candidate, "error", str(exc))
    except SimulationTimeout as exc:
        # 模拟可能仍在跑，保留 simulating，下一次 run 会按 sim_id 续跑
        ledger.log("runner", candidate["id"], "sim_timeout", {"sim_id": sim_id})
        print(f"  TIMEOUT {candidate['label']:22s} {sim_id}", flush=True)
        return _record_summary(ledger, candidate, "timeout", str(exc), sim_id=sim_id)

    alpha_id = data.get("alpha")
    if not alpha_id:
        ledger.finish_simulation(sim_row_id, "error", "COMPLETE 但无 alpha 字段")
        ledger.set_candidate_status(candidate["id"], "sim_error")
        return _record_summary(ledger, candidate, "error", "COMPLETE 但无 alpha 字段")

    ledger.finish_simulation(sim_row_id, "complete", alpha_id=alpha_id)
    try:
        payload = _fetch_alpha(client, alpha_id)
    except RuntimeError as exc:
        ledger.set_candidate_status(candidate["id"], "sim_error")
        print(f"  ERROR {candidate['label']:24s} {str(exc)[:180]}", flush=True)
        return _record_summary(ledger, candidate, "error", str(exc), alpha_id=alpha_id)

    ledger.record_alpha(candidate["id"], payload)
    ledger.set_candidate_status(candidate["id"], "simulated")
    stats = payload.get("is") or {}
    sharpe = stats.get("sharpe")
    fitness = stats.get("fitness")
    sh = f"{sharpe:.2f}" if isinstance(sharpe, (int, float)) else "-"
    ft = f"{fitness:.2f}" if isinstance(fitness, (int, float)) else "-"
    print(f"  OK    {candidate['label']:24s} S={sh} F={ft} {alpha_id}", flush=True)
    return _record_summary(
        ledger,
        candidate,
        "simulated",
        alpha_id=alpha_id,
        sim_id=sim_id,
        sharpe=sharpe,
        fitness=fitness,
    )


def _process_claimed(
    client: BrainClient,
    ledger: Ledger,
    task: tuple[dict, int],
    timeout: int,
    poll_interval: float,
) -> dict:
    candidate, sim_row_id = task
    settings = json.loads(candidate["settings_json"])
    ledger.mark_submitting(sim_row_id)
    try:
        sim_id, retry_after = client.simulate(candidate["expression"], settings)
    except AuthError:
        ledger.finish_simulation(sim_row_id, "abandoned", "auth")
        ledger.set_candidate_status(candidate["id"], "prechecked")
        raise
    except ConcurrencyLimit as exc:
        # 429 并发槽满：释放本轮占用，等待后重新排队，不标记失败
        ledger.release_simulation(sim_row_id)
        ledger.set_candidate_status(candidate["id"], "prechecked")
        wait = min(max(exc.retry_after, 10.0), 120.0)
        print(
            f"  WAIT  {candidate['label']:23s} 并发槽满，{wait:.0f}s 后重试",
            flush=True,
        )
        time.sleep(wait)
        return _record_summary(ledger, candidate, "concurrency_wait", str(exc))
    except SimulationRejected as exc:
        ledger.finish_simulation(sim_row_id, "error", str(exc))
        ledger.set_candidate_status(candidate["id"], "sim_error")
        print(f"  REJECT {candidate['label']:23s} {str(exc)[:160]}", flush=True)
        return _record_summary(ledger, candidate, "rejected", str(exc))
    except AmbiguousSubmit as exc:
        # 请求可能已到达平台，不能盲目重投
        ledger.finish_simulation(sim_row_id, "unknown", str(exc))
        ledger.set_candidate_status(candidate["id"], "unknown")
        print(f"  UNKNOWN {candidate['label']:22s} {str(exc)[:160]}", flush=True)
        return _record_summary(ledger, candidate, "unknown", str(exc))
    except requests.RequestException as exc:
        ledger.finish_simulation(sim_row_id, "abandoned", str(exc))
        ledger.set_candidate_status(candidate["id"], "prechecked")
        print(f"  NETERR {candidate['label']:23s} {str(exc)[:160]}", flush=True)
        return _record_summary(ledger, candidate, "network_error", str(exc))

    ledger.attach_sim_id(sim_row_id, sim_id, retry_after)
    ledger.quota_add(today_utc(), "sim")
    time.sleep(min(max(retry_after, 0.0), poll_interval))
    try:
        return _poll_and_record(
            client, ledger, sim_row_id, sim_id, candidate, timeout, poll_interval
        )
    except AuthError:
        ledger.log("runner", candidate["id"], "auth_expired_during_poll", {"sim_id": sim_id})
        raise
    except requests.RequestException as exc:
        # 已拿到 sim_id，保留 simulating，下次续跑
        ledger.log("runner", candidate["id"], "sim_network_error", {"sim_id": sim_id, "error": str(exc)})
        print(f"  NETERR {candidate['label']:23s} {str(exc)[:160]}", flush=True)
        return _record_summary(ledger, candidate, "network_error", str(exc), sim_id=sim_id)


def _resume_record(
    client: BrainClient,
    ledger: Ledger,
    record: dict,
    timeout: int,
    poll_interval: float,
) -> dict:
    candidate = ledger.get_candidate(record["candidate_id"])
    if not candidate:
        return {"candidate_id": record["candidate_id"], "status": "missing"}
    if record.get("alpha_id"):
        payload = _fetch_alpha(client, record["alpha_id"])
        ledger.record_alpha(candidate["id"], payload)
        ledger.set_candidate_status(candidate["id"], "simulated")
        print(f"  RESUME {candidate['label']:23s} alpha={record['alpha_id']}", flush=True)
        return _record_summary(ledger, candidate, "simulated", alpha_id=record["alpha_id"])
    print(f"  RESUME {candidate['label']:23s} sim={record['sim_id']}", flush=True)
    return _poll_and_record(
        client, ledger, record["sim_row_id"], record["sim_id"], candidate, timeout, poll_interval
    )


def run_batch(
    ledger: Ledger,
    client: BrainClient,
    batch_id: str | None = None,
    workers: int = 2,
    limit: int | None = None,
    timeout: int = 900,
    poll_interval: float = 8.0,
    max_sims: int | None = None,
    dry_run: bool = False,
) -> dict:
    if dry_run:
        claimable = ledger.count_claimable(batch_id)
        print(f"batch={batch_id or '*'} 可回测 {claimable} 条")
        for item in ledger.list_candidates(batch_id, ["prechecked"], limit=10):
            print(f"  {item['label']:24s} {item['region']}/{item['universe']}")
        return {"claimable": claimable, "inflight": 0, "dry_run": True}

    if not client.authenticated():
        raise AuthError("cookie 无效或已过期，先运行: python -m engine.cli login")

    inflight = ledger.recover_inflight()
    if inflight:
        print(f"发现 {len(inflight)} 条可续跑的模拟", flush=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total = ledger.count_claimable(batch_id)
    ledger.create_run(run_id, batch_id, total)
    print(f"run_id={run_id} batch={batch_id or '*'} 待跑={total} workers={workers}", flush=True)

    stop = threading.Event()
    counter_lock = threading.Lock()
    claimed = 0
    results: list[dict] = []
    errors: list[str] = []

    def reserve_one() -> bool:
        nonlocal claimed
        with counter_lock:
            if limit is not None and claimed >= limit:
                return False
            if max_sims is not None and ledger.quota_get(today_utc(), "sim") >= max_sims:
                print("达到 max_sims 上限，停止", flush=True)
                stop.set()
                return False
            claimed += 1
            return True

    def worker() -> None:
        nonlocal claimed
        while not stop.is_set():
            if not reserve_one():
                return
            task = ledger.claim_next(batch_id, run_id)
            if task is None:
                with counter_lock:
                    claimed -= 1
                return
            try:
                summary = _process_claimed(client, ledger, task, timeout, poll_interval)
                results.append(summary)
            except AuthError as exc:
                stop.set()
                errors.append(str(exc))
                print(f"认证失效，停止调度: {exc}", flush=True)
                return
            except Exception as exc:  # noqa: BLE001
                candidate, sim_row_id = task
                ledger.finish_simulation(sim_row_id, "error", str(exc))
                ledger.set_candidate_status(candidate["id"], "sim_error")
                errors.append(str(exc))
                print(f"  ERROR {candidate['label']:24s} {str(exc)[:180]}", flush=True)

    if inflight:
        # 轮询不占平台并发槽，所有在途模拟都应恢复，避免遗留 simulating
        with ThreadPoolExecutor(max_workers=min(len(inflight), 8)) as pool:
            futures = [
                pool.submit(_resume_record, client, ledger, record, timeout, poll_interval)
                for record in inflight
            ]
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except AuthError as exc:
                    stop.set()
                    errors.append(str(exc))
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))

    if not stop.is_set():
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(worker) for _ in range(max(1, workers))]
            for future in as_completed(futures):
                future.result()

    simulated = sum(1 for item in results if item.get("status") == "simulated")
    failed = len(results) - simulated
    status = "auth_error" if any("cookie" in error or "失效" in error for error in errors) else "done"
    ledger.finish_run(run_id, status, simulated, note=f"failed={failed} errors={errors[:3]}")
    print(
        f"\n回测完成：成功 {simulated} / 失败或待续 {failed} / 本轮认领 {claimed}"
        + (f" / 错误 {len(errors)}" if errors else "")
    )
    return {
        "run_id": run_id,
        "claimed": claimed,
        "simulated": simulated,
        "failed": failed,
        "errors": errors,
    }
