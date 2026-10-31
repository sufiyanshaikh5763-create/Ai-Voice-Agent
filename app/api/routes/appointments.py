from datetime import date

from fastapi import APIRouter, Query, Request, status

from app.core.dependencies import (ClientAdminOrElevated, ClientAdminUser,
                                   ClientMemberUser, DbSession, TenantId)
from app.models.enums import AppointmentStatus
from app.schemas.appointment import (AppointmentCreate, AppointmentHistoryOut,
                                     AppointmentOut, AppointmentUpdate,
                                     CancelRequest, RescheduleRequest)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.appointment_service import AppointmentService
from app.services.cancellation_service import CancellationService
from app.services.reschedule_service import RescheduleService
from app.utils.pagination import PageParamsDep, paginated

router = APIRouter()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=PaginatedResponse[AppointmentOut])
def list_appointments(
    _: ClientMemberUser, tenant_id: TenantId, db: DbSession, page: PageParamsDep,
    status_filter: AppointmentStatus | None = Query(None, alias="status"),
    day: date | None = Query(None, alias="date", description="Exact appointment date"),
    date_from: date | None = None, date_to: date | None = None,
    customer_id: int | None = Query(None, alias="customer"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
):
    items, total = AppointmentService(db, tenant_id).list(
        page.offset, page.limit, status=status_filter, day=day, date_from=date_from,
        date_to=date_to, customer_id=customer_id, descending=order == "desc")
    return paginated(items, total, page, AppointmentOut)


@router.post("", response_model=ApiResponse[AppointmentOut], status_code=status.HTTP_201_CREATED)
def create_appointment(request: Request, body: AppointmentCreate, actor: ClientAdminOrElevated,
                       tenant_id: TenantId, db: DbSession):
    appointment = AppointmentService(db, tenant_id).create(body, actor, _ip(request))
    return ApiResponse(message="Appointment created successfully",
                       data=AppointmentOut.model_validate(appointment))


@router.get("/{appointment_id}", response_model=ApiResponse[AppointmentOut])
def get_appointment(appointment_id: int, _: ClientMemberUser, tenant_id: TenantId, db: DbSession):
    appointment = AppointmentService(db, tenant_id).get(appointment_id)
    return ApiResponse(message="Appointment retrieved successfully",
                       data=AppointmentOut.model_validate(appointment))


@router.patch("/{appointment_id}", response_model=ApiResponse[AppointmentOut])
def update_appointment(request: Request, appointment_id: int, body: AppointmentUpdate,
                       actor: ClientAdminOrElevated, tenant_id: TenantId, db: DbSession):
    appointment = AppointmentService(db, tenant_id).update(appointment_id, body, actor, _ip(request))
    return ApiResponse(message="Appointment updated successfully",
                       data=AppointmentOut.model_validate(appointment))


@router.delete("/{appointment_id}", response_model=ApiResponse[None])
def delete_appointment(request: Request, appointment_id: int, actor: ClientAdminUser,
                       tenant_id: TenantId, db: DbSession):
    AppointmentService(db, tenant_id).delete(appointment_id, actor, _ip(request))
    return ApiResponse(message="Appointment deleted successfully")


@router.get("/{appointment_id}/history", response_model=ApiResponse[list[AppointmentHistoryOut]])
def appointment_history(appointment_id: int, _: ClientMemberUser, tenant_id: TenantId,
                        db: DbSession):
    entries = AppointmentService(db, tenant_id).history(appointment_id)
    return ApiResponse(message="Appointment history retrieved successfully",
                       data=[AppointmentHistoryOut.model_validate(e) for e in entries])


@router.post("/{appointment_id}/cancel", response_model=ApiResponse[AppointmentOut])
def cancel_appointment(request: Request, appointment_id: int, actor: ClientAdminOrElevated,
                       tenant_id: TenantId, db: DbSession, body: CancelRequest | None = None):
    reason = body.reason if body else None
    appointment = CancellationService(db, tenant_id).cancel(
        appointment_id, reason, actor=actor, ip=_ip(request))
    return ApiResponse(message="Appointment cancelled successfully",
                       data=AppointmentOut.model_validate(appointment))


@router.post("/{appointment_id}/reschedule", response_model=ApiResponse[AppointmentOut])
def reschedule_appointment(request: Request, appointment_id: int, body: RescheduleRequest,
                           actor: ClientAdminOrElevated, tenant_id: TenantId, db: DbSession):
    appointment = RescheduleService(db, tenant_id).reschedule(
        appointment_id, body.new_date, body.new_time, body.reason, actor=actor, ip=_ip(request))
    return ApiResponse(message="Appointment rescheduled successfully",
                       data=AppointmentOut.model_validate(appointment))
