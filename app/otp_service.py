import secrets
import hashlib
import time

import resend

from app.core.config import get_settings

OTP_TTL = 600          # 10 minutes
RESEND_COOLDOWN = 60   # seconds
MAX_ATTEMPTS = 5


class EmailConfigurationError(RuntimeError):
    pass


# Temporary storage (see note below)
otp_store = {}  # email -> {hash, expires_at, attempts, last_sent}

def _hash(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def send_otp(email: str):
    settings = get_settings()
    if not settings.resend_api_key.strip():
        raise EmailConfigurationError("RESEND_API_KEY is required to send OTP emails")

    email = email.lower().strip()
    rec = otp_store.get(email)
    if rec and time.time() - rec["last_sent"] < RESEND_COOLDOWN:
        raise ValueError("Please wait before requesting another code")

    resend.api_key = settings.resend_api_key
    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_store[email] = {
        "hash": _hash(otp),
        "expires_at": time.time() + OTP_TTL,
        "attempts": 0,
        "last_sent": time.time(),
    }

    resend.Emails.send({
        "from": settings.mail_from,
        "to": [email],
        "subject": "Your verification code",
        "html": f"""
        <div style="font-family:sans-serif">
          <h2>Verify your email</h2>
          <p>Your code is:</p>
          <p style="font-size:28px;letter-spacing:6px"><b>{otp}</b></p>
          <p>It expires in 10 minutes. If you didn't request this, ignore this email.</p>
        </div>""",
    })

def verify_otp(email: str, otp: str) -> bool:
    email = email.lower().strip()
    rec = otp_store.get(email)
    if not rec or time.time() > rec["expires_at"]:
        return False
    if rec["attempts"] >= MAX_ATTEMPTS:
        return False
    if not secrets.compare_digest(rec["hash"], _hash(otp)):
        rec["attempts"] += 1
        return False
    del otp_store[email]
    return True