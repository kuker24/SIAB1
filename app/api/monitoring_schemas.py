"""Pydantic schemas for monitoring API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ViolationStats(BaseModel):
    total_violations: int
    by_type: Dict[str, int]
    timeline: Dict[str, int]
    top_offenders: List[Dict[str, Any]]


class LiveExamStats(BaseModel):
    exam_id: int
    exam_title: str
    active_participants: int
    completed_participants: int
    total_violations: int
    average_score: float
    average_progress: float
    timestamp: str


class SessionStatus(BaseModel):
    session_id: int
    user_id: int
    user_name: str
    user_class: Optional[str]
    progress: float
    violation_count: int
    start_time: str
    status: str
    ip_address: Optional[str]
    is_online: bool = False
    last_active: Optional[str] = None
    terminated_by_admin: bool = False
    recovery_category: Optional[str] = None
    recovery_message: Optional[str] = None
    allow_continue: bool = False


class DegradeModeUpdate(BaseModel):
    enabled: bool
    reason: Optional[str] = None
    ttl_minutes: int = 120


class AutoRestartScheduleUpdate(BaseModel):
    enabled: bool
    time_wib: str = "00:30"
    restart_buffer_minutes: int = 30
    full_restart: bool = True
    include_data_services: bool = True
    restart_timeout_seconds: int = 300
    scheduled_runs_wib: Optional[List[str]] = None
    replace_runs: bool = False
    reason: Optional[str] = None


class AutoRestartRunRequest(BaseModel):
    reason: Optional[str] = None
    force: bool = True
    dry_run: bool = True


class ResourceModeUpdate(BaseModel):
    mode: str
    reason: Optional[str] = None
    ttl_minutes: int = 120


class AutoIntelligenceControlUpdate(BaseModel):
    auto_mode_enabled: Optional[bool] = None
    auto_heal_enabled: Optional[bool] = None
    force_tick: bool = False
    reason: Optional[str] = None


class AutoIntelligenceRunRequest(BaseModel):
    reason: Optional[str] = None
    force: bool = True
    force_heal: bool = False


class RestartSystemRequest(BaseModel):
    reason: Optional[str] = None
    restart_buffer_minutes: int = 30
    full_restart: bool = True
    include_data_services: bool = True
    restart_timeout_seconds: int = 300
    dry_run: bool = False


class KickStudentRequest(BaseModel):
    reason: str = "Dikeluarkan oleh pengawas"


class SessionResetRequest(BaseModel):
    reason: Optional[str] = None


class SessionOverrideResetRequest(BaseModel):
    reason: Optional[str] = None
    reset_violation_count: bool = True


class RecoveryCandidate(BaseModel):
    session_id: int
    user_id: int
    user_name: str
    user_class: Optional[str] = None
    status: str
    violation_count: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    recovery_category: str = "unknown"
    recovery_message: str = ""
    submit_mode: str = "unknown"
    reason_bucket: str = "unknown"
    reason_label: str = "Perlu verifikasi"
    allow_continue: bool = False
    can_override: bool = False
    last_event_type: Optional[str] = None
    last_event_at: Optional[str] = None


class RecoveryCandidatesResponse(BaseModel):
    exam_id: int
    exam_title: str
    total_candidates: int
    summary: Dict[str, int]
    candidates: List[RecoveryCandidate]
