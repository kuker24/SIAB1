#!/usr/bin/env python3
"""
Post-Exam Audit Read-Only Script

SELECT-only audit tool for post-exam data safety verification.
Read-only by design: no INSERT/UPDATE/DELETE/DROP/TRUNCATE.

Usage:
    python scripts/post_exam_audit_readonly.py --exam-id 42
    python scripts/post_exam_audit_readonly.py --exam-id 42 --allow-production-readonly
    python scripts/post_exam_audit_readonly.py --exam-id 42 --summary-json audit-report.json
    python scripts/post_exam_audit_readonly.py --exam-id 42 --verbose

Environment:
    DATABASE_URL - PostgreSQL connection string (required)

Safety:
    - Rejects production URLs unless --allow-production-readonly is set
    - All queries are SELECT-only with LIMIT/bounds
    - Does not print raw answer_text, password_hash, or PII
    - Uses explicit BEGIN READ ONLY / ROLLBACK transaction
    - Terminal audit covers both submitted + completed sessions
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Schema constants — actual table/column names from SQLAlchemy models
# ---------------------------------------------------------------------------
_TABLE_EXAM_SESSIONS = "exam_sessions"
_TABLE_ANSWERS = "answers"
_TABLE_EXAM_LOGS = "exam_logs"
_TABLE_USERS = "users"
_TABLE_EXAMS = "exams"
_TABLE_QUESTIONS = "questions"
_TABLE_SECURITY_EVENTS = "security_events"

# Status values
_STATUS_SUBMITTED = "submitted"
_STATUS_IN_PROGRESS = "in_progress"
_STATUS_ABANDONED = "abandoned"
_STATUS_COMPLETED = "completed"

# Terminal statuses — session yang sudah final (tidak bisa lanjut jawab)
# submitted = siswa sudah final-submit, completed = admin/sistem sudah finalize
_TERMINAL_STATUSES = (_STATUS_SUBMITTED, _STATUS_COMPLETED)

def _is_production_url(url: str) -> bool:
    """Treat every non-local database host as production by default."""
    host = (urlsplit(url).hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "::1"} and not host.endswith(
        (".test", ".invalid")
    )


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Post-Exam Audit Read-Only Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--exam-id",
        type=int,
        required=True,
        help="Exam ID to audit.",
    )
    parser.add_argument(
        "--allow-production-readonly",
        action="store_true",
        help="Allow running against production (read-only).",
    )
    parser.add_argument(
        "--summary-json",
        type=str,
        default=None,
        help="Path to write summary JSON output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional detail rows.",
    )
    return parser.parse_args(argv)


def _get_database_url() -> str:
    """Get DATABASE_URL from environment."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("ERROR: DATABASE_URL environment variable is required.")
    return url


def _check_production_safety(url: str, allow_production: bool) -> None:
    """Reject production URLs unless explicitly allowed."""
    if _is_production_url(url) and not allow_production:
        raise SystemExit(
            "ERROR: DATABASE_URL appears to be production. "
            "Use --allow-production-readonly to proceed (read-only only)."
        )


# ---------------------------------------------------------------------------
# Query builders — all SELECT-only, bounded, no PII
# ---------------------------------------------------------------------------

def _q_session_status_distribution(exam_id: int) -> Tuple[str, dict]:
    """Session status distribution."""
    sql = f"""
        SELECT status, COUNT(*) AS session_count
        FROM {_TABLE_EXAM_SESSIONS}
        WHERE exam_id = :exam_id
        GROUP BY status
        ORDER BY session_count DESC;
    """
    return sql, {"exam_id": exam_id}


def _terminal_status_sql(alias: Optional[str] = None) -> str:
    """Build SQL clause for terminal statuses (submitted + completed)."""
    column = "status" if not alias else f"{alias}.status"
    statuses = ", ".join(f"'{s}'" for s in _TERMINAL_STATUSES)
    return f"{column} IN ({statuses})"


def _q_submitted_count(exam_id: int) -> Tuple[str, dict]:
    """Terminal session count (submitted + completed)."""
    sql = f"""
        SELECT COUNT(*) AS terminal_count
        FROM {_TABLE_EXAM_SESSIONS}
        WHERE exam_id = :exam_id AND {_terminal_status_sql()};
    """
    return sql, {"exam_id": exam_id}


def _q_in_progress_stuck(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """In-progress/stuck sessions."""
    sql = f"""
        SELECT id, user_id, start_time, end_time, status, violation_count
        FROM {_TABLE_EXAM_SESSIONS}
        WHERE exam_id = :exam_id AND status = '{_STATUS_IN_PROGRESS}'
        ORDER BY start_time
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_answer_count_per_submitted(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Answer count per terminal session (submitted + completed), ordered lowest first."""
    sql = f"""
        SELECT es.id AS session_id, es.user_id, es.status,
               COUNT(a.id) AS answer_count
        FROM {_TABLE_EXAM_SESSIONS} es
        LEFT JOIN {_TABLE_ANSWERS} a ON a.session_id = es.id
        WHERE es.exam_id = :exam_id AND {_terminal_status_sql("es")}
        GROUP BY es.id, es.user_id, es.status
        ORDER BY answer_count ASC
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_question_count(exam_id: int) -> Tuple[str, dict]:
    """Question count per exam."""
    sql = f"""
        SELECT exam_id, COUNT(*) AS question_count
        FROM {_TABLE_QUESTIONS}
        WHERE exam_id = :exam_id
        GROUP BY exam_id;
    """
    return sql, {"exam_id": exam_id}


def _q_sessions_zero_answers(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Terminal sessions with zero answers — high risk anomaly."""
    sql = f"""
        SELECT es.id AS session_id, es.user_id, es.status,
               es.start_time, es.end_time, es.score
        FROM {_TABLE_EXAM_SESSIONS} es
        LEFT JOIN {_TABLE_ANSWERS} a ON a.session_id = es.id
        WHERE es.exam_id = :exam_id
          AND {_terminal_status_sql("es")}
          AND a.id IS NULL
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_duplicate_answers(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Duplicate answer rows per session/question."""
    sql = f"""
        SELECT session_id, question_id, COUNT(*) AS row_count
        FROM {_TABLE_ANSWERS}
        WHERE session_id IN (
            SELECT id FROM {_TABLE_EXAM_SESSIONS} WHERE exam_id = :exam_id
        )
        GROUP BY session_id, question_id
        HAVING COUNT(*) > 1
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_final_submit_anomalies(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Terminal sessions with missing end_time or timestamp mismatch."""
    sql = f"""
        SELECT es.id AS session_id, es.user_id,
               es.end_time AS session_end_time,
               MAX(a.answered_at) AS last_answer_time
        FROM {_TABLE_EXAM_SESSIONS} es
        JOIN {_TABLE_ANSWERS} a ON a.session_id = es.id
        WHERE es.exam_id = :exam_id AND {_terminal_status_sql("es")}
        GROUP BY es.id, es.user_id, es.end_time
        HAVING es.end_time IS NULL
            OR MAX(a.answered_at) > es.end_time + INTERVAL '5 minutes'
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_answers_after_submit(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Answers recorded after terminal session end_time."""
    sql = f"""
        SELECT a.session_id, a.question_id, a.answered_at, es.end_time
        FROM {_TABLE_ANSWERS} a
        JOIN {_TABLE_EXAM_SESSIONS} es ON es.id = a.session_id
        WHERE es.exam_id = :exam_id
          AND {_terminal_status_sql("es")}
          AND es.end_time IS NOT NULL
          AND a.answered_at > es.end_time
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_submitted_score_null(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Terminal sessions with NULL score — grading not complete."""
    sql = f"""
        SELECT id, user_id, status, score, end_time, violation_count
        FROM {_TABLE_EXAM_SESSIONS}
        WHERE exam_id = :exam_id
          AND {_terminal_status_sql()}
          AND score IS NULL
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_ungraded_answers(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Terminal sessions with ungraded answers."""
    sql = f"""
        SELECT es.id AS session_id, es.status, es.score,
               COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) AS ungraded_answers,
               COUNT(a.id) AS total_answers
        FROM {_TABLE_EXAM_SESSIONS} es
        JOIN {_TABLE_ANSWERS} a ON a.session_id = es.id
        WHERE es.exam_id = :exam_id AND {_terminal_status_sql("es")}
        GROUP BY es.id, es.status, es.score
        HAVING COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) > 0
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_violation_log_aggregate(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Event type aggregate from exam_logs."""
    sql = f"""
        SELECT el.event_type, COUNT(*) AS event_count
        FROM {_TABLE_EXAM_LOGS} el
        JOIN {_TABLE_EXAM_SESSIONS} es ON es.id = el.session_id
        WHERE es.exam_id = :exam_id
        GROUP BY el.event_type
        ORDER BY event_count DESC
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_security_events_aggregate(exam_id: int, limit: int = 50) -> Tuple[str, dict]:
    """Security events aggregate."""
    sql = f"""
        SELECT se.event_type, se.severity, COUNT(*) AS event_count
        FROM {_TABLE_SECURITY_EVENTS} se
        JOIN {_TABLE_EXAM_SESSIONS} es ON es.id = se.session_id
        WHERE es.exam_id = :exam_id
        GROUP BY se.event_type, se.severity
        ORDER BY event_count DESC
        LIMIT {limit};
    """
    return sql, {"exam_id": exam_id}


def _q_violation_count_distribution(exam_id: int) -> Tuple[str, dict]:
    """Violation count distribution for sessions with violations."""
    sql = f"""
        SELECT violation_count, COUNT(*) AS session_count
        FROM {_TABLE_EXAM_SESSIONS}
        WHERE exam_id = :exam_id AND violation_count > 0
        GROUP BY violation_count
        ORDER BY violation_count DESC;
    """
    return sql, {"exam_id": exam_id}


def _q_synthetic_residue(limit: int = 50) -> Tuple[str, dict]:
    """Check for synthetic/test users."""
    sql = f"""
        SELECT id, username, role, student_class, is_active
        FROM {_TABLE_USERS}
        WHERE username LIKE '%%synthetic%%'
           OR username LIKE '%%test_%%'
           OR username LIKE '%%loadtest%%'
           OR username LIKE '%%dummy%%'
        LIMIT {limit};
    """
    return sql, {}


def _q_exam_summary(exam_id: int) -> Tuple[str, dict]:
    """Exam-level summary."""
    sql = f"""
        SELECT
            e.id AS exam_id, e.title, e.start_time, e.end_time,
            e.is_published, e.is_deleted, e.has_ever_had_results,
            COUNT(DISTINCT es.id) AS total_sessions,
            COUNT(DISTINCT CASE WHEN es.status = '{_STATUS_SUBMITTED}' THEN es.id END) AS submitted_sessions,
            COUNT(DISTINCT CASE WHEN es.status = '{_STATUS_COMPLETED}' THEN es.id END) AS completed_sessions,
            COUNT(DISTINCT CASE WHEN {_terminal_status_sql('es')} THEN es.id END) AS terminal_sessions,
            COUNT(DISTINCT CASE WHEN es.status = '{_STATUS_IN_PROGRESS}' THEN es.id END) AS in_progress_sessions,
            COUNT(DISTINCT CASE WHEN es.status = '{_STATUS_ABANDONED}' THEN es.id END) AS abandoned_sessions,
            COUNT(DISTINCT a.id) AS total_answers,
            ROUND(AVG(es.score)::numeric, 2) AS avg_score,
            MIN(es.score) AS min_score,
            MAX(es.score) AS max_score
        FROM {_TABLE_EXAMS} e
        LEFT JOIN {_TABLE_EXAM_SESSIONS} es ON es.exam_id = e.id
        LEFT JOIN {_TABLE_ANSWERS} a ON a.session_id = es.id
        WHERE e.id = :exam_id
        GROUP BY e.id, e.title, e.start_time, e.end_time,
                 e.is_published, e.is_deleted, e.has_ever_had_results;
    """
    return sql, {"exam_id": exam_id}


def _q_score_distribution(exam_id: int) -> Tuple[str, dict]:
    """Score distribution bands (terminal sessions only)."""
    sql = f"""
        SELECT
            CASE
                WHEN score >= 90 THEN 'A (>=90)'
                WHEN score >= 80 THEN 'B (80-89)'
                WHEN score >= 70 THEN 'C (70-79)'
                WHEN score >= 60 THEN 'D (60-69)'
                ELSE 'E (<60)'
            END AS grade_band,
            COUNT(*) AS student_count
        FROM {_TABLE_EXAM_SESSIONS}
        WHERE exam_id = :exam_id
          AND {_terminal_status_sql()}
          AND score IS NOT NULL
        GROUP BY grade_band
        ORDER BY grade_band;
    """
    return sql, {"exam_id": exam_id}


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

class PostExamAuditor:
    """Run read-only audit queries and collect results."""

    def __init__(self, exam_id: int, verbose: bool = False):
        self.exam_id = exam_id
        self.verbose = verbose
        self.results: Dict[str, Any] = {}
        self.anomalies: List[Dict[str, str]] = []
        self.start_time = datetime.now(timezone.utc)

    def _run_query(self, conn, label: str, sql: str, params: dict) -> List[dict]:
        """Execute a SELECT query and return rows as list of dicts."""
        from sqlalchemy import text
        result = conn.execute(text(sql), params)
        columns = result.keys()
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        self.results[label] = rows
        if self.verbose:
            print(f"\n--- {label} ({len(rows)} rows) ---")
            for row in rows[:20]:
                print(f"  {row}")
            if len(rows) > 20:
                print(f"  ... and {len(rows) - 20} more rows")
        return rows

    def _count_label(self, label: str, rows: List[dict], count_key: str = "session_count") -> int:
        """Extract a single count from query results."""
        if not rows:
            return 0
        return int(rows[0].get(count_key, 0))

    def run(self, conn) -> Dict[str, Any]:
        """Run full audit on an existing connection."""
        exam_id = self.exam_id

        # 1. Exam summary
        sql, params = _q_exam_summary(exam_id)
        exam_rows = self._run_query(conn, "exam_summary", sql, params)
        if not exam_rows:
            self.anomalies.append({
                "severity": "high_risk",
                "description": f"Exam {exam_id} not found or no data.",
            })
            return self._build_report()

        # 2. Session status distribution
        sql, params = _q_session_status_distribution(exam_id)
        self._run_query(conn, "session_status_distribution", sql, params)

        # 3. Terminal count (submitted + completed)
        sql, params = _q_submitted_count(exam_id)
        self._run_query(conn, "terminal_count", sql, params)

        # 4. In-progress / stuck
        sql, params = _q_in_progress_stuck(exam_id)
        stuck_rows = self._run_query(conn, "in_progress_stuck", sql, params)
        if stuck_rows:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(stuck_rows)} session(s) still in_progress after exam ended.",
            })

        # 5. Question count
        sql, params = _q_question_count(exam_id)
        self._run_query(conn, "question_count", sql, params)

        # 6. Answer count per terminal session (submitted + completed)
        sql, params = _q_answer_count_per_submitted(exam_id)
        answer_count_rows = self._run_query(conn, "answer_count_per_terminal", sql, params)
        zero_answer_sessions = [r for r in answer_count_rows if int(r.get("answer_count", 0)) == 0]
        if zero_answer_sessions:
            self.anomalies.append({
                "severity": "high_risk",
                "description": f"{len(zero_answer_sessions)} terminal session(s) with zero answers.",
            })

        # 7. Terminal sessions with zero answers (explicit check)
        sql, params = _q_sessions_zero_answers(exam_id)
        zero_rows = self._run_query(conn, "sessions_zero_answers", sql, params)
        if zero_rows and not zero_answer_sessions:
            self.anomalies.append({
                "severity": "high_risk",
                "description": f"{len(zero_rows)} terminal session(s) with zero answers (explicit check).",
            })

        # 8. Duplicate answers
        sql, params = _q_duplicate_answers(exam_id)
        dup_rows = self._run_query(conn, "duplicate_answers", sql, params)
        if dup_rows:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(dup_rows)} duplicate answer row(s) found.",
            })

        # 9. Final submit anomalies
        sql, params = _q_final_submit_anomalies(exam_id)
        submit_anom = self._run_query(conn, "final_submit_anomalies", sql, params)
        if submit_anom:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(submit_anom)} final submit timestamp anomaly(ies).",
            })

        # 10. Answers after final submit
        sql, params = _q_answers_after_submit(exam_id)
        after_rows = self._run_query(conn, "answers_after_submit", sql, params)
        if after_rows:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(after_rows)} answer(s) recorded after final submit.",
            })

        # 11. Terminal sessions with score NULL
        sql, params = _q_submitted_score_null(exam_id)
        score_null_rows = self._run_query(conn, "terminal_score_null", sql, params)
        if score_null_rows:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(score_null_rows)} terminal session(s) with NULL score.",
            })

        # 12. Ungraded answers in terminal sessions
        sql, params = _q_ungraded_answers(exam_id)
        ungraded_rows = self._run_query(conn, "ungraded_answers", sql, params)
        if ungraded_rows:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(ungraded_rows)} terminal session(s) with ungraded answers.",
            })

        # 13. Violation log aggregate
        sql, params = _q_violation_log_aggregate(exam_id)
        self._run_query(conn, "violation_log_aggregate", sql, params)

        # 14. Security events aggregate
        sql, params = _q_security_events_aggregate(exam_id)
        self._run_query(conn, "security_events_aggregate", sql, params)

        # 15. Violation count distribution
        sql, params = _q_violation_count_distribution(exam_id)
        self._run_query(conn, "violation_count_distribution", sql, params)

        # 16. Synthetic residue
        sql, params = _q_synthetic_residue()
        synth_rows = self._run_query(conn, "synthetic_residue", sql, params)
        if synth_rows:
            self.anomalies.append({
                "severity": "needs_review",
                "description": f"{len(synth_rows)} synthetic/test user(s) found.",
            })

        # 17. Score distribution
        sql, params = _q_score_distribution(exam_id)
        self._run_query(conn, "score_distribution", sql, params)

        return self._build_report()

    def _build_report(self) -> Dict[str, Any]:
        """Build summary report."""
        end_time = datetime.now(timezone.utc)

        # Data safety concern
        high_risk = [a for a in self.anomalies if a["severity"] == "high_risk"]
        data_safety_concern = len(high_risk) > 0

        report = {
            "audit_metadata": {
                "exam_id": self.exam_id,
                "audit_start": self.start_time.isoformat(),
                "audit_end": end_time.isoformat(),
                "duration_seconds": (end_time - self.start_time).total_seconds(),
            },
            "exam_summary": self.results.get("exam_summary", []),
            "session_status_distribution": self.results.get("session_status_distribution", []),
            "terminal_count": self.results.get("terminal_count", []),
            "in_progress_stuck_count": len(self.results.get("in_progress_stuck", [])),
            "question_count": self.results.get("question_count", []),
            "sessions_zero_answers_count": len(self.results.get("sessions_zero_answers", [])),
            "duplicate_answers_count": len(self.results.get("duplicate_answers", [])),
            "final_submit_anomalies_count": len(self.results.get("final_submit_anomalies", [])),
            "answers_after_submit_count": len(self.results.get("answers_after_submit", [])),
            "terminal_score_null_count": len(self.results.get("terminal_score_null", [])),
            "ungraded_answers_count": len(self.results.get("ungraded_answers", [])),
            "violation_log_aggregate": self.results.get("violation_log_aggregate", []),
            "security_events_aggregate": self.results.get("security_events_aggregate", []),
            "violation_count_distribution": self.results.get("violation_count_distribution", []),
            "synthetic_residue_count": len(self.results.get("synthetic_residue", [])),
            "score_distribution": self.results.get("score_distribution", []),
            "anomalies": self.anomalies,
            "data_safety_concern": data_safety_concern,
            "high_risk_anomalies": high_risk,
        }
        return report


def _print_summary(report: Dict[str, Any]) -> None:
    """Print human-readable summary."""
    meta = report.get("audit_metadata", {})
    exam = report.get("exam_summary", [{}])
    exam_info = exam[0] if exam else {}

    print("=" * 60)
    print("POST-EXAM AUDIT SUMMARY")
    print("=" * 60)
    print(f"Exam ID:      {meta.get('exam_id')}")
    print(f"Exam Title:   {exam_info.get('title', 'N/A')}")
    print(f"Audit Start:  {meta.get('audit_start')}")
    print(f"Audit End:    {meta.get('audit_end')}")
    print(f"Duration:     {meta.get('duration_seconds', 0):.1f}s")
    print()

    print("SESSION OVERVIEW")
    print("-" * 40)
    print(f"Total Sessions:       {exam_info.get('total_sessions', 0)}")
    print(f"Submitted:            {exam_info.get('submitted_sessions', 0)}")
    print(f"Completed:            {exam_info.get('completed_sessions', 0)}")
    print(f"Terminal (sum):       {exam_info.get('terminal_sessions', exam_info.get('submitted_sessions', 0))}")
    print(f"In Progress:          {exam_info.get('in_progress_sessions', 0)}")
    print(f"Abandoned:            {exam_info.get('abandoned_sessions', 0)}")
    print(f"Total Answers:        {exam_info.get('total_answers', 0)}")
    print(f"Avg Score:            {exam_info.get('avg_score', 'N/A')}")
    print(f"Min Score:            {exam_info.get('min_score', 'N/A')}")
    print(f"Max Score:            {exam_info.get('max_score', 'N/A')}")
    print()

    print("ANOMALY CHECKS")
    print("-" * 40)
    print(f"In-Progress Stuck:    {report.get('in_progress_stuck_count', 0)}")
    print(f"Zero-Answer Sessions: {report.get('sessions_zero_answers_count', 0)}")
    print(f"Duplicate Answers:    {report.get('duplicate_answers_count', 0)}")
    print(f"Submit Anomalies:     {report.get('final_submit_anomalies_count', 0)}")
    print(f"Answers After Submit: {report.get('answers_after_submit_count', 0)}")
    print(f"Terminal Score NULL:  {report.get('terminal_score_null_count', 0)}")
    print(f"Ungraded Answers:     {report.get('ungraded_answers_count', 0)}")
    print(f"Synthetic Residue:    {report.get('synthetic_residue_count', 0)}")
    print()

    violations = report.get("violation_log_aggregate", [])
    if violations:
        print("VIOLATION EVENTS")
        print("-" * 40)
        for v in violations[:10]:
            print(f"  {v.get('event_type', 'N/A'):30s} count={v.get('event_count', 0)}")
        print()

    security = report.get("security_events_aggregate", [])
    if security:
        print("SECURITY EVENTS")
        print("-" * 40)
        for s in security[:10]:
            print(f"  {s.get('event_type', 'N/A'):20s} severity={s.get('severity', 'N/A'):10s} count={s.get('event_count', 0)}")
        print()

    score_dist = report.get("score_distribution", [])
    if score_dist:
        print("SCORE DISTRIBUTION")
        print("-" * 40)
        for sd in score_dist:
            print(f"  {sd.get('grade_band', 'N/A'):15s} count={sd.get('student_count', 0)}")
        print()

    anomalies = report.get("anomalies", [])
    if anomalies:
        print("ANOMALIES FOUND")
        print("-" * 40)
        for a in anomalies:
            print(f"  [{a['severity'].upper():15s}] {a['description']}")
        print()
    else:
        print("ANOMALIES: None found.")
        print()

    data_safety = report.get("data_safety_concern", False)
    print("=" * 60)
    if data_safety:
        print("DATA SAFETY CONCERN: YES — high-risk anomalies found!")
        print("ACTION: Escalate to decision owner before remediation.")
    else:
        print("DATA SAFETY CONCERN: NO — no high-risk anomalies.")
    print("=" * 60)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    args = _parse_args(argv)
    database_url = _get_database_url()
    _check_production_safety(database_url, args.allow_production_readonly)

    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("ERROR: sqlalchemy is required. pip install sqlalchemy psycopg2-binary")
        return 1

    # Explicit read-only transaction — no write risk
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    auditor = PostExamAuditor(exam_id=args.exam_id, verbose=args.verbose)

    report = None
    try:
        with engine.connect() as conn:
            conn.execute(text("BEGIN READ ONLY"))
            try:
                report = auditor.run(conn)
            finally:
                conn.execute(text("ROLLBACK"))
    except Exception as exc:
        print(f"ERROR during audit: {exc}")
        return 1
    finally:
        engine.dispose()

    if report is None:
        print("ERROR: audit did not produce a report.")
        return 1

    _print_summary(report)

    # Write JSON summary if requested
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize datetime objects
        def _json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)

        summary_path.write_text(
            json.dumps(report, indent=2, default=_json_serializer),
            encoding="utf-8",
        )
        print(f"\nSummary JSON written to: {summary_path}")

    # Exit code: 0 = no high-risk, 1 = high-risk found
    if report.get("data_safety_concern", False):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
