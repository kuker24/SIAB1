"""
WebSocket API for real-time exam monitoring.
Uses Redis Pub/Sub for multi-replica support.
"""
import json
import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from app.database import async_session_read
from app.models.session import ExamSession
from app.models.exam import Exam
from app.core.cache import is_freeze_mode_enabled
from app.core.redis_pubsub import get_redis, publish_message, update_session_activity
from app.core.security import (
    AuthenticatedUser,
    decode_token,
    is_freeze_exempt_identity,
    is_teacher_scope_restricted,
)
from app.core.roles import is_admin_scope_role, is_teacher_scope_role

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


@router.get("/ws/health")
async def websocket_health():
    """Health check endpoint for WebSocket service."""
    return {"status": "ok", "message": "WebSocket service is running"}


class WebSocketManager:
    """
    WebSocket manager with Redis Pub/Sub for multi-replica support.

    IMPORTANT: Because we use replicas: 3 in Docker, we MUST use Redis
    to broadcast messages between containers. Direct WebSocket sending
    only works for connections on the same container.
    """

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.listener_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, connection_id: str, channel: str):
        """Connect WebSocket and subscribe to Redis channel."""
        await websocket.accept()
        self.active_connections[connection_id] = websocket

        # Start Redis listener for this connection
        task = asyncio.create_task(self._listen_redis(connection_id, channel))
        self.listener_tasks[connection_id] = task

    async def disconnect(self, connection_id: str):
        """Disconnect WebSocket and cleanup."""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        if connection_id in self.listener_tasks:
            self.listener_tasks[connection_id].cancel()
            del self.listener_tasks[connection_id]

    async def send_personal_message(self, message: dict, connection_id: str):
        """Send message to specific connection."""
        if connection_id in self.active_connections:
            await self.active_connections[connection_id].send_json(message)

    async def broadcast_via_redis(self, channel: str, message: dict):
        """
        Broadcast message to all subscribers via Redis Pub/Sub.
        This ensures all replicas receive the message.
        """
        await publish_message(channel, message)

    async def _listen_redis(self, connection_id: str, channel: str):
        """Listen to Redis channel and forward to WebSocket."""
        logger.debug("Starting Redis listener for %s on channel '%s'", connection_id, channel)
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            logger.debug("Subscribed to Redis channel '%s'", channel)

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON payload on channel '%s'", channel)
                        continue

                    if connection_id in self.active_connections:
                        await self.active_connections[connection_id].send_json(data)

        except asyncio.CancelledError:
            logger.debug("Redis listener cancelled for %s", connection_id)
        except (RedisTimeoutError, RedisConnectionError) as exc:
            logger.warning(
                "Redis listener transient disconnect for %s on %s: %s",
                connection_id,
                channel,
                exc,
            )
        except Exception as e:
            # Common websocket close/disconnect paths should not pollute ERROR logs.
            if e.__class__.__name__ in {
                "WebSocketDisconnect",
                "ClientDisconnected",
                "ConnectionClosedOK",
                "ConnectionClosedError",
                "IncompleteReadError",
            }:
                logger.debug("Redis listener closed for %s: %s", connection_id, e)
            else:
                logger.error(
                    "Redis listener error for %s: %s",
                    connection_id,
                    e,
                    exc_info=True,
                )
        finally:
            if pubsub is not None:
                with suppress(Exception):
                    await pubsub.unsubscribe(channel)
                try:
                    await pubsub.close()
                except Exception as e:
                    logger.warning(f"Error closing pubsub for {connection_id}: {e}")


ws_manager = WebSocketManager()


async def _ws_close(websocket: WebSocket, code: int, reason: str) -> None:
    """Best-effort close helper for unauthorized/forbidden WS connections."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception as exc:
        logger.debug("Failed to close websocket gracefully: %s", exc)


def _extract_ws_token(websocket: WebSocket) -> str | None:
    """Get auth token from query string (?token=...) or Authorization header."""
    query_token = websocket.query_params.get("token")
    if query_token:
        return query_token

    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return None


async def _authenticate_ws_user(websocket: WebSocket) -> AuthenticatedUser | None:
    """Authenticate websocket user from JWT token without DB lookup."""
    token = _extract_ws_token(websocket)
    if not token:
        await _ws_close(websocket, 4401, "Missing websocket token")
        return None

    token_data = decode_token(token, verify_exp=True)
    if not token_data:
        await _ws_close(websocket, 4401, "Invalid or expired websocket token")
        return None

    user = AuthenticatedUser(
        id=token_data.user_id,
        username=token_data.username,
        full_name=token_data.full_name or token_data.username,
        role=token_data.role,
        student_class=token_data.student_class,
        job_title=token_data.job_title,
        is_active=bool(token_data.is_active) if token_data.is_active is not None else True,
        profile_picture=None,
        last_login=None,
    )
    if not user.is_active:
        await _ws_close(websocket, 4401, "Unauthorized websocket user")
        return None

    try:
        freeze_enabled = await is_freeze_mode_enabled()
    except Exception:
        freeze_enabled = False
    if freeze_enabled and not is_freeze_exempt_identity(user.role, user.username, user.job_title):
        await _ws_close(websocket, 4403, "System freeze mode active")
        return None

    return user


@router.websocket("/ws/exam/{exam_id}/{user_id}")
async def exam_websocket(
    websocket: WebSocket,
    exam_id: int,
    user_id: str
):
    """
    WebSocket endpoint for student exam session.

    Receives:
    - Student activity updates
    - Heartbeat pings

    Sends:
    - Time sync updates
    - Force submit commands
    - Admin messages
    """
    async with async_session_read() as db:
        current_user = await _authenticate_ws_user(websocket)
        if not current_user:
            return
        if current_user.role not in ("student", "guruplus"):
            await _ws_close(websocket, 4403, "Only exam participants can access exam websocket")
            return
        if str(current_user.id) != str(user_id):
            await _ws_close(websocket, 4403, "Websocket user mismatch")
            return

        # IMPORTANT: DB session is short-lived here. Keeping it open for the full
        # websocket lifetime can leave "idle in transaction" sessions in PostgreSQL.
        session_result = await db.execute(
            select(ExamSession.id).where(
                ExamSession.exam_id == exam_id,
                ExamSession.user_id == current_user.id,
                ExamSession.status.in_(["in_progress", "paused"])
            )
        )
        if session_result.scalar_one_or_none() is None:
            await _ws_close(websocket, 4403, "No active session for this exam")
            return

    connection_id = f"student_{exam_id}_{current_user.id}"
    channel = f"exam_student_{exam_id}_{current_user.id}"

    connected = False
    await ws_manager.connect(websocket, connection_id, channel)
    connected = True

    # Notify admin of connection (Online Status)
    await ws_manager.broadcast_via_redis(f"exam_monitor_{exam_id}", {
        "type": "student_connected",
        "user_id": current_user.id,
        "exam_id": exam_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Update Heartbeat
            try:
                await update_session_activity(exam_id, current_user.id, {
                    "last_active": datetime.now(timezone.utc).isoformat(),
                    "status": "online"
                })
            except Exception as e:
                logger.error(f"Failed to update heartbeat: {e}")

            # Broadcast student activity to admin monitoring
            await ws_manager.broadcast_via_redis(f"exam_monitor_{exam_id}", {
                "type": "student_activity",
                "user_id": current_user.id,
                "exam_id": exam_id,
                "data": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    except WebSocketDisconnect:
        logger.info("Student websocket disconnected exam_id=%s user_id=%s", exam_id, current_user.id)
    except Exception as exc:
        logger.error("Student websocket error exam_id=%s user_id=%s: %s", exam_id, current_user.id, exc, exc_info=True)
    finally:
        if connected:
            await ws_manager.disconnect(connection_id)
            # Notify admin of disconnect
            await ws_manager.broadcast_via_redis(f"exam_monitor_{exam_id}", {
                "type": "student_disconnected",
                "user_id": current_user.id,
                "exam_id": exam_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })


@router.websocket("/ws/monitor/{exam_id}")
async def monitor_websocket(
    websocket: WebSocket,
    exam_id: int
):
    """
    WebSocket endpoint for admin/teacher exam monitoring.

    Receives all student activities for the exam in real-time:
    - Student starts/ends exam
    - Violation alerts
    - Answer submissions
    - Disconnections
    """
    async with async_session_read() as db:
        current_user = await _authenticate_ws_user(websocket)
        if not current_user:
            return
        if not is_teacher_scope_role(current_user.role):
            await _ws_close(websocket, 4403, "Only teacher/admin/developer can access monitor websocket")
            return

        exam_result = await db.execute(select(Exam).where(Exam.id == exam_id))
        exam = exam_result.scalar_one_or_none()
        if not exam:
            await _ws_close(websocket, 4404, "Exam not found")
            return
        if is_teacher_scope_restricted(current_user) and exam.creator_id != current_user.id:
            await _ws_close(websocket, 4403, "Not authorized to monitor this exam")
            return

    connection_id = f"monitor_{exam_id}_{current_user.id}_{id(websocket)}"
    channel = f"exam_monitor_{exam_id}"

    connected = False
    await ws_manager.connect(websocket, connection_id, channel)
    connected = True

    try:
        while True:
            # Keep connection alive and receive admin commands
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Admin can send commands to students
            if message.get("type") == "broadcast_to_all":
                await ws_manager.broadcast_via_redis(f"exam_broadcast_{exam_id}", {
                    "type": "admin_message",
                    "message": message.get("message"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            elif message.get("type") == "force_submit":
                target_user = message.get("user_id")
                await ws_manager.broadcast_via_redis(f"exam_student_{exam_id}_{target_user}", {
                    "type": "force_submit",
                    "reason": message.get("reason", "Dikumpulkan oleh pengawas"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            # Force kick - remove student from exam immediately
            elif message.get("type") == "force_kick":
                target_user = message.get("user_id")
                reason = message.get("reason", "Dikeluarkan oleh pengawas")

                # Send kick command to student's device
                await ws_manager.broadcast_via_redis(f"exam_student_{exam_id}_{target_user}", {
                    "type": "force_kick",
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

                # Notify monitor that student was kicked
                await ws_manager.broadcast_via_redis(f"exam_monitor_{exam_id}", {
                    "type": "student_kicked",
                    "user_id": target_user,
                    "reason": reason,
                    "kicked_by": current_user.username,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

                logger.info(f"Force kicked user {target_user} from exam {exam_id}: {reason}")

    except WebSocketDisconnect:
        logger.info("Monitor websocket disconnected exam_id=%s user=%s", exam_id, current_user.username)
    except Exception as exc:
        logger.error("Monitor websocket error exam_id=%s user=%s: %s", exam_id, current_user.username, exc, exc_info=True)
    finally:
        if connected:
            await ws_manager.disconnect(connection_id)


@router.websocket("/ws/admin")
async def admin_websocket(
    websocket: WebSocket
):
    """
    Global admin WebSocket for receiving all security events.
    """
    current_user = await _authenticate_ws_user(websocket)
    if not current_user:
        return
    if not is_admin_scope_role(current_user.role):
        await _ws_close(websocket, 4403, "Only admin/developer can access admin websocket")
        return

    connection_id = f"admin_{current_user.id}_{id(websocket)}"
    channel = "security_events"

    connected = False
    await ws_manager.connect(websocket, connection_id, channel)
    connected = True

    try:
        while True:
            await websocket.receive_text()  # Keep alive

    except WebSocketDisconnect:
        logger.info("Admin websocket disconnected user=%s", current_user.username)
    except Exception as exc:
        logger.error("Admin websocket error user=%s: %s", current_user.username, exc, exc_info=True)
    finally:
        if connected:
            await ws_manager.disconnect(connection_id)
