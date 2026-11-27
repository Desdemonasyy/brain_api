"""SQLite 台账：候选 / 模拟 / alpha / 闸门 / 提交队列 / 配额 / 事件。

唯一真相源。所有状态推进都走这里，CSV 只做导出。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_expression(expression: str) -> str:
    return " ".join(expression.split())


def make_candidate_id(expression_norm: str, settings_json: str, region: str) -> str:
    payload = f"{region}|{expression_norm}|{settings_json}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def make_family_key(fields: list[str], operators: list[str], neutralization: str) -> str:
    payload = json.dumps(
        {
            "fields": sorted(set(fields)),
            "operators": sorted(set(operators)),
            "neutralization": neutralization,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    label TEXT,
    hypothesis_id TEXT NOT NULL,
    batch_id TEXT,
    region TEXT NOT NULL,
    universe TEXT NOT NULL,
    delay INTEGER NOT NULL,
    expression TEXT NOT NULL,
    expression_norm TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    family_key TEXT NOT NULL,
    status TEXT NOT NULL,
    priority REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(expression_norm, settings_json, region)
);
CREATE INDEX IF NOT EXISTS idx_candidates_batch_status ON candidates(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_candidates_family ON candidates(family_key);

CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    run_id TEXT,
    sim_id TEXT UNIQUE,
    alpha_id TEXT,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    retry_after REAL,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_simulations_status ON simulations(status);
CREATE INDEX IF NOT EXISTS idx_simulations_candidate ON simulations(candidate_id);

CREATE TABLE IF NOT EXISTS alphas (
    alpha_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    label TEXT,
    sharpe REAL,
    fitness REAL,
    turnover REAL,
    returns REAL,
    drawdown REAL,
    margin REAL,
    long_count INTEGER,
    short_count INTEGER,
    checks_json TEXT,
    yearly_json TEXT,
    grade TEXT,
    platform_status TEXT,
    date_submitted TEXT,
    self_corr REAL,
    prod_corr REAL,
    corr_checked_at TEXT,
    pnl_rows INTEGER NOT NULL DEFAULT 0,
    settings_json TEXT,
    raw_json TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS gates (
    candidate_id TEXT NOT NULL,
    gate TEXT NOT NULL,
    result TEXT NOT NULL,
    value REAL,
    limit_value REAL,
    detail TEXT,
    checked_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, gate)
);

CREATE TABLE IF NOT EXISTS submissions (
    candidate_id TEXT PRIMARY KEY,
    alpha_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    queue_rank REAL,
    evidence_json TEXT,
    queued_at TEXT,
    approved_by TEXT,
    approved_at TEXT,
    approval_hash TEXT,
    expires_at TEXT,
    submitted_at TEXT,
    platform_status TEXT,
    score_checked_at TEXT,
    score_delta REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS alpha_pnl (
    alpha_id TEXT NOT NULL,
    date TEXT NOT NULL,
    pnl REAL NOT NULL,
    PRIMARY KEY(alpha_id, date)
);
CREATE INDEX IF NOT EXISTS idx_alpha_pnl_alpha ON alpha_pnl(alpha_id);

CREATE TABLE IF NOT EXISTS correlations (
    alpha_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    benchmark_id TEXT NOT NULL DEFAULT '',
    correlation REAL,
    sharpe REAL,
    returns REAL,
    turnover REAL,
    fitness REAL,
    margin REAL,
    source TEXT,
    checked_at TEXT,
    PRIMARY KEY(alpha_id, kind, benchmark_id)
);

CREATE TABLE IF NOT EXISTS quota (
    day TEXT NOT NULL,
    kind TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    limit_value INTEGER,
    PRIMARY KEY(day, kind)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    batch_id TEXT,
    status TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT,
    entity TEXT,
    action TEXT,
    payload_json TEXT
);
"""


class Ledger:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.DB_PATH)

    # ---------- 连接 ----------
    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def init(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
            self._migrate(connection)
        finally:
            connection.close()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        alpha_columns = {row["name"] for row in connection.execute("PRAGMA table_info(alphas)")}
        for name, ddl in {
            "self_corr": "REAL",
            "prod_corr": "REAL",
            "corr_checked_at": "TEXT",
            "pnl_rows": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in alpha_columns:
                connection.execute(f"ALTER TABLE alphas ADD COLUMN {name} {ddl}")

        submission_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(submissions)")
        }
        for name, ddl in {
            "status": "TEXT NOT NULL DEFAULT 'queued'",
            "queue_rank": "REAL",
            "evidence_json": "TEXT",
            "expires_at": "TEXT",
            "note": "TEXT",
        }.items():
            if name not in submission_columns:
                connection.execute(f"ALTER TABLE submissions ADD COLUMN {name} {ddl}")

    # ---------- 事件 ----------
    def log(self, actor: str, entity: str, action: str, payload: dict | None = None) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO events(ts, actor, entity, action, payload_json) VALUES(?,?,?,?,?)",
                (utcnow(), actor, entity, action, json.dumps(payload or {}, ensure_ascii=False)),
            )

    # ---------- 候选 ----------
    def add_candidate(
        self,
        *,
        expression: str,
        settings: dict,
        family_key: str,
        hypothesis_id: str,
        label: str = "",
        batch_id: str = "",
        priority: float = 0.0,
        status: str = "draft",
    ) -> tuple[dict, bool]:
        expression_norm = normalize_expression(expression)
        settings_json = json.dumps(settings, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        region = str(settings.get("region", "USA"))
        candidate_id = make_candidate_id(expression_norm, settings_json, region)
        now = utcnow()
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO candidates(
                    id, label, hypothesis_id, batch_id, region, universe, delay,
                    expression, expression_norm, settings_json, family_key,
                    status, priority, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate_id,
                    label or candidate_id[:8],
                    hypothesis_id,
                    batch_id,
                    region,
                    str(settings.get("universe", "")),
                    int(settings.get("delay", 1)),
                    expression,
                    expression_norm,
                    settings_json,
                    family_key,
                    status,
                    priority,
                    now,
                    now,
                ),
            )
            created = cursor.rowcount > 0
            row = connection.execute(
                "SELECT * FROM candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return dict(row), created

    def get_candidate(self, candidate_id: str) -> dict | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM candidates WHERE id=?", (candidate_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def list_candidates(
        self,
        batch_id: str | None = None,
        statuses: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        clauses = []
        params: list = []
        if batch_id:
            clauses.append("batch_id=?")
            params.append(batch_id)
        if statuses:
            clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        sql = "SELECT * FROM candidates"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY priority DESC, created_at ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        connection = self.connect()
        try:
            rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def set_candidate_status(self, candidate_id: str, status: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE candidates SET status=?, updated_at=? WHERE id=?",
                (status, utcnow(), candidate_id),
            )

    def set_candidate_priority(self, candidate_id: str, priority: float) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE candidates SET priority=?, updated_at=? WHERE id=?",
                (priority, utcnow(), candidate_id),
            )

    def family_conflicts(self, family_key: str, exclude_id: str) -> list[dict]:
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT c.id, c.label, c.status, a.alpha_id FROM candidates c
                LEFT JOIN alphas a ON a.candidate_id = c.id
                WHERE c.family_key=? AND c.id<>?
                  AND c.status IN ('audited','gate_passed','awaiting_human','approved','submitted','verified')
                ORDER BY c.updated_at DESC
                """,
                (family_key, exclude_id),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def count_claimable(self, batch_id: str | None) -> int:
        connection = self.connect()
        try:
            row = connection.execute(
                """
                SELECT COUNT(*) AS n FROM candidates c
                WHERE c.status='prechecked'
                  AND (? IS NULL OR c.batch_id=?)
                  AND NOT EXISTS (
                      SELECT 1 FROM simulations s
                      WHERE s.candidate_id=c.id AND s.status IN ('claimed','submitting','simulating')
                  )
                """,
                (batch_id, batch_id),
            ).fetchone()
            return int(row["n"])
        finally:
            connection.close()

    # ---------- 模拟 ----------
    def claim_next(self, batch_id: str | None, run_id: str) -> tuple[dict, int] | None:
        now = utcnow()
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT c.* FROM candidates c
                WHERE c.status='prechecked'
                  AND (? IS NULL OR c.batch_id=?)
                  AND NOT EXISTS (
                      SELECT 1 FROM simulations s
                      WHERE s.candidate_id=c.id AND s.status IN ('claimed','submitting','simulating')
                  )
                ORDER BY c.priority DESC, c.created_at ASC
                LIMIT 1
                """,
                (batch_id, batch_id),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE candidates SET status='simulating', updated_at=? WHERE id=?",
                (now, row["id"]),
            )
            cursor = connection.execute(
                """
                INSERT INTO simulations(candidate_id, run_id, status, created_at, started_at)
                VALUES(?,?,'claimed',?,?)
                """,
                (row["id"], run_id, now, now),
            )
            return dict(row), int(cursor.lastrowid)

    def mark_submitting(self, sim_row_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE simulations SET status='submitting' WHERE id=?", (sim_row_id,)
            )

    def release_simulation(self, sim_row_id: int) -> None:
        """并发槽满时释放本轮 claim，让候选重新排队。"""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE simulations SET status='queued', error=NULL, started_at=NULL WHERE id=?",
                (sim_row_id,),
            )

    def attach_sim_id(self, sim_row_id: int, sim_id: str, retry_after: float) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE simulations
                SET sim_id=?, status='simulating', attempts=attempts+1,
                    retry_after=?, started_at=?
                WHERE id=?
                """,
                (sim_id, retry_after, utcnow(), sim_row_id),
            )

    def finish_simulation(
        self,
        sim_row_id: int,
        status: str,
        error: str | None = None,
        alpha_id: str | None = None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE simulations SET status=?, error=?, alpha_id=COALESCE(?, alpha_id), finished_at=? WHERE id=?",
                (status, error, alpha_id, utcnow(), sim_row_id),
            )

    def recover_inflight(self) -> list[dict]:
        """恢复崩溃/中断的模拟；返回可按 sim_id 续跑的记录。"""
        inflight = []
        with self.transaction() as connection:
            claimed = connection.execute(
                "SELECT * FROM simulations WHERE status='claimed'"
            ).fetchall()
            for row in claimed:
                connection.execute(
                    "UPDATE simulations SET status='abandoned', finished_at=? WHERE id=?",
                    (utcnow(), row["id"]),
                )
                connection.execute(
                    "UPDATE candidates SET status='prechecked', updated_at=? WHERE id=? AND status='simulating'",
                    (utcnow(), row["candidate_id"]),
                )
                self._log_conn(
                    connection, "runner", row["candidate_id"], "sim_abandoned",
                    {"sim_row_id": row["id"]},
                )

            unknown = connection.execute(
                "SELECT * FROM simulations WHERE status='submitting' AND sim_id IS NULL"
            ).fetchall()
            for row in unknown:
                connection.execute(
                    "UPDATE simulations SET status='unknown', finished_at=? WHERE id=?",
                    (utcnow(), row["id"]),
                )
                connection.execute(
                    "UPDATE candidates SET status='unknown', updated_at=? WHERE id=?",
                    (utcnow(), row["candidate_id"]),
                )
                self._log_conn(
                    connection, "runner", row["candidate_id"], "sim_unknown",
                    {"sim_row_id": row["id"], "reason": "提交后进程中断，是否已创建模拟未知"},
                )

            rows = connection.execute(
                """
                SELECT s.id AS sim_row_id, s.sim_id, s.alpha_id, s.candidate_id, s.attempts
                FROM simulations s
                JOIN candidates c ON c.id = s.candidate_id
                WHERE (s.status='simulating' AND s.sim_id IS NOT NULL)
                   OR (s.status='complete' AND s.alpha_id IS NOT NULL AND c.status='simulating')
                """
            ).fetchall()
            inflight = [dict(row) for row in rows]
        return inflight

    def alive_sim(self, candidate_id: str) -> dict | None:
        connection = self.connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM simulations
                WHERE candidate_id=? AND status IN ('claimed','submitting','simulating')
                ORDER BY id DESC LIMIT 1
                """,
                (candidate_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def simulation_by_id(self, sim_row_id: int) -> dict | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM simulations WHERE id=?", (sim_row_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    # ---------- alpha ----------
    def record_alpha(self, candidate_id: str, payload: dict, yearly: dict | None = None) -> str:
        alpha_id = payload.get("id")
        stats = payload.get("is") or {}
        checks = stats.get("checks") or payload.get("checks") or []
        settings = payload.get("settings") or {}
        yearly_json = json.dumps(yearly, ensure_ascii=False) if yearly is not None else None
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO alphas(
                    alpha_id, candidate_id, label, sharpe, fitness, turnover, returns,
                    drawdown, margin, long_count, short_count, checks_json, yearly_json,
                    grade, platform_status, date_submitted, self_corr, prod_corr,
                    corr_checked_at, settings_json, raw_json, fetched_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(alpha_id) DO UPDATE SET
                    candidate_id=excluded.candidate_id,
                    label=excluded.label,
                    sharpe=excluded.sharpe,
                    fitness=excluded.fitness,
                    turnover=excluded.turnover,
                    returns=excluded.returns,
                    drawdown=excluded.drawdown,
                    margin=excluded.margin,
                    long_count=excluded.long_count,
                    short_count=excluded.short_count,
                    checks_json=excluded.checks_json,
                    yearly_json=COALESCE(excluded.yearly_json, alphas.yearly_json),
                    grade=excluded.grade,
                    platform_status=excluded.platform_status,
                    date_submitted=excluded.date_submitted,
                    self_corr=COALESCE(excluded.self_corr, alphas.self_corr),
                    prod_corr=COALESCE(excluded.prod_corr, alphas.prod_corr),
                    corr_checked_at=COALESCE(excluded.corr_checked_at, alphas.corr_checked_at),
                    settings_json=excluded.settings_json,
                    raw_json=excluded.raw_json,
                    fetched_at=excluded.fetched_at
                """,
                (
                    alpha_id,
                    candidate_id,
                    payload.get("name") or candidate_id[:8],
                    stats.get("sharpe"),
                    stats.get("fitness"),
                    stats.get("turnover"),
                    stats.get("returns"),
                    stats.get("drawdown"),
                    stats.get("margin"),
                    stats.get("longCount"),
                    stats.get("shortCount"),
                    json.dumps(checks, ensure_ascii=False),
                    yearly_json,
                    payload.get("grade"),
                    payload.get("status"),
                    payload.get("dateSubmitted"),
                    stats.get("selfCorrelation"),
                    stats.get("prodCorrelation"),
                    utcnow() if stats.get("selfCorrelation") is not None or stats.get("prodCorrelation") is not None else None,
                    json.dumps(settings, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False)[:200000],
                    utcnow(),
                ),
            )
        return alpha_id

    def get_alpha(self, alpha_id: str) -> dict | None:
        connection = self.connect()
        try:
            row = connection.execute("SELECT * FROM alphas WHERE alpha_id=?", (alpha_id,)).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def alpha_for_candidate(self, candidate_id: str) -> dict | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM alphas WHERE candidate_id=? ORDER BY fetched_at DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    # ---------- PnL / 相关性 ----------
    def record_pnl(self, alpha_id: str, rows: list[dict]) -> int:
        values = []
        for row in rows:
            date = row.get("date")
            pnl = row.get("pnl")
            if date is None or pnl is None:
                continue
            values.append((alpha_id, str(date), float(pnl)))
        if not values:
            return 0
        with self.transaction() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO alpha_pnl(alpha_id, date, pnl) VALUES(?,?,?)",
                values,
            )
            count = connection.execute(
                "SELECT COUNT(*) AS n FROM alpha_pnl WHERE alpha_id=?", (alpha_id,)
            ).fetchone()["n"]
            connection.execute(
                "UPDATE alphas SET pnl_rows=? WHERE alpha_id=?", (int(count), alpha_id)
            )
        return len(values)

    def pnl_count(self, alpha_id: str) -> int:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM alpha_pnl WHERE alpha_id=?", (alpha_id,)
            ).fetchone()
            return int(row["n"])
        finally:
            connection.close()

    def load_pnl(self, alpha_id: str) -> dict[str, float]:
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT date, pnl FROM alpha_pnl WHERE alpha_id=? ORDER BY date", (alpha_id,)
            ).fetchall()
            return {row["date"]: float(row["pnl"]) for row in rows}
        finally:
            connection.close()

    def replace_correlations(self, alpha_id: str, kind: str, rows: list[dict], source: str) -> None:
        now = utcnow()
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM correlations WHERE alpha_id=? AND kind=?", (alpha_id, kind)
            )
            for row in rows:
                benchmark_id = str(row.get("benchmark_id") or row.get("id") or "")
                connection.execute(
                    """
                    INSERT OR REPLACE INTO correlations(
                        alpha_id, kind, benchmark_id, correlation, sharpe, returns,
                        turnover, fitness, margin, source, checked_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        alpha_id,
                        kind,
                        benchmark_id,
                        row.get("correlation"),
                        row.get("sharpe"),
                        row.get("returns"),
                        row.get("turnover"),
                        row.get("fitness"),
                        row.get("margin"),
                        source,
                        now,
                    ),
                )
            if kind in ("self", "prod"):
                column = "self_corr" if kind == "self" else "prod_corr"
                max_value = max(
                    (float(row["correlation"]) for row in rows if row.get("correlation") is not None),
                    default=None,
                )
                connection.execute(
                    f"UPDATE alphas SET {column}=?, corr_checked_at=? WHERE alpha_id=?",
                    (max_value, now, alpha_id),
                )

    def get_correlations(self, alpha_id: str, kind: str | None = None) -> list[dict]:
        connection = self.connect()
        try:
            if kind:
                rows = connection.execute(
                    "SELECT * FROM correlations WHERE alpha_id=? AND kind=? ORDER BY correlation DESC",
                    (alpha_id, kind),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM correlations WHERE alpha_id=? ORDER BY kind, correlation DESC",
                    (alpha_id,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def set_alpha_corr(
        self,
        alpha_id: str,
        self_corr: float | None = None,
        prod_corr: float | None = None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE alphas SET
                    self_corr=COALESCE(?, self_corr),
                    prod_corr=COALESCE(?, prod_corr),
                    corr_checked_at=?
                WHERE alpha_id=?
                """,
                (self_corr, prod_corr, utcnow(), alpha_id),
            )

    # ---------- 提交队列 ----------
    def upsert_submission(
        self,
        candidate_id: str,
        alpha_id: str,
        *,
        status: str = "queued",
        queue_rank: float = 0.0,
        evidence: dict | None = None,
        note: str = "",
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO submissions(
                    candidate_id, alpha_id, status, queue_rank, evidence_json,
                    queued_at, note
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    alpha_id=excluded.alpha_id,
                    status=excluded.status,
                    queue_rank=excluded.queue_rank,
                    evidence_json=excluded.evidence_json,
                    note=excluded.note,
                    queued_at=COALESCE(submissions.queued_at, excluded.queued_at)
                """,
                (
                    candidate_id,
                    alpha_id,
                    status,
                    queue_rank,
                    json.dumps(evidence or {}, ensure_ascii=False),
                    utcnow(),
                    note,
                ),
            )

    def update_submission(self, candidate_id: str, **fields) -> None:
        allowed = {
            "status", "queue_rank", "evidence_json", "approved_by", "approved_at",
            "approval_hash", "expires_at", "submitted_at", "platform_status",
            "score_checked_at", "score_delta", "note",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self.transaction() as connection:
            connection.execute(
                f"UPDATE submissions SET {assignments} WHERE candidate_id=?",
                (*updates.values(), candidate_id),
            )

    def get_submission(self, candidate_id: str) -> dict | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM submissions WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def list_queue(self, batch_id: str | None = None, statuses: list[str] | None = None) -> list[dict]:
        clauses = []
        params: list = []
        if batch_id:
            clauses.append("c.batch_id=?")
            params.append(batch_id)
        if statuses:
            clauses.append(f"s.status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        sql = """
            SELECT s.*, c.label, c.batch_id, c.region, c.universe, c.hypothesis_id,
                   a.sharpe, a.fitness, a.turnover, a.returns, a.self_corr, a.prod_corr,
                   a.grade
            FROM submissions s
            JOIN candidates c ON c.id = s.candidate_id
            LEFT JOIN alphas a ON a.alpha_id = s.alpha_id
        """
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY s.queue_rank DESC, s.queued_at ASC"
        connection = self.connect()
        try:
            rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def daily_submit_count(self, day: str) -> int:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM submissions WHERE submitted_at LIKE ?",
                (f"{day}%",),
            ).fetchone()
            return int(row["n"])
        finally:
            connection.close()

    # ---------- 闸门 ----------
    def set_gate(
        self,
        candidate_id: str,
        gate: str,
        result: str,
        value: float | None = None,
        limit_value: float | None = None,
        detail: str = "",
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO gates(candidate_id, gate, result, value, limit_value, detail, checked_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(candidate_id, gate) DO UPDATE SET
                    result=excluded.result, value=excluded.value,
                    limit_value=excluded.limit_value, detail=excluded.detail,
                    checked_at=excluded.checked_at
                """,
                (candidate_id, gate, result, value, limit_value, detail, utcnow()),
            )

    def get_gates(self, candidate_id: str) -> list[dict]:
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM gates WHERE candidate_id=? ORDER BY gate", (candidate_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def delete_gate(self, candidate_id: str, gate: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM gates WHERE candidate_id=? AND gate=?", (candidate_id, gate)
            )

    # ---------- 配额 / 运行 ----------
    def quota_add(self, day: str, kind: str, amount: int = 1) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO quota(day, kind, used) VALUES(?,?,?)
                ON CONFLICT(day, kind) DO UPDATE SET used=used+excluded.used
                """,
                (day, kind, amount),
            )

    def quota_get(self, day: str, kind: str) -> int:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT used FROM quota WHERE day=? AND kind=?", (day, kind)
            ).fetchone()
            return int(row["used"]) if row else 0
        finally:
            connection.close()

    def create_run(self, run_id: str, batch_id: str | None, total: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs(run_id, batch_id, status, total, done, started_at)
                VALUES(?,?, 'running', ?, 0, ?)
                """,
                (run_id, batch_id, total, utcnow()),
            )

    def finish_run(self, run_id: str, status: str, done: int, note: str = "") -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE runs SET status=?, done=?, note=?, finished_at=? WHERE run_id=?",
                (status, done, note, utcnow(), run_id),
            )

    # ---------- 统计 ----------
    def status_counts(self, batch_id: str | None = None) -> dict[str, int]:
        connection = self.connect()
        try:
            if batch_id:
                rows = connection.execute(
                    "SELECT status, COUNT(*) AS n FROM candidates WHERE batch_id=? GROUP BY status",
                    (batch_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT status, COUNT(*) AS n FROM candidates GROUP BY status"
                ).fetchall()
            return {row["status"]: int(row["n"]) for row in rows}
        finally:
            connection.close()

    @staticmethod
    def _log_conn(connection, actor: str, entity: str, action: str, payload: dict) -> None:
        connection.execute(
            "INSERT INTO events(ts, actor, entity, action, payload_json) VALUES(?,?,?,?,?)",
            (utcnow(), actor, entity, action, json.dumps(payload, ensure_ascii=False)),
        )
