"""Inbound provider webhooks. Authenticated by signature (see integrations/sarvam/webhook.py),
NOT by JWT — there is no end user attached to a provider event."""
import json
import logging

from fastapi import APIRouter, Header, Request
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.exceptions import BadRequestError, UnauthorizedError
from app.core.rate_limit import limiter
from app.integrations.sarvam.schemas import SarvamWebhookEnvelope
from app.integrations.sarvam.webhook import verify_signature
from app.schemas.common import ApiResponse
from app.schemas.webhook import WebhookOutcome
from app.services.webhook_service import WebhookService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/sarvam", response_model=ApiResponse[WebhookOutcome])
@limiter.limit("120/minute")
async def sarvam_webhook(request: Request,
                         x_sarvam_signature: str | None = Header(default=None)):
    raw_body = await request.body()
    settings = get_settings()
    if not verify_signature(raw_body, x_sarvam_signature, settings.sarvam_webhook_secret):
        raise UnauthorizedError("Invalid webhook signature", error_code="INVALID_WEBHOOK_SIGNATURE")

    try:
        raw_payload = json.loads(raw_body)
        envelope = SarvamWebhookEnvelope.model_validate(raw_payload)
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as exc:
        raise BadRequestError("Invalid webhook payload", error_code="INVALID_WEBHOOK_PAYLOAD") from exc

    # A dedicated session: webhooks aren't part of the request-scoped get_db dependency chain,
    # so failures here never affect (or get rolled back by) unrelated requests.
    with SessionLocal() as db:
        outcome = WebhookService(db).process(
            envelope, raw_payload, request_id=getattr(request.state, "request_id", None))
    if outcome.status.value == "failed":
        logger.warning("Sarvam webhook %s failed: %s", outcome.event_id, outcome.message)
    return ApiResponse(message=outcome.message, data=outcome)
