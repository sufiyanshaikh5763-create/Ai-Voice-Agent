"""Staff PIN management, verification, encryption and elevation."""
import hmac
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, PinLockedError, PinWrongError
from app.core.security import create_elevation_token
from app.models.staff_pin import PinAttempt, StaffPin
from app.services.audit_service import record_audit


def get_fernet() -> Fernet:
    key = get_settings().pin_encryption_key
    if not key:
        # Fallback 32-byte urlsafe base64 key for local dev and tests
        key = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI="
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_pin(pin: str) -> str:
    return get_fernet().encrypt(pin.encode("utf-8")).decode("utf-8")


def verify_pin_decrypted(plain_pin: str, pin_encrypted: str) -> bool:
    try:
        decrypted = get_fernet().decrypt(pin_encrypted.encode("utf-8")).decode("utf-8")
        return hmac.compare_digest(plain_pin, decrypted)
    except Exception:
        return False


class PinService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def encrypt_pin(self, pin: str) -> str:
        return encrypt_pin(pin)

    def decrypt_pin(self, encrypted_pin: str) -> str:
        return get_fernet().decrypt(encrypted_pin.encode("utf-8")).decode("utf-8")

    def _check_locks_and_windows(
        self, client_id: int, user_id: int, now: datetime
    ) -> tuple[PinAttempt | None, PinAttempt | None]:
        user_attempt = self.db.scalar(
            select(PinAttempt).where(PinAttempt.user_id == user_id, PinAttempt.client_id == client_id)
        )
        client_attempt = self.db.scalar(
            select(PinAttempt).where(PinAttempt.user_id.is_(None), PinAttempt.client_id == client_id)
        )

        # Check user lock
        if user_attempt and user_attempt.locked_until and user_attempt.locked_until > now:
            retry_after = max(1, int((user_attempt.locked_until - now).total_seconds()))
            raise PinLockedError(retry_after)

        # Check client-level lock
        if client_attempt and client_attempt.locked_until and client_attempt.locked_until > now:
            retry_after = max(1, int((client_attempt.locked_until - now).total_seconds()))
            raise PinLockedError(retry_after)

        # Rolling 1-hour window reset for client
        one_hour_ago = now - timedelta(hours=1)
        if client_attempt and client_attempt.window_started_at and client_attempt.window_started_at < one_hour_ago:
            client_attempt.failed_count = 0
            client_attempt.window_started_at = now
            client_attempt.locked_until = None

        # Check client 15 failures per hour cap across all users
        if client_attempt and client_attempt.failed_count >= 15:
            client_attempt.locked_until = (client_attempt.window_started_at or now) + timedelta(hours=1)
            self.db.commit()
            retry_after = max(1, int((client_attempt.locked_until - now).total_seconds()))
            raise PinLockedError(retry_after)

        # Reset user window if older than 1 hour or lock expired
        if user_attempt:
            if user_attempt.locked_until and user_attempt.locked_until <= now:
                user_attempt.locked_until = None
                user_attempt.failed_count = 0
                user_attempt.window_started_at = now
            elif user_attempt.window_started_at and user_attempt.window_started_at < one_hour_ago:
                user_attempt.failed_count = 0
                user_attempt.window_started_at = now

        return user_attempt, client_attempt

    def _record_failure(
        self,
        client_id: int,
        user_id: int,
        now: datetime,
        user_attempt: PinAttempt | None,
        client_attempt: PinAttempt | None,
    ) -> None:
        if not user_attempt:
            user_attempt = PinAttempt(
                user_id=user_id,
                client_id=client_id,
                failed_count=0,
                window_started_at=now,
            )
            self.db.add(user_attempt)
        if not user_attempt.window_started_at:
            user_attempt.window_started_at = now
        user_attempt.failed_count += 1

        if not client_attempt:
            client_attempt = PinAttempt(
                user_id=None,
                client_id=client_id,
                failed_count=0,
                window_started_at=now,
            )
            self.db.add(client_attempt)
        if not client_attempt.window_started_at:
            client_attempt.window_started_at = now
        client_attempt.failed_count += 1

        # Check client cap of 15 failures across all users in 1 hour
        if client_attempt.failed_count >= 15:
            client_attempt.locked_until = client_attempt.window_started_at + timedelta(hours=1)
            self.db.commit()
            retry_after = max(1, int((client_attempt.locked_until - now).total_seconds()))
            raise PinLockedError(retry_after)

        # Check user 5-failure lock (15 minutes)
        if user_attempt.failed_count >= 5:
            user_attempt.locked_until = now + timedelta(minutes=15)
            self.db.commit()
            raise PinLockedError(15 * 60)

        self.db.commit()
        tries_left = 5 - user_attempt.failed_count
        raise PinWrongError(tries_left)

    def verify_pin(self, client_id: int, user_id: int, pin: str, ip: str | None) -> dict:
        now = datetime.now(timezone.utc)
        user_attempt, client_attempt = self._check_locks_and_windows(client_id, user_id, now)

        staff_pin = self.db.scalar(select(StaffPin).where(StaffPin.client_id == client_id))
        if staff_pin is None or not verify_pin_decrypted(pin, staff_pin.pin_encrypted):
            self._record_failure(client_id, user_id, now, user_attempt, client_attempt)

        # Success!
        if user_attempt:
            user_attempt.failed_count = 0
            user_attempt.locked_until = None
        self.db.commit()
        token = create_elevation_token(user_id, client_id)
        return {"ok": True, "elevation_token": token, "expires_in": 900}

    def change_pin(
        self,
        client_id: int,
        user_id: int,
        current_pin: str,
        new_pin: str,
        confirm_pin: str,
        ip: str | None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        user_attempt, client_attempt = self._check_locks_and_windows(client_id, user_id, now)

        # newPin must be exactly 4 digits and equal confirmPin
        if not (len(new_pin) == 4 and new_pin.isdigit()):
            raise BadRequestError("PIN must be exactly 4 digits", error_code="INVALID_PIN")
        if new_pin != confirm_pin:
            raise BadRequestError("PINs do not match", error_code="PIN_MISMATCH")

        staff_pin = self.db.scalar(select(StaffPin).where(StaffPin.client_id == client_id))
        if staff_pin is not None:
            # currentPin may be empty only when no PIN is set yet
            if not current_pin or not verify_pin_decrypted(current_pin, staff_pin.pin_encrypted):
                self._record_failure(client_id, user_id, now, user_attempt, client_attempt)

        encrypted = encrypt_pin(new_pin)
        if staff_pin is None:
            staff_pin = StaffPin(
                client_id=client_id,
                pin_encrypted=encrypted,
                changed_at=now,
                changed_by_user_id=user_id,
            )
            self.db.add(staff_pin)
        else:
            staff_pin.pin_encrypted = encrypted
            staff_pin.changed_at = now
            staff_pin.changed_by_user_id = user_id

        if user_attempt:
            user_attempt.failed_count = 0
            user_attempt.locked_until = None

        record_audit(
            self.db,
            "staff PIN changed",
            user_id=user_id,
            client_id=client_id,
            entity_type="staff_pin",
            entity_id=str(client_id),
            ip_address=ip,
        )
        self.db.commit()
        return {"ok": True, "message": "PIN changed successfully"}
