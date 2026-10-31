import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import resend

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def warn_if_console_backend_in_production() -> None:
    settings = get_settings()
    if settings.app_env == "production" and settings.email_backend.lower() == "console":
        logger.warning(
            "EMAIL_BACKEND=console in production; verification emails are not being sent."
        )


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_verification_email(self, to_email: str, code: str) -> None:
        """Send 6-digit verification code according to configured EMAIL_BACKEND."""
        backend = (self.settings.email_backend or "console").lower()

        if backend == "console":
            if self.settings.app_env != "production":
                logger.info("Verification code for %s: %s", to_email, code)
            else:
                logger.info("Verification email dispatched to %s (code suppressed in production)", to_email)
            return

        if backend == "smtp":
            self._send_via_smtp(to_email, code)
            return

        if backend == "resend":
            self._send_via_resend(to_email, code)
            return

        logger.warning("Unknown EMAIL_BACKEND '%s'. Falling back to console dispatch.", backend)
        if self.settings.app_env != "production":
            logger.info("Verification code for %s: %s", to_email, code)

    def _send_via_smtp(self, to_email: str, code: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Verify your email address - Talkaor"
        msg["From"] = self.settings.email_from
        msg["To"] = to_email

        text_content = (
            f"Hello,\n\n"
            f"Your Talkaor verification code is: {code}\n\n"
            f"This code will expire in 10 minutes.\n"
            f"If you did not request this, please ignore this email.\n"
        )
        html_content = (
            f"<p>Hello,</p>"
            f"<p>Your Talkaor verification code is: <strong>{code}</strong></p>"
            f"<p>This code will expire in 10 minutes.</p>"
            f"<p>If you did not request this, please ignore this email.</p>"
        )

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        host = self.settings.smtp_host
        port = self.settings.smtp_port or 587
        user = self.settings.smtp_user
        password = self.settings.smtp_password

        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
            logger.info("Verification email sent via SMTP to %s", to_email)
        except Exception as exc:
            logger.error("Failed to send verification email via SMTP to %s: %s", to_email, exc)
            raise

    def _send_via_resend(self, to_email: str, code: str) -> None:
        if not self.settings.resend_api_key:
            raise RuntimeError("RESEND_API_KEY is required when EMAIL_BACKEND=resend")

        resend.api_key = self.settings.resend_api_key
        try:
            resend.Emails.send({
                "from": self.settings.mail_from,
                "to": [to_email],
                "subject": "Verify your email address - Talkaor",
                "html": (
                    "<p>Hello,</p>"
                    f"<p>Your Talkaor verification code is: <strong>{code}</strong></p>"
                    "<p>This code will expire in 10 minutes.</p>"
                    "<p>If you did not request this, please ignore this email.</p>"
                ),
            })
            logger.info("Verification email sent via Resend to %s", to_email)
        except Exception as exc:
            logger.error("Failed to send verification email via Resend to %s: %s", to_email, exc)
            raise
