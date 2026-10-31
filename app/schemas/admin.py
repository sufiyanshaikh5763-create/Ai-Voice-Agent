from datetime import date, datetime

from pydantic import BaseModel, Field


class AccessRequestItem(BaseModel):
    id: int
    business: str
    plan: str
    billing: str
    amount: int
    status: str
    transaction_id: str | None = None
    payer_name: str | None = None
    payment_date: date | None = None
    screenshot_available: bool = False
    amount_mismatch: bool = False


class AccessDeclineRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class AccessActionResponse(BaseModel):
    id: int
    business: str
    status: str
    reason: str | None = None


class AdminBusinessItem(BaseModel):
    id: int
    name: str
    plan: str
    minutes_used: int
    minutes_limit: int
    status: str
    renews_on: datetime | None = None
    last_login: datetime | None = None
    has_pin: bool = False


class BusinessStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(Active|Suspended)$")


class BusinessMinutePackRequest(BaseModel):
    minutes: int = Field(..., ge=1, le=10000)


class PinViewResponse(BaseModel):
    pin: str
    changedAt: str | None = None


class PinResetRequest(BaseModel):
    pin: str | None = Field(None, pattern="^[0-9]{4}$")


class PinResetResponse(BaseModel):
    pin: str
    message: str = "PIN reset successfully"


class AdminAgentItem(BaseModel):
    id: int
    name: str
    languages: list[str] = ["English"]
    phone: str | None = None
    phone_number: str | None = None
    online: bool = True
    calls_today: int = 0
    business_id: int
    business_name: str


class AgentPowerRequest(BaseModel):
    online: bool


class LogItem(BaseModel):
    at: str
    text: str
    level: str


class AdminMessageItem(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    message: str | None = None
    received_at: datetime
    read: bool
    handled: bool


class AdminMessageUpdateRequest(BaseModel):
    read: bool | None = None
    handled: bool | None = None


class AdminUserResetPasswordRequest(BaseModel):
    new_password: str


class AdminWebhookEventItem(BaseModel):
    id: int
    provider: str
    event_id: str
    event_type: str
    client_id: int | None = None
    business_name: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    processed_at: datetime | None = None


class AdminWebhookEventDetail(AdminWebhookEventItem):
    payload: dict


class AdminToolCallItem(BaseModel):
    id: int
    client_id: int | None = None
    business_name: str | None = None
    tool: str
    action: str
    tenant_resolution: str | None = None
    success: bool
    error_code: str | None = None
    message: str | None = None
    appointment_id: int | None = None
    duration_ms: int
    request_id: str | None = None
    created_at: datetime


class AdminAppointmentItem(BaseModel):
    id: int
    client_id: int
    business_name: str
    customer_name: str
    date: date
    time: str
    status: str
    source: str
    created_at: datetime


class AdminMonitoringItem(BaseModel):
    client_id: int
    business_name: str
    access_status: str
    agent_status: str | None = None
    provider_agent_id_present: bool
    last_call_time: datetime | None = None
    minutes_used: int
    minutes_limit: int
    usage_percent: float
    alert: str
    failed_webhook_events_24h: int
    last_webhook_received_at: datetime | None = None
    last_tool_call_at: datetime | None = None
    last_tool_call_error: str | None = None


class AdminHealthDetails(BaseModel):
    database_ok: bool
    last_webhook_received_at: datetime | None = None
    sarvam_api_key_set: bool
    sarvam_base_url_set: bool
    sarvam_webhook_secret_set: bool
    email_backend: str
    resend_api_key_set: bool
    app_env_production: bool
