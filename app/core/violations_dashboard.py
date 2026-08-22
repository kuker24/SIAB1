"""
Violation dashboard query + payload helpers.

Separated from API router to keep endpoint modules focused on transport/auth concerns.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exam import Exam
from app.models.session import ExamLog, ExamSession
from app.models.user import User
from app.core.security import is_teacher_scope_restricted
from app.core.violation_metadata import (
    KNOWN_VIOLATION_EVENT_TYPES,
    canonical_violation_event_type,
    get_violation_explanation,
    get_violation_metadata,
    strip_violation_prefix,
)
from app.core.violation_scoring import VIOLATION_DISABLED_EVENT_TYPES_SQL

WIB_TIMEZONE = timezone(timedelta(hours=7))
VIOLATION_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _counted_for_score_condition():
    """
    Count only violations that contribute to scoring/policy.
    Legacy logs without this key are treated as counted.
    """
    counted_text = func.lower(
        func.coalesce(ExamLog.event_data["counted_for_score"].astext, "true")
    )
    disabled_types = VIOLATION_DISABLED_EVENT_TYPES_SQL
    return and_(
        counted_text.in_(("true", "t", "1", "yes", "y", "on")),
        func.lower(ExamLog.event_type).notin_(disabled_types),
    )


def _visible_violation_condition(include_warning_only: bool = True):
    """
    Visibility condition for violation dashboard.
    - include_warning_only=True  -> show counted + warning-only violations (except disabled types)
    - include_warning_only=False -> show only counted violations (legacy behavior)
    """
    disabled_types = VIOLATION_DISABLED_EVENT_TYPES_SQL
    if include_warning_only:
        return func.lower(ExamLog.event_type).notin_(disabled_types)
    return _counted_for_score_condition()


def _violation_event_type_condition():
    return or_(
        ExamLog.event_type.ilike("violation_%"),
        func.lower(ExamLog.event_type).in_(KNOWN_VIOLATION_EVENT_TYPES),
    )


def _base_violations_filters(
    *,
    date_from: datetime,
    date_to: datetime,
    include_warning_only: bool = True,
):
    return (
        ExamLog.created_at >= date_from,
        ExamLog.created_at <= date_to,
        Exam.is_deleted == False,
        _visible_violation_condition(include_warning_only=include_warning_only),
        _violation_event_type_condition(),
    )


def _coerce_event_data_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "f", "0", "no", "n", "off", ""}:
            return False
    return default


def _ensure_aware_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        # Admin UI date filters are entered in WIB local calendar dates.
        # Treat naive datetimes as WIB to avoid shifting "hari ini" window by +7 hours.
        return value.replace(tzinfo=WIB_TIMEZONE)
    return value


def _coerce_violations_date_range(
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> tuple[datetime, datetime]:
    effective_from = _ensure_aware_datetime(date_from) or (
        datetime.now(timezone.utc) - timedelta(days=7)
    )
    effective_to = _ensure_aware_datetime(date_to) or datetime.now(timezone.utc)
    # Normalize to UTC for DB query consistency.
    return effective_from.astimezone(timezone.utc), effective_to.astimezone(timezone.utc)


def _format_wib_datetime(value: Optional[datetime]) -> str:
    aware_value = _ensure_aware_datetime(value)
    if not aware_value:
        return "-"
    return aware_value.astimezone(WIB_TIMEZONE).strftime("%d %b %Y %H:%M WIB")


def _compact_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return " ".join(text.split())


def _truncate_text(value: str, limit: int = 220) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _format_date_range_label(date_from: datetime, date_to: datetime) -> str:
    start = _ensure_aware_datetime(date_from).astimezone(WIB_TIMEZONE)
    end = _ensure_aware_datetime(date_to).astimezone(WIB_TIMEZONE)
    if start.date() == end.date():
        return (
            f"{start.strftime('%d %b %Y')} "
            f"({start.strftime('%H:%M')} - {end.strftime('%H:%M')} WIB)"
        )
    return (
        f"{start.strftime('%d %b %Y %H:%M WIB')} "
        f"s/d {end.strftime('%d %b %Y %H:%M WIB')}"
    )


def _summarize_violation_event_data(event_data: Dict[str, Any]) -> str:
    if not isinstance(event_data, dict):
        return ""

    fragments: List[str] = []

    details = _compact_text(event_data.get("details"))
    if details:
        fragments.append(details)

    action = _compact_text(event_data.get("action")).replace("_", " ")
    if action and action.lower() not in details.lower():
        fragments.append(f"Aksi: {action}")

    source = _compact_text(event_data.get("source")).replace("_", " ")
    if source:
        fragments.append(f"Sumber: {source}")

    package_name = _compact_text(event_data.get("package_name") or event_data.get("package"))
    if package_name:
        fragments.append(f"Paket: {package_name}")

    overlay_apps = event_data.get("overlay_apps") or []
    if isinstance(overlay_apps, list) and overlay_apps:
        cleaned_apps = [_compact_text(item) for item in overlay_apps if _compact_text(item)]
        if cleaned_apps:
            extra = len(cleaned_apps) - 3
            label = ", ".join(cleaned_apps[:3])
            if extra > 0:
                label = f"{label} +{extra} lainnya"
            fragments.append(f"App: {label}")

    accessibility_services = event_data.get("accessibility_services") or []
    if isinstance(accessibility_services, list) and accessibility_services:
        cleaned_services = [
            _compact_text(item) for item in accessibility_services if _compact_text(item)
        ]
        if cleaned_services:
            extra = len(cleaned_services) - 2
            label = ", ".join(cleaned_services[:2])
            if extra > 0:
                label = f"{label} +{extra} lainnya"
            fragments.append(f"Layanan: {label}")

    resolution = _compact_text(event_data.get("screen_resolution"))
    if resolution and resolution.lower() != "mobile":
        fragments.append(f"Resolusi: {resolution}")

    return _truncate_text(" | ".join(fragments))


def _sort_by_violation_weight(item: Dict[str, Any]) -> tuple[int, int, str]:
    severity_score = VIOLATION_SEVERITY_ORDER.get(
        str(item.get("severity") or "").lower(),
        0,
    )
    return (
        int(item.get("count") or 0),
        severity_score,
        str(item.get("label") or item.get("violation_type") or ""),
    )


def _build_violation_record(log: ExamLog) -> Optional[Dict[str, Any]]:
    if not log.session or not log.session.user:
        return None

    log_event_data = log.event_data if isinstance(log.event_data, dict) else {}
    normalized_event_type = canonical_violation_event_type(
        log.event_type,
        log_event_data,
        assume_violation=False,
    )
    if not normalized_event_type:
        return None

    event_type = strip_violation_prefix(normalized_event_type)
    event_meta = get_violation_metadata(normalized_event_type, log_event_data)
    created_at = _ensure_aware_datetime(log.created_at) or datetime.now(timezone.utc)
    exam_title = (
        (log.session.exam.title if log.session.exam else None)
        or log.session.archived_exam_title
        or f"Ujian #{log.session.exam_id}"
    )
    participant_name = log.session.user.full_name or log.session.user.username
    detail_summary = _summarize_violation_event_data(log_event_data)
    counted_for_score = _coerce_event_data_bool(
        log_event_data.get("counted_for_score"),
        default=True,
    )

    return {
        "id": log.id,
        "exam_id": log.session.exam_id,
        "exam_title": exam_title,
        "exam_session_id": log.session_id,
        "session_id": log.session_id,
        "user_id": log.session.user.id,
        "name": participant_name,
        "username": log.session.user.username,
        "class": log.session.user.student_class,
        "event_type": normalized_event_type,
        "violation_type": event_type,
        "label": event_meta["label"],
        "severity": event_meta["severity"],
        "category": event_meta["category"],
        "description": event_meta["description"],
        "message": f"{participant_name} melakukan {event_meta['label']}",
        "detail_summary": detail_summary,
        "source": _compact_text(log_event_data.get("source")) or "unknown",
        "created_at": created_at.isoformat(),
        "created_at_display": _format_wib_datetime(created_at),
        "event_data": log_event_data,
        "counted_for_score": counted_for_score,
    }


def _build_violations_dashboard_payload(
    logs: List[ExamLog],
    *,
    exam_id: Optional[int],
    date_from: datetime,
    date_to: datetime,
    selected_exam_title: Optional[str] = None,
) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    timeline: Dict[str, int] = {}
    type_aggregates: Dict[str, Dict[str, Any]] = {}
    user_violations: Dict[int, Dict[str, Any]] = {}
    violations: List[Dict[str, Any]] = []
    affected_sessions = set()
    affected_exams = set()

    for log in logs:
        violation_record = _build_violation_record(log)
        if not violation_record:
            continue

        event_type = violation_record["violation_type"]
        by_type[event_type] = by_type.get(event_type, 0) + 1

        created_at = (
            _parse_iso_timestamp(violation_record["created_at"])
            or datetime.now(timezone.utc)
        )
        hour_bucket = created_at.astimezone(WIB_TIMEZONE).strftime("%Y-%m-%d %H:00")
        timeline[hour_bucket] = timeline.get(hour_bucket, 0) + 1

        affected_sessions.add(violation_record["session_id"])
        if violation_record["exam_id"]:
            affected_exams.add(violation_record["exam_id"])
        violations.append(violation_record)

        user_id = int(violation_record["user_id"])
        offender_bucket = user_violations.setdefault(
            user_id,
            {
                "user_id": user_id,
                "name": violation_record["name"],
                "username": violation_record["username"],
                "class": violation_record["class"],
                "count": 0,
                "exam_titles": set(),
                "type_breakdown_map": {},
                "recent_violations": [],
                "latest_violation_at": "",
                "latest_violation_at_display": "-",
            },
        )
        offender_bucket["count"] += 1
        offender_bucket["exam_titles"].add(violation_record["exam_title"])
        if violation_record["created_at"] > offender_bucket["latest_violation_at"]:
            offender_bucket["latest_violation_at"] = violation_record["created_at"]
            offender_bucket["latest_violation_at_display"] = violation_record[
                "created_at_display"
            ]
        offender_bucket["recent_violations"].append(
            {
                "created_at": violation_record["created_at"],
                "created_at_display": violation_record["created_at_display"],
                "label": violation_record["label"],
                "violation_type": event_type,
                "severity": violation_record["severity"],
                "exam_title": violation_record["exam_title"],
                "detail_summary": violation_record["detail_summary"],
            }
        )
        offender_type_entry = offender_bucket["type_breakdown_map"].setdefault(
            event_type,
            {
                "violation_type": event_type,
                "label": violation_record["label"],
                "severity": violation_record["severity"],
                "category": violation_record["category"],
                "count": 0,
                "last_seen_at": "",
                "last_seen_at_display": "-",
            },
        )
        offender_type_entry["count"] += 1
        if violation_record["created_at"] > offender_type_entry["last_seen_at"]:
            offender_type_entry["last_seen_at"] = violation_record["created_at"]
            offender_type_entry["last_seen_at_display"] = violation_record[
                "created_at_display"
            ]

        type_bucket = type_aggregates.setdefault(
            event_type,
            {
                "violation_type": event_type,
                "label": violation_record["label"],
                "severity": violation_record["severity"],
                "category": violation_record["category"],
                "description": violation_record["description"],
                "count": 0,
                "offender_ids": set(),
                "offenders_map": {},
                "recent_violations": [],
            },
        )
        type_bucket["count"] += 1
        type_bucket["offender_ids"].add(user_id)
        type_bucket["recent_violations"].append(
            {
                "created_at": violation_record["created_at"],
                "created_at_display": violation_record["created_at_display"],
                "name": violation_record["name"],
                "username": violation_record["username"],
                "class": violation_record["class"],
                "exam_title": violation_record["exam_title"],
                "detail_summary": violation_record["detail_summary"],
            }
        )
        type_offender_entry = type_bucket["offenders_map"].setdefault(
            user_id,
            {
                "user_id": user_id,
                "name": violation_record["name"],
                "username": violation_record["username"],
                "class": violation_record["class"],
                "count": 0,
                "exam_titles": set(),
                "latest_violation_at": "",
                "latest_violation_at_display": "-",
            },
        )
        type_offender_entry["count"] += 1
        type_offender_entry["exam_titles"].add(violation_record["exam_title"])
        if violation_record["created_at"] > type_offender_entry["latest_violation_at"]:
            type_offender_entry["latest_violation_at"] = violation_record["created_at"]
            type_offender_entry["latest_violation_at_display"] = violation_record[
                "created_at_display"
            ]

    violations.sort(key=lambda item: item["created_at"], reverse=True)

    offender_details: List[Dict[str, Any]] = []
    for offender in user_violations.values():
        type_breakdown = sorted(
            offender["type_breakdown_map"].values(),
            key=_sort_by_violation_weight,
            reverse=True,
        )
        offender_details.append(
            {
                "user_id": offender["user_id"],
                "name": offender["name"],
                "username": offender["username"],
                "class": offender["class"],
                "count": offender["count"],
                "exam_titles": sorted(offender["exam_titles"]),
                "latest_violation_at": offender["latest_violation_at"],
                "latest_violation_at_display": offender["latest_violation_at_display"],
                "type_breakdown": type_breakdown,
                "recent_violations": sorted(
                    offender["recent_violations"],
                    key=lambda item: item["created_at"],
                    reverse=True,
                )[:4],
            }
        )

    offender_details.sort(
        key=lambda item: (int(item["count"]), item["latest_violation_at"], item["name"]),
        reverse=True,
    )

    type_breakdown: List[Dict[str, Any]] = []
    for item in type_aggregates.values():
        offenders = []
        for offender in item["offenders_map"].values():
            offenders.append(
                {
                    "user_id": offender["user_id"],
                    "name": offender["name"],
                    "username": offender["username"],
                    "class": offender["class"],
                    "count": offender["count"],
                    "exam_titles": sorted(offender["exam_titles"]),
                    "latest_violation_at": offender["latest_violation_at"],
                    "latest_violation_at_display": offender[
                        "latest_violation_at_display"
                    ],
                }
            )
        offenders.sort(
            key=lambda offender: (
                int(offender["count"]),
                offender["latest_violation_at"],
                offender["name"],
            ),
            reverse=True,
        )
        recent_violations = sorted(
            item["recent_violations"],
            key=lambda violation: violation["created_at"],
            reverse=True,
        )[:5]
        type_breakdown.append(
            {
                "violation_type": item["violation_type"],
                "label": item["label"],
                "severity": item["severity"],
                "category": item["category"],
                "description": item["description"],
                "explanation": get_violation_explanation(
                    item["violation_type"],
                    assume_violation=True,
                ),
                "count": item["count"],
                "offender_count": len(item["offender_ids"]),
                "offenders": offenders,
                "recent_violations": recent_violations,
            }
        )

    type_breakdown.sort(key=_sort_by_violation_weight, reverse=True)
    average_per_session = (
        round(len(violations) / len(affected_sessions), 2)
        if affected_sessions
        else 0
    )

    generated_at = datetime.now(timezone.utc)
    return {
        "total_violations": len(violations),
        "by_type": by_type,
        "type_details": {
            violation_type: get_violation_metadata(
                violation_type,
                assume_violation=True,
            )
            for violation_type in by_type.keys()
        },
        "type_breakdown": type_breakdown,
        "top_offenders": offender_details[:10],
        "offender_details": offender_details,
        "unique_offender_count": len(user_violations),
        "timeline": dict(sorted(timeline.items())),
        "violations": violations,
        "unique_exam_count": len(affected_exams),
        "affected_session_count": len(affected_sessions),
        "average_per_session": average_per_session,
        "selected_exam_title": selected_exam_title,
        "date_range_label": _format_date_range_label(date_from, date_to),
        "generated_at": generated_at.isoformat(),
        "generated_at_display": _format_wib_datetime(generated_at),
        "filters": {
            "exam_id": exam_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def _build_violations_query(
    *,
    exam_id: Optional[int],
    date_from: datetime,
    date_to: datetime,
    current_user: User,
    include_warning_only: bool = True,
):
    query = (
        select(ExamLog)
        .options(
            selectinload(ExamLog.session).selectinload(ExamSession.user),
            selectinload(ExamLog.session).selectinload(ExamSession.exam),
        )
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            *_base_violations_filters(
                date_from=date_from,
                date_to=date_to,
                include_warning_only=include_warning_only,
            )
        )
    )
    if exam_id:
        query = query.where(ExamSession.exam_id == exam_id)
    if is_teacher_scope_restricted(current_user):
        query = query.where(Exam.creator_id == current_user.id)
    return query


def _apply_violations_scope(query, *, exam_id: Optional[int], current_user: User):
    if exam_id:
        query = query.where(ExamSession.exam_id == exam_id)
    if is_teacher_scope_restricted(current_user):
        query = query.where(Exam.creator_id == current_user.id)
    return query


async def _build_violations_summary_payload(
    db: AsyncSession,
    *,
    exam_id: Optional[int],
    date_from: datetime,
    date_to: datetime,
    current_user: User,
    include_warning_only: bool = True,
) -> Dict[str, Any]:
    grouped_query = (
        select(
            ExamSession.user_id,
            ExamLog.event_type,
            func.count(ExamLog.id).label("count"),
        )
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            *_base_violations_filters(
                date_from=date_from,
                date_to=date_to,
                include_warning_only=include_warning_only,
            )
        )
        .group_by(ExamSession.user_id, ExamLog.event_type)
    )
    distinct_session_query = (
        select(func.count(func.distinct(ExamLog.session_id)))
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            *_base_violations_filters(
                date_from=date_from,
                date_to=date_to,
                include_warning_only=include_warning_only,
            )
        )
    )
    grouped_query = _apply_violations_scope(
        grouped_query,
        exam_id=exam_id,
        current_user=current_user,
    )
    distinct_session_query = _apply_violations_scope(
        distinct_session_query,
        exam_id=exam_id,
        current_user=current_user,
    )

    grouped_result = await db.execute(grouped_query)
    grouped_rows = grouped_result.fetchall()
    by_user: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    total_violations = 0

    for user_id, event_type, count in grouped_rows:
        safe_count = int(count or 0)
        if safe_count <= 0:
            continue
        total_violations += safe_count

        if user_id is not None:
            user_key = str(int(user_id))
            by_user[user_key] = by_user.get(user_key, 0) + safe_count

        normalized_type = canonical_violation_event_type(
            event_type,
            {},
            assume_violation=True,
        ) or event_type
        violation_type = strip_violation_prefix(normalized_type)
        by_type[violation_type] = by_type.get(violation_type, 0) + safe_count

    affected_session_count_result = await db.execute(distinct_session_query)
    affected_session_count = int(affected_session_count_result.scalar() or 0)
    generated_at = datetime.now(timezone.utc)
    return {
        "summary_only": True,
        "exam_id": exam_id,
        "total_violations": total_violations,
        "unique_offender_count": len(by_user),
        "affected_session_count": affected_session_count,
        "by_type": by_type,
        "by_user": by_user,
        "generated_at": generated_at.isoformat(),
        "filters": {
            "exam_id": exam_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


async def _build_violations_aggregate_payload(
    db: AsyncSession,
    *,
    exam_id: Optional[int],
    date_from: datetime,
    date_to: datetime,
    current_user: User,
    include_warning_only: bool = True,
    selected_exam_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Build aggregate-first violation dashboard without loading individual logs."""
    base_filters = _base_violations_filters(
        date_from=date_from,
        date_to=date_to,
        include_warning_only=include_warning_only,
    )
    type_query = (
        select(
            ExamLog.event_type,
            func.count(ExamLog.id).label("count"),
            func.count(func.distinct(ExamSession.user_id)).label("offender_count"),
            func.max(ExamLog.created_at).label("last_seen_at"),
        )
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(*base_filters)
        .group_by(ExamLog.event_type)
        .order_by(desc("count"))
        .limit(50)
    )
    offender_query = (
        select(
            ExamSession.user_id,
            User.full_name,
            User.username,
            User.student_class,
            func.count(ExamLog.id).label("count"),
            func.max(ExamLog.created_at).label("latest_violation_at"),
        )
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .join(User, User.id == ExamSession.user_id)
        .where(*base_filters)
        .group_by(ExamSession.user_id, User.full_name, User.username, User.student_class)
        .order_by(desc("count"), desc("latest_violation_at"))
        .limit(10)
    )
    timeline_query = (
        select(
            func.date_trunc("hour", ExamLog.created_at).label("hour_bucket"),
            func.count(ExamLog.id).label("count"),
        )
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(*base_filters)
        .group_by("hour_bucket")
        .order_by("hour_bucket")
    )
    distinct_query = (
        select(
            func.count(ExamLog.id).label("total_violations"),
            func.count(func.distinct(ExamSession.user_id)).label("unique_offenders"),
            func.count(func.distinct(ExamLog.session_id)).label("affected_sessions"),
            func.count(func.distinct(ExamSession.exam_id)).label("unique_exams"),
        )
        .join(ExamSession, ExamLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(*base_filters)
    )

    type_query = _apply_violations_scope(type_query, exam_id=exam_id, current_user=current_user)
    offender_query = _apply_violations_scope(
        offender_query,
        exam_id=exam_id,
        current_user=current_user,
    )
    timeline_query = _apply_violations_scope(
        timeline_query,
        exam_id=exam_id,
        current_user=current_user,
    )
    distinct_query = _apply_violations_scope(
        distinct_query,
        exam_id=exam_id,
        current_user=current_user,
    )

    type_rows = (await db.execute(type_query)).all()
    offender_rows = (await db.execute(offender_query)).all()
    timeline_rows = (await db.execute(timeline_query)).all()
    totals = (await db.execute(distinct_query)).mappings().one()

    by_type: Dict[str, int] = {}
    type_breakdown: List[Dict[str, Any]] = []
    for event_type, count, offender_count, last_seen_at in type_rows:
        normalized_type = canonical_violation_event_type(
            event_type,
            {},
            assume_violation=True,
        ) or event_type
        violation_type = strip_violation_prefix(normalized_type)
        safe_count = int(count or 0)
        by_type[violation_type] = by_type.get(violation_type, 0) + safe_count
        meta = get_violation_metadata(normalized_type, assume_violation=True)
        type_breakdown.append(
            {
                "violation_type": violation_type,
                "label": meta["label"],
                "severity": meta["severity"],
                "category": meta["category"],
                "description": meta["description"],
                "explanation": get_violation_explanation(violation_type, assume_violation=True),
                "count": safe_count,
                "offender_count": int(offender_count or 0),
                "last_seen_at": (
                    _ensure_aware_datetime(last_seen_at).isoformat() if last_seen_at else ""
                ),
                "last_seen_at_display": _format_wib_datetime(last_seen_at),
                "offenders": [],
                "recent_violations": [],
            }
        )

    top_offenders: List[Dict[str, Any]] = []
    for user_id, full_name, username, student_class, count, latest_violation_at in offender_rows:
        name = full_name or username or f"User #{user_id}"
        top_offenders.append(
            {
                "user_id": int(user_id),
                "name": name,
                "username": username,
                "class": student_class,
                "count": int(count or 0),
                "exam_titles": [],
                "latest_violation_at": (
                    _ensure_aware_datetime(latest_violation_at).isoformat()
                    if latest_violation_at
                    else ""
                ),
                "latest_violation_at_display": _format_wib_datetime(latest_violation_at),
                "type_breakdown": [],
                "recent_violations": [],
            }
        )

    timeline: Dict[str, int] = {}
    for hour_bucket, count in timeline_rows:
        aware_bucket = _ensure_aware_datetime(hour_bucket) or datetime.now(timezone.utc)
        timeline[aware_bucket.astimezone(WIB_TIMEZONE).strftime("%Y-%m-%d %H:00")] = int(
            count or 0
        )

    total_violations = int(totals["total_violations"] or 0)
    affected_session_count = int(totals["affected_sessions"] or 0)
    generated_at = datetime.now(timezone.utc)
    return {
        "aggregate_only": True,
        "summary_only": True,
        "total_violations": total_violations,
        "by_type": by_type,
        "type_details": {
            violation_type: get_violation_metadata(violation_type, assume_violation=True)
            for violation_type in by_type.keys()
        },
        "type_breakdown": type_breakdown,
        "top_offenders": top_offenders,
        "offender_details": top_offenders,
        "unique_offender_count": int(totals["unique_offenders"] or 0),
        "timeline": timeline,
        "violations": [],
        "unique_exam_count": int(totals["unique_exams"] or 0),
        "affected_session_count": affected_session_count,
        "average_per_session": (
            round(total_violations / affected_session_count, 2)
            if affected_session_count
            else 0
        ),
        "selected_exam_title": selected_exam_title,
        "date_range_label": _format_date_range_label(date_from, date_to),
        "generated_at": generated_at.isoformat(),
        "generated_at_display": _format_wib_datetime(generated_at),
        "filters": {
            "exam_id": exam_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "detail_level": "summary",
        },
    }


async def _resolve_selected_exam_title(
    db: AsyncSession,
    *,
    exam_id: Optional[int],
    current_user: User,
) -> Optional[str]:
    if not exam_id:
        return None
    query = select(Exam.title).where(Exam.id == exam_id, Exam.is_deleted == False)
    if is_teacher_scope_restricted(current_user):
        query = query.where(Exam.creator_id == current_user.id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


def _build_violations_export_filename() -> str:
    timestamp = datetime.now(WIB_TIMEZONE).strftime("%Y%m%d_%H%M%S")
    return f"violations_report_{timestamp}.pdf"


__all__ = [
    "_build_violations_aggregate_payload",
    "_build_violations_dashboard_payload",
    "_build_violations_export_filename",
    "_build_violations_query",
    "_build_violations_summary_payload",
    "_coerce_violations_date_range",
    "_resolve_selected_exam_title",
]
