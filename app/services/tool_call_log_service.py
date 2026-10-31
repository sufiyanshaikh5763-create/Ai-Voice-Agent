"""Best-effort, privacy-conscious audit logging for public Sarvam tool routes."""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.client import Client
from app.services.audit_service import record_audit

logger = logging.getLogger(__name__)

MAX_TOOL_LOGS_PER_MINUTE = 60
_invalid_token_lock = threading.Lock()
_last_invalid_token_log = 0.0
_invalid_token_log_interval = 60.0
_legacy_token_lock = threading.Lock()
_last_legacy_token_log = 0.0
_sensitive_key_terms = (
    "token", "secret", "password", "authorization", "apikey", "signature",
)
_phone_key_terms = ("phone", "mobile", "telephone", "tel")
_phone_pattern = re.compile(r"(?<!\w)\+?\d[\d\s().-]{5,}\d(?!\w)")


def _key_name(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _mask_digits(value: str) -> str:
    digits = [index for index, character in enumerate(value) if character.isdigit()]
    if len(digits) < 7:
        return value
    for index in digits[:-4]:
        value = value[:index] + "*" + value[index + 1:]
    return value


def sanitize_payload(value: Any, key: Any = "") -> Any:
    """Drop secret-bearing keys and mask phone-like values recursively."""
    normalized_key = _key_name(key)
    if any(term in normalized_key for term in _sensitive_key_terms):
        return None
    if isinstance(value, dict):
        return {
            str(child_key): sanitize_payload(child_value, child_key)
            for child_key, child_value in value.items()
            if not any(term in _key_name(child_key) for term in _sensitive_key_terms)
        }
    if isinstance(value, list):
        return [sanitize_payload(item, key) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        if any(term in normalized_key for term in _phone_key_terms) or 7 <= len(str(value)) <= 15:
            return _mask_digits(str(value))
    if isinstance(value, str):
        if any(term in normalized_key for term in _phone_key_terms):
            value = _mask_digits(value)
        else:
            value = _phone_pattern.sub(lambda match: _mask_digits(match.group(0)), value)
        settings = get_settings()
        for secret in (
            settings.sarvam_webhook_secret, settings.sarvam_api_key,
            settings.resend_api_key, settings.smtp_password,
            settings.jwt_secret_key,
        ):
            if secret:
                value = value.replace(secret, "[redacted]")
        return value
    return value


def safe_request_id(request, token: str | None = None) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    if request_id and token:
        request_id = request_id.replace(token, "[redacted]")
    return request_id[:255] if request_id else None


def log_invalid_tool_token(reason: str, request_id: str | None = None) -> None:
    """Log invalid credentials at most once per minute without retaining the credential."""
    global _last_invalid_token_log
    now = time.monotonic()
    with _invalid_token_lock:
        if now - _last_invalid_token_log < _invalid_token_log_interval:
            return
        _last_invalid_token_log = now
    logger.warning(
        "Sarvam tool request rejected before tenant authentication: %s [request_id=%s]",
        reason[:80], request_id[:128] if request_id else None,
    )


def log_legacy_shared_token_use(client_id: int, request_id: str | None = None) -> None:
    """Emit a single bounded warning per process/minute without retaining the token."""
    global _last_legacy_token_log
    now = time.monotonic()
    with _legacy_token_lock:
        if now - _last_legacy_token_log < 60.0:
            return
        _last_legacy_token_log = now
    logger.warning(
        "Legacy shared Sarvam tool token used [client_id=%s request_id=%s]",
        client_id, request_id[:128] if request_id else None,
    )


def _tool_lock_key(client_id: int | None) -> int:
    return (0x53415256 << 32) + (client_id or 0)


def _allowed_to_log(db, client_id: int | None, now: datetime) -> bool:
    # Serialize cap checks across workers so concurrent requests cannot bypass the limit.
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"),
               {"lock_key": _tool_lock_key(client_id)})
    predicates = [
        AuditLog.action.like("sarvam_tool.%"),
        AuditLog.created_at >= now - timedelta(minutes=1),
    ]
    predicates.append(AuditLog.client_id.is_(None) if client_id is None
                      else AuditLog.client_id == client_id)
    count = db.scalar(select(func.count(AuditLog.id)).where(*predicates)) or 0
    return count < MAX_TOOL_LOGS_PER_MINUTE


def record_tool_call(
    *,
    client_id: int | None,
    tool: str,
    success: bool,
    error_code: str | None,
    message: str | None,
    appointment_id: int | None,
    duration_ms: int,
    request_id: str | None,
    legacy_shared_token_used: bool = False,
) -> None:
    """Persist one capped tool audit row in its own transaction."""
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        tenant_resolution = "resolved"
        requested_client_id = client_id
        if client_id is not None:
            client = db.get(Client, client_id)
            if client is None:
                client_id = None
                tenant_resolution = "unknown_client_id"
            elif (
                not client.is_active
                or client.status.value != "active"
                or client.access_status.value == "suspended"
            ):
                tenant_resolution = "inactive_client"
        if not _allowed_to_log(db, client_id, now):
            db.rollback()
            return
        level = (
            "info" if success else
            "error" if error_code == "INTERNAL_ERROR" else "warning"
        )
        action = f"sarvam_tool.{tool}"
        details = {
            "tool": tool,
            "success": success,
            "error_code": error_code,
            "duration_ms": max(0, duration_ms),
            "appointment_id": appointment_id,
            "request_id": request_id[:255] if request_id else None,
            "tenant_resolution": tenant_resolution,
            "requested_client_id": requested_client_id,
        }
        if legacy_shared_token_used:
            details["legacy_shared_token_used"] = True
        if legacy_shared_token_used and message is None:
            message = "Legacy shared token used"
        safe_message = sanitize_payload(message)[:255] if message else None
        record_audit(
            db, action, client_id=client_id, details=details,
            level=level, message=safe_message,
        )
        db.commit()


def log_tool_validation_failure(request) -> None:
    path = request.url.path
    match = re.search(
        r"/sarvam/([^/]+)/(\d+)/appointments/(check-slot|book|reschedule|cancel)$", path
    )
    if not match:
        return
    token, raw_client_id, tool = match.groups()
    client_id = int(raw_client_id)
    try:
        with SessionLocal() as db:
            if db.get(Client, client_id) is None:
                client_id = None
    except Exception:
        logger.exception("Could not resolve tenant for Sarvam tool validation audit")
        client_id = None
    record_tool_call(
        client_id=client_id, tool=tool.replace("-", "_"), success=False,
        error_code="VALIDATION_ERROR", message="Validation failed",
        appointment_id=None, duration_ms=0,
        request_id=safe_request_id(request, token),
        legacy_shared_token_used=getattr(
            request.state, "sarvam_legacy_shared_token_used", False
        ),
    )
