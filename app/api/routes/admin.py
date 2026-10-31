from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.core.config import get_settings
from app.core.dependencies import DbSession, SuperAdminUser
from app.core.rate_limit import limiter
from app.models.enums import AppointmentStatus
from app.schemas.admin import (AccessActionResponse, AccessDeclineRequest,
                               AccessRequestItem, AdminAgentItem,
                               AdminAppointmentItem, AdminBusinessItem,
                               AdminHealthDetails, AdminMessageItem,
                               AdminMonitoringItem, AdminToolCallItem,
                               AdminWebhookEventDetail, AdminWebhookEventItem,
                               AdminMessageUpdateRequest, AdminUserResetPasswordRequest,
                               AgentPowerRequest, BusinessMinutePackRequest,
                               BusinessStatusUpdateRequest, LogItem,
                               PinResetRequest, PinResetResponse,
                               PinViewResponse)
from app.schemas.agent import AgentOut
from app.schemas.agent_link import (AdminAgentCreate, AdminAgentUpdate,
                                    ClientIntegrationOut, ClientToolTokenOut)
from app.schemas.user import UserOut, UserUpdate
from app.services.admin_agent_service import AdminAgentService
from app.services.admin_service import AdminService
from app.services.client_tool_credential_service import ClientToolCredentialService
from app.schemas.common import ApiResponse, PaginatedResponse
from app.utils.pagination import PageParamsDep, paginated

router = APIRouter()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ---------------- 1. ACCESS REQUESTS ----------------

@router.get("/access-requests", response_model=list[AccessRequestItem])
def list_access_requests(user: SuperAdminUser, db: DbSession):
    """Retrieve all pending, needs review, or recently decided access requests."""
    return AdminService(db).get_access_requests()


@router.post("/access/{client_id}/approve", response_model=AccessActionResponse)
def approve_client_access(client_id: int, request: Request, user: SuperAdminUser, db: DbSession):
    """Approve client payment, activate subscription, and dispatch welcome email."""
    return AdminService(db).approve_access(client_id=client_id, user=user, ip=_ip(request))


@router.post("/access/{client_id}/decline", response_model=AccessActionResponse)
def decline_client_access(
    client_id: int, body: AccessDeclineRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Decline client payment, store rejection reason, and dispatch notification email."""
    return AdminService(db).decline_access(client_id=client_id, reason=body.reason, user=user, ip=_ip(request))


# ---------------- 2. BUSINESSES ----------------

@router.get("/businesses", response_model=list[AdminBusinessItem])
def list_businesses(user: SuperAdminUser, db: DbSession):
    """List all registered platform businesses with subscription, usage, and login metrics."""
    return AdminService(db).get_businesses()


@router.patch("/businesses/{client_id}/status")
def update_business_status(
    client_id: int, body: BusinessStatusUpdateRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Set business status to Active or Suspended across all client accounts."""
    return AdminService(db).update_business_status(client_id=client_id, status_str=body.status, user=user, ip=_ip(request))


@router.post("/businesses/{client_id}/minute-pack")
def add_minute_pack(
    client_id: int, body: BusinessMinutePackRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Add bonus/purchased minutes (1 to 10000) to a business."""
    return AdminService(db).add_minute_pack(client_id=client_id, minutes=body.minutes, user=user, ip=_ip(request))


@router.post("/businesses/{client_id}/pin-view", response_model=PinViewResponse)
@limiter.limit("10/minute")
def view_business_pin(client_id: int, request: Request, user: SuperAdminUser, db: DbSession):
    """Decrypt and view current staff PIN (audit-logged, rate-limited to 10/min)."""
    return AdminService(db).view_pin(client_id=client_id, user=user, ip=_ip(request))


@router.post("/businesses/{client_id}/pin-reset", response_model=PinResetResponse)
def reset_business_pin(
    client_id: int, body: PinResetRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Reset staff PIN to provided or generated 4 digits and clear lockout attempts."""
    return AdminService(db).reset_pin(client_id=client_id, pin=body.pin, user=user, ip=_ip(request))


# ---------------- 3. AGENTS ----------------

@router.get("/agents", response_model=list[AdminAgentItem])
def list_all_agents(user: SuperAdminUser, db: DbSession):
    """Retrieve all agents across all tenants with call metrics."""
    return AdminService(db).get_agents()


@router.post(
    "/clients/{client_id}/agents",
    response_model=ApiResponse[AgentOut],
    status_code=status.HTTP_201_CREATED,
)
def create_client_agent(
    client_id: int, body: AdminAgentCreate, request: Request,
    user: SuperAdminUser, db: DbSession,
):
    agent = AdminAgentService(db).create(client_id, body, user, _ip(request))
    return ApiResponse(message="Agent linked successfully",
                        data=AgentOut.model_validate(agent))

@router.patch("/agents/{agent_id}", response_model=ApiResponse[AgentOut])
def update_agent_link(
    agent_id: int, body: AdminAgentUpdate, request: Request,
    user: SuperAdminUser, db: DbSession,
):
    agent = AdminAgentService(db).update(agent_id, body, user, _ip(request))
    return ApiResponse(message="Agent updated successfully",
                        data=AgentOut.model_validate(agent))


@router.post("/agents/{agent_id}/unlink", response_model=ApiResponse[AgentOut])
def unlink_agent(
    agent_id: int, request: Request, user: SuperAdminUser, db: DbSession,
):
    agent = AdminAgentService(db).unlink(agent_id, user, _ip(request))
    return ApiResponse(message="Agent unlinked successfully",
                        data=AgentOut.model_validate(agent))

@router.post(
    "/clients/{client_id}/tool-token",
    response_model=ApiResponse[ClientToolTokenOut],
)
def create_or_rotate_client_tool_token(
    client_id: int, request: Request, user: SuperAdminUser, db: DbSession,
):
    result = ClientToolCredentialService(db).create_or_rotate(
        client_id, user, _ip(request), get_settings().public_api_base_url
    )
    return ApiResponse(message="Client tool token created or rotated", data=result)


@router.get(
    "/clients/{client_id}/integration",
    response_model=ApiResponse[ClientIntegrationOut],
)
def get_client_integration(
    client_id: int, user: SuperAdminUser, db: DbSession,
):
    result = ClientToolCredentialService(db).integration(
        client_id, get_settings().public_api_base_url
    )
    return ApiResponse(message="Client integration details retrieved", data=result)


@router.patch("/agents/{agent_id}/power")
def toggle_agent_power(
    agent_id: int, body: AgentPowerRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Toggle agent online/offline status platform-wide."""
    return AdminService(db).toggle_agent_power(agent_id=agent_id, online=body.online, user=user, ip=_ip(request))


# ---------------- 4. AUDIT LOGS ----------------

@router.get("/logs", response_model=list[LogItem])
def list_logs(
    user: SuperAdminUser,
    db: DbSession,
    level: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[datetime | None, Query()] = None,
):
    """Retrieve filtered audit logs with human-readable timestamps and levels."""
    return AdminService(db).get_logs(level=level, limit=limit, before=before)


# ---------------- 5. MESSAGES & SCREENSHOT ----------------

@router.get("/messages", response_model=list[AdminMessageItem])
def list_messages(user: SuperAdminUser, db: DbSession):
    """List contact form inquiries and platform messages."""
    return AdminService(db).get_messages()


@router.patch("/messages/{message_id}", response_model=AdminMessageItem)
def update_message_status(
    message_id: int, body: AdminMessageUpdateRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Update read or handled status for a contact message."""
    return AdminService(db).update_message(
        message_id=message_id, read=body.read, handled=body.handled, user=user, ip=_ip(request)
    )


@router.get("/payments/{payment_id}/screenshot")
def stream_payment_screenshot(payment_id: int, user: SuperAdminUser, db: DbSession):
    """Stream securely stored payment screenshot receipt for super_admin review."""
    return AdminService(db).get_screenshot_response(payment_id=payment_id)


# ---------------- 6. USER MANAGEMENT & PROTECTION ----------------

@router.patch("/users/{user_id}", response_model=UserOut)
def admin_update_user(
    user_id: int, body: UserUpdate, request: Request, user: SuperAdminUser, db: DbSession
):
    """Update user by super_admin. Protected accounts reject with 403."""
    updated = AdminService(db).update_user(target_user_id=user_id, data=body, user=user, ip=_ip(request))
    return UserOut.model_validate(updated)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(user_id: int, request: Request, user: SuperAdminUser, db: DbSession):
    """Delete user by super_admin. Protected accounts reject with 403."""
    AdminService(db).delete_user(target_user_id=user_id, user=user, ip=_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_200_OK)
def admin_reset_user_password(
    user_id: int, body: AdminUserResetPasswordRequest, request: Request, user: SuperAdminUser, db: DbSession
):
    """Reset user password by super_admin. Protected accounts reject with 403."""
    AdminService(db).reset_user_password(target_user_id=user_id, new_password=body.new_password, user=user, ip=_ip(request))
    return {"message": "Password reset successfully"}


# ---------------- 7. LOGWATCH ----------------

@router.get("/webhook-events", response_model=PaginatedResponse[AdminWebhookEventItem])
def list_webhook_events(
    user: SuperAdminUser, db: DbSession, page: PageParamsDep,
    status_filter: str | None = Query(None, alias="status"),
    client_id: int | None = None, event_type: str | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
):
    items, total = AdminService(db).get_webhook_events(
        page.offset, page.limit, status=status_filter, client_id=client_id,
        event_type=event_type, date_from=date_from, date_to=date_to)
    return paginated(items, total, page, AdminWebhookEventItem)


@router.get("/webhook-events/{id}", response_model=AdminWebhookEventDetail)
def get_webhook_event(id: int, user: SuperAdminUser, db: DbSession):
    return AdminService(db).get_webhook_event(id)


@router.get("/tool-calls", response_model=PaginatedResponse[AdminToolCallItem])
def list_tool_calls(
    user: SuperAdminUser, db: DbSession, page: PageParamsDep,
    client_id: int | None = None, tool: str | None = None,
    success: bool | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
):
    items, total = AdminService(db).get_tool_calls(
        page.offset, page.limit, client_id=client_id, tool=tool, success=success,
        date_from=date_from, date_to=date_to)
    return paginated(items, total, page, AdminToolCallItem)


@router.get("/appointments", response_model=PaginatedResponse[AdminAppointmentItem])
def list_admin_appointments(
    user: SuperAdminUser, db: DbSession, page: PageParamsDep,
    client_id: int | None = None, status_filter: AppointmentStatus | None = Query(None, alias="status"),
    source: str | None = Query(None, pattern="^(ai_agent|manual)$"),
    date_from: date | None = None, date_to: date | None = None,
):
    items, total = AdminService(db).get_admin_appointments(
        page.offset, page.limit, client_id=client_id, status=status_filter,
        source=source, date_from=date_from, date_to=date_to)
    return paginated(items, total, page, AdminAppointmentItem)


@router.get("/monitoring", response_model=PaginatedResponse[AdminMonitoringItem])
def admin_monitoring(user: SuperAdminUser, db: DbSession, page: PageParamsDep):
    items, total = AdminService(db).get_monitoring(page.offset, page.limit)
    return paginated(items, total, page, AdminMonitoringItem)


@router.get("/health/details", response_model=AdminHealthDetails)
def admin_health_details(user: SuperAdminUser, db: DbSession):
    return AdminService(db).get_health_details()
