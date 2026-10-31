from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.appointment import Appointment, AppointmentHistory
from app.models.enums import AppointmentAction, AppointmentStatus, ChangeSource
from app.models.user import User
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.customer_repository import CustomerRepository
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate
from app.services.appointment_rules import (ensure_not_cancelled, ensure_not_in_past,
                                            ensure_status_change_allowed)
from app.services.audit_service import record_audit
from app.services.transactions import commit_or_conflict
from app.utils.helpers import drop_nulls

_SLOT_TAKEN = "This customer already has an appointment at that date and time"
_SLOT_CODE = "APPOINTMENT_CONFLICT"


class AppointmentService:
    def __init__(self, db: Session, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repo = AppointmentRepository(db, tenant_id)
        self.customers = CustomerRepository(db, tenant_id)

    # ----- helpers -----
    def _timezone(self) -> str:
        client = ClientRepository(self.db).get_by_id(self.tenant_id)
        return client.timezone if client else "UTC"

    def _require_customer(self, customer_id: int) -> None:
        if self.customers.get(customer_id) is None:
            raise NotFoundError("Customer not found", error_code="CUSTOMER_NOT_FOUND")

    # ----- queries -----
    def list(self, offset: int, limit: int, *, status: AppointmentStatus | None,
             day: date | None, date_from: date | None, date_to: date | None,
             customer_id: int | None, descending: bool = False) -> tuple[list[Appointment], int]:
        filters = []
        if status is not None:
            filters.append(Appointment.status == status)
        if day is not None:
            filters.append(Appointment.appointment_date == day)
        if date_from is not None:
            filters.append(Appointment.appointment_date >= date_from)
        if date_to is not None:
            filters.append(Appointment.appointment_date <= date_to)
        if customer_id is not None:
            filters.append(Appointment.customer_id == customer_id)
        return self.repo.list(
            offset=offset, limit=limit, filters=filters,
            order_by=(
                [Appointment.appointment_date.desc(), Appointment.appointment_time.desc(),
                 Appointment.id.desc()]
                if descending else
                [Appointment.appointment_date, Appointment.appointment_time, Appointment.id]
            ))

    def get(self, appointment_id: int) -> Appointment:
        appointment = self.repo.get(appointment_id)
        if appointment is None:
            raise NotFoundError("Appointment not found", error_code="APPOINTMENT_NOT_FOUND")
        return appointment

    def history(self, appointment_id: int) -> list[AppointmentHistory]:
        self.get(appointment_id)  # 404 for missing or foreign appointments
        return self.repo.list_history(appointment_id)

    # ----- commands -----
    def create(self, data: AppointmentCreate, actor: User | None, ip: str | None,
              source: ChangeSource = ChangeSource.USER) -> Appointment:
        self._require_customer(data.customer_id)
        ensure_not_in_past(data.appointment_date, data.appointment_time, self._timezone())
        if self.repo.has_active_at(data.customer_id, data.appointment_date, data.appointment_time):
            raise ConflictError(_SLOT_TAKEN, error_code=_SLOT_CODE)
        actor_id = actor.id if actor else None
        appointment = self.repo.add(Appointment(**data.model_dump()))
        self.repo.add_history(
            appointment_id=appointment.id, action=AppointmentAction.CREATED,
            source=source, actor_user_id=actor_id,
            new_date=appointment.appointment_date, new_time=appointment.appointment_time,
            new_status=appointment.status.value)
        record_audit(self.db, "appointment.create", user_id=actor_id, client_id=self.tenant_id,
                     entity_type="appointment", entity_id=appointment.id, ip_address=ip)
        commit_or_conflict(self.db, _SLOT_TAKEN, _SLOT_CODE)
        return self.get(appointment.id)

    def update(self, appointment_id: int, data: AppointmentUpdate, actor: User,
               ip: str | None) -> Appointment:
        appointment = self.get(appointment_id)
        ensure_not_cancelled(appointment)
        # `notes` may be cleared with null; the other fields cannot be null.
        changes = drop_nulls(data.model_dump(exclude_unset=True), nullable=("notes",))
        old_status = appointment.status

        if "status" in changes:
            ensure_status_change_allowed(old_status, changes["status"])
        if "customer_id" in changes and changes["customer_id"] != appointment.customer_id:
            self._require_customer(changes["customer_id"])
            if self.repo.has_active_at(changes["customer_id"], appointment.appointment_date,
                                       appointment.appointment_time, exclude_id=appointment.id):
                raise ConflictError(_SLOT_TAKEN, error_code=_SLOT_CODE)

        for field, value in changes.items():
            setattr(appointment, field, value)
        if appointment.status != old_status:
            self.repo.add_history(
                appointment_id=appointment.id, action=AppointmentAction.UPDATED,
                source=ChangeSource.USER, actor_user_id=actor.id,
                old_status=old_status.value, new_status=appointment.status.value)
        record_audit(self.db, "appointment.update", user_id=actor.id, client_id=self.tenant_id,
                     entity_type="appointment", entity_id=appointment.id,
                     details={"fields": sorted(changes)}, ip_address=ip)
        commit_or_conflict(self.db, _SLOT_TAKEN, _SLOT_CODE)
        return self.get(appointment.id)

    def delete(self, appointment_id: int, actor: User, ip: str | None) -> None:
        appointment = self.get(appointment_id)
        # The history rows go with the appointment, so the audit log keeps a snapshot.
        record_audit(self.db, "appointment.delete", user_id=actor.id, client_id=self.tenant_id,
                     entity_type="appointment", entity_id=appointment.id,
                     details={"customer_id": appointment.customer_id,
                              "date": appointment.appointment_date.isoformat(),
                              "time": appointment.appointment_time.isoformat(timespec="minutes"),
                              "status": appointment.status.value},
                     ip_address=ip)
        self.repo.delete_with_history(appointment)
        self.db.commit()
