"""命令行入口：

python -m engine.cli init
python -m engine.cli login
python -m engine.cli load candidates.json --batch legs39 --hypothesis H39
python -m engine.cli export-legs _legs38.py --var BSERIES --batch legs38 --hypothesis H38
python -m engine.cli precheck --batch legs38
python -m engine.cli run --batch legs38 --workers 3
python -m engine.cli audit --batch legs38
python -m engine.cli backfill-submitted --pages 3
python -m engine.cli status --batch legs38
python -m engine.cli show <candidate_id>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from . import config, corr, family, gate, miner, precheck, queue, report
from .audit import audit_batch
from .client import AuthError, BrainClient
from .ledger import Ledger, make_family_key
from .runner import run_batch


def _insert_items(
    ledger: Ledger,
    items: list[dict],
    batch_id: str,
    hypothesis_id: str,
    defaults: dict | None = None,
) -> dict:
    added = 0
    skipped = 0
    for index, item in enumerate(items):
        expression = item.get("expression") or item.get("code")
        label = item.get("label") or item.get("name") or f"{batch_id}_{index + 1}"
        if not expression:
            print(f"  SKIP {label}: 缺少 expression")
            skipped += 1
            continue
        settings = dict(config.BASE_SETTINGS)
        settings.update(defaults or {})
        settings.update(item.get("settings") or {})
        fields = precheck.extract_fields(expression)
        operators = precheck.extract_operators(expression)
        family_key = make_family_key(
            fields, operators, str(settings.get("neutralization", ""))
        )
        candidate, created = ledger.add_candidate(
            expression=expression,
            settings=settings,
            family_key=family_key,
            hypothesis_id=hypothesis_id,
            label=label,
            batch_id=batch_id,
            priority=float(item.get("priority", 0.0)),
        )
        if created:
            added += 1
        else:
            skipped += 1
            if candidate["status"] != "draft":
                print(f"  DUP  {label}: 已存在且状态为 {candidate['status']}")
    print(f"导入完成：新增 {added} / 跳过 {skipped} / 总计 {len(items)}")
    return {"added": added, "skipped": skipped, "total": len(items)}


def cmd_load(args, ledger: Ledger) -> None:
    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    payload = miner.validate_plan(json.loads(raw))
    items = payload.get("items") or []
    batch_id = args.batch or payload.get("batch") or "default"
    hypothesis = args.hypothesis or payload.get("hypothesis") or "imported"
    defaults = payload.get("defaults") or {}
    _insert_items(ledger, items, batch_id, hypothesis, defaults)


def cmd_validate(args) -> None:
    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    payload = miner.validate_plan(json.loads(raw))
    print(
        f"schema OK: batch={payload.get('batch')} hypothesis={payload.get('hypothesis')} "
        f"items={len(payload.get('items') or [])}"
    )


def cmd_export_legs(args, ledger: Ledger) -> None:
    script_path = Path(args.script).resolve()
    if not script_path.exists():
        raise SystemExit(f"脚本不存在: {script_path}")
    sys.path.insert(0, str(config.ROOT))
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    series = getattr(module, args.var)
    base = dict(getattr(module, "BASE", {}) or {})
    items: list[dict] = []
    for row in series:
        if isinstance(row, dict):
            expression = row.get("expression") or row.get("code")
            overrides = row.get("settings") or {}
            label = row.get("label") or row.get("name")
        else:
            label, expression, overrides = row[0], row[1], (row[2] if len(row) > 2 else {})
            overrides = overrides or {}
        settings = dict(overrides)
        items.append({"label": label, "expression": expression, "settings": settings})
    print(f"从 {script_path.name}:{args.var} 读取 {len(items)} 条候选，BASE={base}")
    _insert_items(ledger, items, args.batch, args.hypothesis, base)


def cmd_precheck(args, ledger: Ledger) -> None:
    precheck.precheck_batch(ledger, batch_id=args.batch, allow_unknown=args.allow_unknown)


def cmd_run(args, ledger: Ledger) -> None:
    client = BrainClient()
    run_batch(
        ledger,
        client,
        batch_id=args.batch,
        workers=args.workers,
        limit=args.limit,
        timeout=args.timeout,
        poll_interval=args.poll,
        max_sims=args.max_sims,
        dry_run=args.dry_run,
    )


def cmd_audit(args, ledger: Ledger) -> None:
    client = BrainClient()
    audit_batch(ledger, client, batch_id=args.batch, limit=args.limit, force=args.force)


def cmd_corr(args, ledger: Ledger) -> None:
    if args.corr_command == "set-prod":
        result = corr.set_prod_corr(ledger, args.candidate, args.value, args.note)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    client = BrainClient()
    if args.corr_command == "sync":
        corr.sync_pnl(ledger, client, batch_id=args.batch, force=args.force)
    elif args.corr_command == "check":
        corr.check_batch(ledger, client, batch_id=args.batch, limit=args.limit)


def cmd_family(args, ledger: Ledger) -> None:
    client = None if args.no_sync else BrainClient()
    family.cluster_batch(
        ledger,
        client,
        batch_id=args.batch,
        threshold=args.threshold,
        sync=not args.no_sync,
    )


def cmd_gate(args, ledger: Ledger) -> None:
    gate.gate_batch(ledger, batch_id=args.batch, limit=args.limit)


def cmd_queue(args, ledger: Ledger) -> None:
    queue.show_queue(ledger, batch_id=args.batch, include_done=args.all)


def cmd_approve(args, ledger: Ledger) -> None:
    queue.approve(ledger, args.candidate, args.by, batch_id=args.batch)


def cmd_submit(args, ledger: Ledger) -> None:
    client = BrainClient()
    queue.submit_candidate(
        ledger,
        client,
        args.candidate,
        args.hash,
        dry_run=args.dry_run,
        batch_id=args.batch,
    )


def cmd_verify(args, ledger: Ledger) -> None:
    client = BrainClient()
    queue.verify_submission(ledger, client, args.candidate, batch_id=args.batch)


def cmd_report(args, ledger: Ledger) -> None:
    report.write_daily_report(ledger, batch_id=args.batch, day=args.date)


def cmd_backfill(args, ledger: Ledger) -> None:
    client = BrainClient()
    total = 0
    for page in range(args.pages):
        alphas = client.list_user_alphas(limit=50, offset=page * 50)
        if not alphas:
            break
        for summary in alphas:
            if not summary.get("dateSubmitted"):
                continue
            alpha_id = summary.get("id")
            try:
                detail = client.get_alpha(alpha_id)
            except Exception as exc:  # noqa: BLE001
                print(f"  SKIP {alpha_id}: {exc}")
                continue
            regular = detail.get("regular") or {}
            expression = regular.get("code") or ""
            settings = detail.get("settings") or summary.get("settings") or {}
            if not expression:
                expression = f"backfill:{alpha_id}"
                settings = {}
            fields = precheck.extract_fields(expression)
            operators = precheck.extract_operators(expression)
            family_key = make_family_key(
                fields, operators, str(settings.get("neutralization", ""))
            )
            candidate, created = ledger.add_candidate(
                expression=expression,
                settings=settings,
                family_key=family_key,
                hypothesis_id="backfill",
                label=summary.get("name") or alpha_id[:8],
                batch_id="submitted",
                priority=1.0,
                status="verified",
            )
            if not created and candidate["status"] in ("draft", "precheck_failed", "prechecked"):
                ledger.set_candidate_status(candidate["id"], "verified")
            yearly = client.get_yearly_stats(alpha_id) if args.yearly else None
            ledger.record_alpha(candidate["id"], detail, yearly=yearly)
            total += 1
            action = "NEW" if created else "EXIST"
            print(f"  {action} {alpha_id} {summary.get('name') or ''} {candidate['label']}")
    print(f"\n回灌完成：{total} 条已提交 alpha")


def cmd_status(args, ledger: Ledger) -> None:
    counts = ledger.status_counts(args.batch)
    print(f"状态统计（batch={args.batch or '*'}）")
    if not counts:
        print("  台账为空")
        return
    for status, count in sorted(counts.items()):
        print(f"  {status:18s} {count}")
    total = sum(counts.values())
    print(f"  {'TOTAL':18s} {total}")


def cmd_list(args, ledger: Ledger) -> None:
    rows = ledger.list_candidates(args.batch, [args.status] if args.status else None, args.limit)
    print(f"{'label':26s} {'status':16s} region/universe        hypothesis")
    for row in rows:
        print(
            f"{row['label'][:26]:26s} {row['status']:16s} "
            f"{row['region']}/{row['universe']:<18s} {row['hypothesis_id']}"
        )
    print(f"共 {len(rows)} 条")


def _resolve_candidate(ledger: Ledger, key: str) -> dict | None:
    candidate = ledger.get_candidate(key)
    if candidate:
        return candidate
    for row in ledger.list_candidates(limit=None):
        if row["label"] == key or row["id"].startswith(key):
            return row
    return None


def cmd_requeue(args, ledger: Ledger) -> None:
    candidate = _resolve_candidate(ledger, args.candidate_id)
    if not candidate:
        print("未找到候选")
        return
    alive = ledger.alive_sim(candidate["id"])
    if alive:
        print(f"候选仍有进行中的模拟 {alive['sim_id'] or alive['status']}，不能重置")
        return
    if candidate["status"] in ("draft", "prechecked"):
        print(f"状态已是 {candidate['status']}，无需重置")
        return
    ledger.log("cli", candidate["id"], "requeue", {"from": candidate["status"]})
    ledger.set_candidate_status(candidate["id"], "prechecked")
    print(f"{candidate['label']} 已从 {candidate['status']} 重置为 prechecked")


def cmd_show(args, ledger: Ledger) -> None:
    candidate = _resolve_candidate(ledger, args.candidate_id)
    if not candidate:
        print("未找到候选")
        return
    print(f"candidate: {candidate['id']}")
    print(f"label    : {candidate['label']}")
    print(f"batch    : {candidate['batch_id']}")
    print(f"status   : {candidate['status']}")
    print(f"region   : {candidate['region']}/{candidate['universe']} delay={candidate['delay']}")
    print(f"priority : {candidate['priority']}")
    print(f"settings : {candidate['settings_json']}")
    print(f"expression:\n  {candidate['expression']}")
    alpha = ledger.alpha_for_candidate(candidate["id"])
    if alpha:
        print(
            f"alpha    : {alpha['alpha_id']} S={alpha['sharpe']} F={alpha['fitness']} "
            f"T={alpha['turnover']} returns={alpha['returns']} margin={alpha['margin']} "
            f"grade={alpha['grade']} submitted={alpha['date_submitted']}"
        )
    gates = ledger.get_gates(candidate["id"])
    if gates:
        print("gates:")
        for gate in gates:
            detail = gate["detail"]
            try:
                detail = json.dumps(json.loads(detail), ensure_ascii=False)
            except (TypeError, ValueError):
                pass
            print(f"  {gate['gate']:20s} {gate['result']:8s} value={gate['value']} limit={gate['limit_value']}")
            if detail:
                print(f"    {str(detail)[:1200]}")


OPS_INDEX_PATH = Path(__file__).resolve().parents[1] / "docs" / "operators_index.json"
DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs" / "worldquantAlpha-dev"
STATE_DIR = Path(__file__).resolve().parents[1] / ".state"


def cmd_docs(args: argparse.Namespace) -> None:
    if not DOCS_ROOT.exists():
        print(f"缺少本地文档库: {DOCS_ROOT}")
        print("先运行 docs 下载脚本，或检查目录是否被移动")
        return
    files = sorted(DOCS_ROOT.rglob("*.md"))
    query = (args.query or "").strip().lower()
    if not query:
        if args.json:
            print(json.dumps([str(p.relative_to(DOCS_ROOT)) for p in files], ensure_ascii=False, indent=2))
            return
        print(f"本地 WorldQuant 文档库: {DOCS_ROOT}（{len(files)} 个）")
        for path in files:
            print(f"  {path.relative_to(DOCS_ROOT)}")
        print("\n搜索: python -m engine.cli docs <关键词>")
        return

    hits = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        low = text.lower()
        if query in path.name.lower() or query in low:
            index = low.find(query)
            snippet = text[max(0, index - 80): index + 200].replace("\n", " ")
            hits.append({"path": str(path.relative_to(DOCS_ROOT)), "snippet": snippet})
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return
    for hit in hits[:20]:
        print(f"\n[{hit['path']}]")
        print(f"  ...{hit['snippet']}...")
    if not hits:
        print("没有匹配的文档。试试 运算符 / 数据字段 / 提交标准 / API")


def _as_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def cmd_data(args: argparse.Namespace) -> None:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(STATE_DIR.glob("fields_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            items = []
            for key, value in data.items():
                if isinstance(value, dict):
                    value.setdefault("id", key)
                    items.append(value)
        elif isinstance(data, list):
            items = data
        else:
            continue
        for field in items:
            if not isinstance(field, dict):
                continue
            field_id = field.get("id")
            dataset = field.get("dataset") or {}
            dataset_id = dataset.get("id") or ""
            if not field_id:
                continue
            key = (dataset_id, field_id)
            if key in seen:
                continue
            seen.add(key)
            category = field.get("category") or {}
            rows.append(
                {
                    "id": field_id,
                    "type": str(field.get("type") or ""),
                    "coverage": _as_float(field.get("coverage")),
                    "dataset": dataset_id,
                    "dataset_name": dataset.get("name") or "",
                    "category": category.get("name") if isinstance(category, dict) else str(category),
                    "description": str(field.get("description") or ""),
                }
            )

    if not rows:
        print(f"没有本地字段缓存: {STATE_DIR}/fields_*.json")
        print("先通过 BRAIN API 拉取 /data-fields 并缓存，或直接看平台 Data Explorer")
        return

    query = (args.query or "").strip().lower()
    dataset_filter = (args.dataset or "").strip().lower()
    type_filter = (args.type or "").strip().upper()
    min_coverage = float(args.min_coverage or 0.0)

    if not query and not dataset_filter and not type_filter and min_coverage <= 0:
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            groups.setdefault((row["dataset"], row["dataset_name"]), []).append(row)
        if args.json:
            summary = [
                {
                    "dataset": key[0],
                    "name": key[1],
                    "fields": len(items),
                    "max_coverage": max((x["coverage"] for x in items if x["coverage"] is not None), default=None),
                }
                for key, items in groups.items()
            ]
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        print(f"本地字段缓存: {len(rows)} 个字段 / {len(groups)} 个数据集")
        for (dataset_id, name), items in sorted(groups.items()):
            coverages = [x["coverage"] for x in items if x["coverage"] is not None]
            max_cov = max(coverages) if coverages else None
            print(
                f"  {dataset_id:24s} {name[:38]:38s} fields={len(items):4d} "
                f"max_cov={'-' if max_cov is None else f'{max_cov:.2f}'}"
            )
        print("\n搜索: python -m engine.cli data <关键词> [--dataset model16] [--type MATRIX] [--min-coverage 0.8]")
        return

    filtered = []
    for row in rows:
        if dataset_filter and dataset_filter not in row["dataset"].lower() and dataset_filter not in row["dataset_name"].lower():
            continue
        if type_filter and type_filter != row["type"].upper():
            continue
        if row["coverage"] is not None and row["coverage"] < min_coverage:
            continue
        if min_coverage > 0 and row["coverage"] is None:
            continue
        if query:
            haystack = " ".join(
                [row["id"], row["description"], row["dataset"], row["dataset_name"], str(row["category"])]
            ).lower()
            if query not in haystack:
                continue
        filtered.append(row)

    filtered.sort(key=lambda x: (x["coverage"] is not None, x["coverage"] or 0), reverse=True)
    filtered = filtered[: args.limit]
    if args.json:
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
        return
    for row in filtered:
        coverage = "-" if row["coverage"] is None else f"{row['coverage']:.2f}"
        print(
            f"{row['dataset']:14s} {row['id']:42s} {row['type']:8s} cov={coverage:>5s} | "
            f"{row['description'][:90]}"
        )
    if not filtered:
        print("没有匹配字段。放宽关键词或降低 --min-coverage")


def cmd_ops(args: argparse.Namespace) -> None:
    path = OPS_INDEX_PATH
    if not path.exists():
        print(f"缺少算子索引: {path}")
        print("先运行 docs/operators_reference.md 的解析脚本，或检查文件是否被移动")
        return
    index = json.loads(path.read_text(encoding="utf-8"))
    items = list(index.get("operators", []))
    query = (args.query or "").strip().lower()
    category = (args.category or "").strip().lower()
    category = {
        "时序": "时间序列",
        "ts": "time series",
        "截面": "截面",
        "cross": "cross sectional",
        "组": "组别",
        "group": "group",
        "算术": "算术",
        "逻辑": "逻辑",
        "向量": "向量",
        "变换": "变换",
    }.get(category, category)

    if category:
        items = [
            item for item in items
            if category in (item.get("category") or "").lower()
            or category in (item.get("category_en") or "").lower()
        ]
    if query:
        items = [
            item for item in items
            if query in (item.get("name") or "").lower()
            or query in (item.get("syntax") or "").lower()
            or query in (item.get("description") or "").lower()
        ]

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    if not query and not category:
        print(f"运算符手册: {index.get('count')} 个")
        print(f"来源: {index.get('source')}")
        for cat in index.get("categories", []):
            print(f"  {cat['name']}（{cat['en']}）: {cat['count']} 个")
        print("\n用法: python -m engine.cli ops <关键词> [--category 时序] [--json]")
        print("示例: python -m engine.cli ops regression")
        return

    for item in items[:30]:
        print(f"[{item.get('category')}] {item.get('name')}")
        print(f"  {item.get('syntax')}")
        print(f"  {item.get('description')}")
    if len(items) > 30:
        print(f"\n... 还有 {len(items) - 30} 条，请缩小关键词")

    for item in index.get("platform_forbidden", []):
        if query and query in (item.get("name") or "").lower():
            print(f"[平台禁用] {item['name']}: {item['reason']}")

    if not items and not any(query in (item.get("name") or "").lower() for item in index.get("platform_forbidden", [])):
        print("没有匹配的运算符。试试 rank / ts_ / group_ / trade_when / vec_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine.cli", description="BRAIN alpha 管线")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="初始化 SQLite 台账")
    sub.add_parser("login", help="登录 BRAIN 并保存 cookie")

    p_load = sub.add_parser("load", help="从 JSON 导入候选")
    p_load.add_argument("path", help="JSON 文件路径，或 - 从 stdin 读取")
    p_load.add_argument("--batch", default=None)
    p_load.add_argument("--hypothesis", default=None)

    p_export = sub.add_parser("export-legs", help="把现有 _legs*.py 的系列导入候选池")
    p_export.add_argument("script")
    p_export.add_argument("--var", default="BSERIES")
    p_export.add_argument("--batch", required=True)
    p_export.add_argument("--hypothesis", required=True)

    p_pre = sub.add_parser("precheck", help="G1 预检")
    p_pre.add_argument("--batch", default=None)
    p_pre.add_argument("--allow-unknown", action="store_true", help="未知字段/算子只告警")

    p_run = sub.add_parser("run", help="批量回测")
    p_run.add_argument("--batch", default=None)
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--max-sims", type=int, default=None)
    p_run.add_argument("--timeout", type=int, default=900)
    p_run.add_argument("--poll", type=float, default=8.0)
    p_run.add_argument("--dry-run", action="store_true")

    p_audit = sub.add_parser("audit", help="G2–G5 审计")
    p_audit.add_argument("--batch", default=None)
    p_audit.add_argument("--limit", type=int, default=None)
    p_audit.add_argument("--force", action="store_true", help="重审已审计/被拒候选")

    p_validate = sub.add_parser("validate", help="校验挖掘 agent 产出的候选 JSON")
    p_validate.add_argument("path", help="JSON 文件路径，或 - 从 stdin 读取")

    p_corr = sub.add_parser("corr", help="G6 相关性与 PnL")
    corr_sub = p_corr.add_subparsers(dest="corr_command", required=True)
    p_corr_sync = corr_sub.add_parser("sync", help="同步 PnL")
    p_corr_sync.add_argument("--batch", default=None)
    p_corr_sync.add_argument("--force", action="store_true")
    p_corr_check = corr_sub.add_parser("check", help="跑 G6")
    p_corr_check.add_argument("--batch", default=None)
    p_corr_check.add_argument("--limit", type=int, default=None)
    p_corr_set = corr_sub.add_parser("set-prod", help="人工写回 prod correlation")
    p_corr_set.add_argument("candidate")
    p_corr_set.add_argument("value", type=float)
    p_corr_set.add_argument("--note", default="")

    p_family = sub.add_parser("family", help="家族聚类")
    family_sub = p_family.add_subparsers(dest="family_command", required=True)
    p_family_cluster = family_sub.add_parser("cluster")
    p_family_cluster.add_argument("--batch", default=None)
    p_family_cluster.add_argument("--threshold", type=float, default=0.95)
    p_family_cluster.add_argument("--no-sync", action="store_true")

    p_gate = sub.add_parser("gate", help="G7 排队")
    p_gate.add_argument("--batch", default=None)
    p_gate.add_argument("--limit", type=int, default=None)

    p_queue = sub.add_parser("queue", help="查看提交队列")
    p_queue.add_argument("--batch", default=None)
    p_queue.add_argument("--all", action="store_true", help="包含已提交/已验证")

    p_approve = sub.add_parser("approve", help="人工批准一条候选")
    p_approve.add_argument("candidate")
    p_approve.add_argument("--by", default="human")
    p_approve.add_argument("--batch", default=None, help="按 batch 限定 label 查找，解决同名冲突")

    p_submit = sub.add_parser("submit", help="人工提交（必须带 approval hash）")
    p_submit.add_argument("candidate")
    p_submit.add_argument("--hash", required=True)
    p_submit.add_argument("--dry-run", action="store_true")
    p_submit.add_argument("--batch", default=None, help="按 batch 限定")

    p_verify = sub.add_parser("verify", help="回查提交状态")
    p_verify.add_argument("candidate")
    p_verify.add_argument("--batch", default=None, help="按 batch 限定")

    p_report = sub.add_parser("report", help="生成每日报告")
    p_report.add_argument("--batch", default=None)
    p_report.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天（UTC）")

    p_backfill = sub.add_parser("backfill-submitted", help="回灌已提交 alpha 作为基准池")
    p_backfill.add_argument("--pages", type=int, default=1)
    p_backfill.add_argument("--yearly", action="store_true")

    p_status = sub.add_parser("status", help="状态统计")
    p_status.add_argument("--batch", default=None)

    p_list = sub.add_parser("list", help="列出候选")
    p_list.add_argument("--batch", default=None)
    p_list.add_argument("--status", default=None)
    p_list.add_argument("--limit", type=int, default=50)

    p_show = sub.add_parser("show", help="查看候选详情")
    p_show.add_argument("candidate_id")

    p_ops = sub.add_parser("ops", help="搜索 BRAIN 运算符手册")
    p_ops.add_argument("query", nargs="?", default="", help="关键词，如 regression / group / trade_when")
    p_ops.add_argument("--category", default="", help="按类别过滤，如 时序 / 截面 / 组别")
    p_ops.add_argument("--json", action="store_true", help="输出 JSON")

    p_docs = sub.add_parser("docs", help="本地 WorldQuant 文档库")
    p_docs.add_argument("query", nargs="?", default="", help="关键词，如 数据字段 / 提交标准")
    p_docs.add_argument("--json", action="store_true", help="输出 JSON")

    p_data = sub.add_parser("data", help="搜索本地数据字段缓存")
    p_data.add_argument("query", nargs="?", default="", help="字段/描述关键词")
    p_data.add_argument("--dataset", default="", help="数据集 id 或名称，如 model16")
    p_data.add_argument("--type", default="", help="MATRIX / VECTOR")
    p_data.add_argument("--min-coverage", type=float, default=0.0)
    p_data.add_argument("--limit", type=int, default=30)
    p_data.add_argument("--json", action="store_true", help="输出 JSON")

    p_requeue = sub.add_parser("requeue", help="把失败/未知候选重置回 prechecked")
    p_requeue.add_argument("candidate_id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ledger = Ledger()
    ledger.init()
    try:
        if args.command == "init":
            print(f"台账已初始化: {ledger.path}")
        elif args.command == "login":
            BrainClient().login()
        elif args.command == "load":
            cmd_load(args, ledger)
        elif args.command == "export-legs":
            cmd_export_legs(args, ledger)
        elif args.command == "precheck":
            cmd_precheck(args, ledger)
        elif args.command == "run":
            cmd_run(args, ledger)
        elif args.command == "audit":
            cmd_audit(args, ledger)
        elif args.command == "corr":
            cmd_corr(args, ledger)
        elif args.command == "family":
            cmd_family(args, ledger)
        elif args.command == "gate":
            cmd_gate(args, ledger)
        elif args.command == "queue":
            cmd_queue(args, ledger)
        elif args.command == "approve":
            cmd_approve(args, ledger)
        elif args.command == "submit":
            cmd_submit(args, ledger)
        elif args.command == "verify":
            cmd_verify(args, ledger)
        elif args.command == "report":
            cmd_report(args, ledger)
        elif args.command == "validate":
            cmd_validate(args)
        elif args.command == "backfill-submitted":
            cmd_backfill(args, ledger)
        elif args.command == "status":
            cmd_status(args, ledger)
        elif args.command == "list":
            cmd_list(args, ledger)
        elif args.command == "show":
            cmd_show(args, ledger)
        elif args.command == "ops":
            cmd_ops(args)
        elif args.command == "docs":
            cmd_docs(args)
        elif args.command == "data":
            cmd_data(args)
        elif args.command == "requeue":
            cmd_requeue(args, ledger)
        else:
            parser.print_help()
            return 1
    except AuthError as exc:
        print(f"\n认证失败: {exc}")
        print("先在浏览器登录 BRAIN，把 cookie 写入 .state/session.json，或运行 python -m engine.cli login")
        return 2
    except KeyboardInterrupt:
        print("\n已中断")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
