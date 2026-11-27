"""Orchestrator：按顺序跑预检/回测/审计/相关性/闸门，并生成日报。

不包含 submit；提交必须人工 approve + submit。
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import audit, corr, family, gate, precheck, report, runner
from .client import BrainClient
from .ledger import Ledger

TZ = ZoneInfo("Asia/Shanghai")


def run_cycle(
    ledger: Ledger,
    client: BrainClient,
    batch_id: str | None = None,
    workers: int = 2,
    limit: int | None = None,
) -> dict:
    print("\n=== G1 预检 ===")
    precheck.precheck_batch(ledger, batch_id=batch_id)
    print("\n=== 批量回测 ===")
    run_result = runner.run_batch(ledger, client, batch_id=batch_id, workers=workers, limit=limit)
    print("\n=== G2–G5 审计 ===")
    audit.audit_batch(ledger, client, batch_id=batch_id)
    print("\n=== PnL 同步 ===")
    corr.sync_pnl(ledger, client, batch_id=batch_id)
    print("\n=== 家族聚类 ===")
    family.cluster_batch(ledger, client, batch_id=batch_id, sync=False)
    print("\n=== G6 相关性 ===")
    corr.check_batch(ledger, client, batch_id=batch_id, sync=False)
    print("\n=== G7 队列 ===")
    gate_result = gate.gate_batch(ledger, batch_id=batch_id)
    print("\n=== 日报 ===")
    path = report.write_daily_report(ledger, batch_id=batch_id)
    return {"run": run_result, "gate": gate_result, "report": str(path)}


def daemon(ledger: Ledger, client: BrainClient, batch_id: str | None, workers: int) -> None:
    ran_cycle = None
    reported = None
    print("Orchestrator 已启动（北京时区）；09:05 跑管线，16:05 出日报。Ctrl+C 退出。")
    while True:
        now = datetime.now(TZ)
        today = now.date()
        if 9 <= now.hour < 16 and ran_cycle != today:
            print(f"\n[{now.isoformat(timespec='minutes')}] 开始每日管线")
            run_cycle(ledger, client, batch_id=batch_id, workers=workers)
            ran_cycle = today
        if now.hour >= 16 and reported != today:
            print(f"\n[{now.isoformat(timespec='minutes')}] 生成结算日报")
            report.write_daily_report(ledger, batch_id=batch_id)
            reported = today
        time.sleep(60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BRAIN alpha orchestrator")
    parser.add_argument("--batch", default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--once", action="store_true", help="跑一轮完整管线")
    parser.add_argument("--daemon", action="store_true", help="常驻，09:05 跑管线 / 16:05 出日报")
    parser.add_argument("--report-only", action="store_true", help="只生成日报")
    args = parser.parse_args(argv)

    ledger = Ledger()
    ledger.init()
    if args.report_only:
        report.write_daily_report(ledger, batch_id=args.batch)
        return 0
    client = BrainClient()
    if not client.authenticated():
        print("cookie 无效，先 python -m engine.cli login")
        return 2
    if args.daemon:
        daemon(ledger, client, args.batch, args.workers)
        return 0
    result = run_cycle(ledger, client, batch_id=args.batch, workers=args.workers, limit=args.limit)
    print("\n完成:", json_summary(result))
    return 0


def json_summary(result: dict) -> str:
    import json

    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
