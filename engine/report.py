"""每日报告：状态统计、今日产出、今日提交、观测池与待办。

日报按"日"聚合，不按批次过滤；batch_id 只作为"最近批次"标注。
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .ledger import Ledger, today_utc

REPORT_DIR = config.DATA_DIR / "reports"

OBSERVE_STATUSES = ["audited", "corr_pending", "corr_passed"]


def _fmt(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"


def _pct(value, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%" if isinstance(value, (int, float)) else "-"


def _alpha_line(candidate: dict, alpha: dict) -> str:
    return (
        f"| {candidate['label']} | `{alpha.get('alpha_id')}` | "
        f"{_fmt(alpha.get('sharpe'))} | {_fmt(alpha.get('fitness'))} | "
        f"{_pct(alpha.get('turnover'))} | {_fmt(alpha.get('self_corr'), 3)} | "
        f"{candidate.get('status')} |"
    )


def _passed_g2_g5(ledger: Ledger, candidate_id: str) -> bool:
    results = {gate["gate"]: gate["result"] for gate in ledger.get_gates(candidate_id)}
    return all(
        results.get(name) == "PASS"
        for name in ("G2_PLATFORM_CHECKS", "G3_QUALITY", "G4_TURNOVER", "G5_ROBUSTNESS")
    )


def build_report(ledger: Ledger, batch_id: str | None = None, day: str | None = None) -> str:
    day = day or today_utc()
    day_candidates = [
        candidate
        for candidate in ledger.list_candidates()
        if str(candidate.get("created_at") or "").startswith(day)
    ]
    counts: dict[str, int] = {}
    for candidate in day_candidates:
        counts[candidate["status"]] = counts.get(candidate["status"], 0) + 1
    if not batch_id and day_candidates:
        batch_id = max(day_candidates, key=lambda c: c.get("created_at") or "").get("batch_id")

    queue = ledger.list_queue(None, ["queued", "approved"])
    scheduled = ledger.list_queue(None, ["submitted", "verified"])
    submitted_today = [
        row for row in scheduled if str(row.get("submitted_at") or "").startswith(day)
    ]
    approved_today = [
        row
        for row in scheduled
        if not str(row.get("submitted_at") or "").startswith(day)
        and str(row.get("approved_at") or "").startswith(day)
    ]
    daily_n = ledger.daily_submit_count(day)

    produced: list[tuple[dict, dict]] = []
    for candidate in day_candidates:
        alpha = ledger.alpha_for_candidate(candidate["id"])
        if alpha and alpha.get("fitness") is not None:
            produced.append((candidate, alpha))
    produced.sort(key=lambda item: item[1]["fitness"], reverse=True)

    observe: list[tuple[dict, dict]] = []
    for candidate in day_candidates:
        alpha = ledger.alpha_for_candidate(candidate["id"])
        if not alpha or alpha.get("fitness") is None:
            continue
        if _passed_g2_g5(ledger, candidate["id"]):
            observe.append((candidate, alpha))
    observe.sort(key=lambda item: item[1]["fitness"], reverse=True)

    lines = [
        f"# BRAIN Alpha 日报 {day}",
        "",
        f"- 台账: `{ledger.path}`",
        f"- 最近批次: `{batch_id or '*'}`",
        f"- 今日提交: {daily_n}/2",
        "",
        "## 状态统计（当日新建候选）",
        "",
    ]
    if counts:
        for status, count in sorted(counts.items(), key=lambda item: -item[1]):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- 台账为空")

    lines += ["", f"## 今日产出 Top（新建 {len(day_candidates)} 条 / 完成回测 {len(produced)} 条）", ""]
    if produced:
        lines.append("| label | alpha | S | F | T | self | 状态 |")
        lines.append("|---|---|---|---|---|---|---|")
        for candidate, alpha in produced[:12]:
            lines.append(_alpha_line(candidate, alpha))
    else:
        lines.append("- 今日尚无完成的回测")

    lines += ["", "## 今日已提交", ""]
    if submitted_today:
        for row in submitted_today:
            lines.append(
                f"- {row['label']} `{row['alpha_id']}` status={row['status']} "
                f"S={_fmt(row.get('sharpe'))} F={_fmt(row.get('fitness'))} "
                f"self={_fmt(row.get('self_corr'), 3)} submitted_at={row.get('submitted_at')}"
            )
    else:
        lines.append("- 今日暂无平台提交")
    for row in approved_today:
        lines.append(
            f"- {row['label']} `{row['alpha_id']}` 当日批准，平台提交时间 "
            f"{row.get('submitted_at') or '未记录'}（status={row['status']}）"
        )

    lines += ["", "## 观测池 Top（当日候选 · G2–G5 通过）", ""]
    if observe:
        lines.append("| label | alpha | S | F | T | self | 状态 |")
        lines.append("|---|---|---|---|---|---|---|")
        for candidate, alpha in observe[:12]:
            lines.append(_alpha_line(candidate, alpha))
    else:
        lines.append("- 暂无通过 G2–G5 的候选")

    lines += ["", "## 提交队列（待人工批准）", ""]
    if queue:
        lines.append("| status | label | alpha | S | F | T | self | prod | score |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for row in queue:
            lines.append(
                f"| {row['status']} | {row['label']} | {row['alpha_id']} | "
                f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('fitness'))} | {_pct(row.get('turnover'))} | "
                f"{_fmt(row.get('self_corr'), 3)} | {_fmt(row.get('prod_corr'), 3)} | {_fmt(row.get('queue_rank'))} |"
            )
    else:
        lines.append("- 队列为空")

    note_path = REPORT_DIR / "notes" / f"{day}.md"
    if note_path.exists():
        note = note_path.read_text(encoding="utf-8").strip()
        if note:
            lines += ["", "## 备注（人工，次日检索用）", "", note, ""]

    lines += [
        "",
        "## 待办",
        "",
        "- 提交前按多维度验证：参数邻域 / 正交维度 / 分年 Sharpe / self / 集中度。",
        "- 若 G6 显示 prod 缺失，先在平台确认 prod correlation，再 `python -m engine.cli corr set-prod <candidate> <value>`。",
        "- 人工 `approve` → `submit` → `verify`；本报告不触发提交。",
        "- 16:00 北京结算后回看积分与 grade，把失败原因写回台账。",
        "",
    ]
    return "\n".join(lines)


def write_daily_report(ledger: Ledger, batch_id: str | None = None, day: str | None = None) -> Path:
    day = day or today_utc()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{day}.md"
    content = build_report(ledger, batch_id, day)
    path.write_text(content, encoding="utf-8")
    print(f"日报已写入: {path}")
    return path
