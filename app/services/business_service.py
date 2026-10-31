"""Business profile bundle management: hours, services, and staff."""
from datetime import time

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.audit_log import AuditLog
from app.models.business_profile import BusinessHour, Service, StaffMember
from app.models.client import Client
from app.models.user import User
from app.schemas.business import BusinessProfilePatchRequest
from app.services.audit_service import record_audit
from app.services.billing_service import BillingService


def parse_time(val: str | time | None) -> time | None:
    if val is None or val == "":
        return None
    if isinstance(val, time):
        return val
    parts = str(val).split(":")
    return time(int(parts[0]), int(parts[1]))


def format_time(t: time | None) -> str | None:
    if t is None:
        return None
    return t.strftime("%H:%M")


class BusinessService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _ensure_default_hours(self, client_id: int) -> list[BusinessHour]:
        existing = list(
            self.db.scalars(
                select(BusinessHour)
                .where(BusinessHour.client_id == client_id)
                .order_by(BusinessHour.weekday)
            ).all()
        )
        if len(existing) == 7:
            return existing

        self.db.execute(delete(BusinessHour).where(BusinessHour.client_id == client_id))
        created = []
        for day in range(5):  # Mon-Fri
            created.append(
                BusinessHour(
                    client_id=client_id,
                    weekday=day,
                    open_time=time(9, 0),
                    close_time=time(18, 0),
                    closed=False,
                )
            )
        # Sat
        created.append(
            BusinessHour(
                client_id=client_id,
                weekday=5,
                open_time=time(9, 0),
                close_time=time(14, 0),
                closed=False,
            )
        )
        # Sun
        created.append(
            BusinessHour(
                client_id=client_id,
                weekday=6,
                open_time=None,
                close_time=None,
                closed=True,
            )
        )
        self.db.add_all(created)
        self.db.commit()
        return created

    def get_business_bundle(self, client_id: int) -> dict:
        client = self.db.get(Client, client_id)
        if not client:
            raise NotFoundError("Client not found", error_code="CLIENT_NOT_FOUND")

        billing_info = BillingService(self.db).get_billing_me(client_id)

        # Retrieve last login for this client from audit logs
        last_login_log = self.db.scalar(
            select(AuditLog)
            .where(AuditLog.client_id == client_id, AuditLog.action == "auth.login")
            .order_by(desc(AuditLog.created_at))
            .limit(1)
        )
        last_login = (
            last_login_log.created_at.isoformat() if last_login_log and last_login_log.created_at else None
        )

        status_str = (
            client.access_status.value
            if hasattr(client.access_status, "value")
            else str(client.access_status)
        )

        # 7 daily hours entries (Mon=0 to Sun=6)
        hours_rows = self._ensure_default_hours(client_id)
        hours_list = [
            {
                "open": format_time(h.open_time),
                "close": format_time(h.close_time),
                "closed": bool(h.closed),
            }
            for h in hours_rows
        ]

        # Services list
        service_rows = self.db.scalars(
            select(Service)
            .where(Service.client_id == client_id)
            .order_by(Service.sort_order, Service.id)
        ).all()
        services_list = [s.name for s in service_rows]

        # Staff members list
        staff_rows = self.db.scalars(
            select(StaffMember)
            .where(StaffMember.client_id == client_id)
            .order_by(StaffMember.id)
        ).all()
        staff_list = [
            {
                "id": sm.id,
                "name": sm.name,
                "title": sm.title,
                "days": list(sm.available_days) if sm.available_days else [True] * 7,
            }
            for sm in staff_rows
        ]

        renews_on_val = billing_info.get("renews_on")
        renews_on_str = (
            renews_on_val.strftime("%Y-%m-%d")
            if hasattr(renews_on_val, "strftime")
            else str(renews_on_val) if renews_on_val else None
        )

        return {
            "business": {
                "id": client.id,
                "name": client.business_name,
                "plan": billing_info["plan"],
                "minutes_used": billing_info["minutes_used"],
                "minutes_limit": billing_info["minutes_limit"],
                "status": status_str,
                "renews_on": renews_on_str,
                "last_login": last_login,
            },
            "hours": hours_list,
            "services": services_list,
            "staff": staff_list,
            "timezone": client.timezone or "Asia/Kolkata",
        }

    def update_business_bundle(
        self,
        client_id: int,
        user: User,
        data: BusinessProfilePatchRequest,
        ip: str | None = None,
    ) -> dict:
        client = self.db.get(Client, client_id)
        if not client:
            raise NotFoundError("Client not found", error_code="CLIENT_NOT_FOUND")

        updated_fields = []

        # Atomic replacement in one transaction
        if data.hours is not None:
            existing_hours = self.db.scalars(
                select(BusinessHour)
                .where(BusinessHour.client_id == client_id)
                .order_by(BusinessHour.weekday)
            ).all()
            next_hours = [
                (
                    parse_time(h.open) if not h.closed else None,
                    parse_time(h.close) if not h.closed else None,
                    bool(h.closed),
                )
                for h in data.hours
            ]
            hours_changed = [
                (h.open_time, h.close_time, bool(h.closed)) for h in existing_hours
            ] != next_hours
            self.db.execute(delete(BusinessHour).where(BusinessHour.client_id == client_id))
            new_hours = []
            for day_idx, h in enumerate(data.hours):
                new_hours.append(
                    BusinessHour(
                        client_id=client_id,
                        weekday=day_idx,
                        open_time=parse_time(h.open) if not h.closed else None,
                        close_time=parse_time(h.close) if not h.closed else None,
                        closed=bool(h.closed),
                    )
                )
            self.db.add_all(new_hours)
            if hours_changed:
                updated_fields.append("hours")

        if data.services is not None:
            existing_services = self.db.scalars(
                select(Service)
                .where(Service.client_id == client_id)
                .order_by(Service.sort_order, Service.id)
            ).all()
            next_services = [name.strip() for name in data.services]
            services_changed = [service.name for service in existing_services] != next_services
            self.db.execute(delete(Service).where(Service.client_id == client_id))
            new_services = [
                Service(client_id=client_id, name=name.strip(), sort_order=idx)
                for idx, name in enumerate(data.services)
            ]
            self.db.add_all(new_services)
            if services_changed:
                updated_fields.append("services")

        if data.staff is not None:
            existing_staff = self.db.scalars(
                select(StaffMember)
                .where(StaffMember.client_id == client_id)
                .order_by(StaffMember.id)
            ).all()
            next_staff = [
                (member.name.strip(), member.title.strip() if member.title else None, member.days)
                for member in data.staff
            ]
            staff_changed = [
                (member.name, member.title, list(member.available_days))
                for member in existing_staff
            ] != next_staff
            self.db.execute(delete(StaffMember).where(StaffMember.client_id == client_id))
            new_staff = [
                StaffMember(
                    client_id=client_id,
                    name=s.name.strip(),
                    title=s.title.strip() if s.title else None,
                    available_days=s.days,
                )
                for s in data.staff
            ]
            self.db.add_all(new_staff)
            if staff_changed:
                updated_fields.append("staff")

        record_audit(
            self.db,
            "business.update",
            user_id=user.id,
            client_id=client_id,
            details={"updated": updated_fields, "updated_fields": updated_fields},
            ip_address=ip,
        )
        self.db.commit()

        return self.get_business_bundle(client_id)
