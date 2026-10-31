"""Import every model so Base.metadata (and Alembic) sees all tables."""
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentHistory
from app.models.audit_log import AuditLog
from app.models.business_profile import BusinessHour, Service, StaffMember
from app.models.call import Call
from app.models.call_attempt import CallAttempt
from app.models.cancellation import Cancellation
from app.models.client import Client
from app.models.client_tool_credential import ClientToolCredential
from app.models.customer import Customer
from app.models.email_verification import EmailVerification
from app.models.enquiry import Enquiry
from app.models.payment import Payment
from app.models.plan import MinutePack, Plan, Subscription
from app.models.refresh_token import RefreshToken
from app.models.staff_pin import PinAttempt, StaffPin
from app.models.user import User
from app.models.webhook_event import WebhookEvent

__all__ = [
    "Agent", "Appointment", "AppointmentHistory", "AuditLog", "BusinessHour", "Call",
    "CallAttempt", "Cancellation", "Client", "ClientToolCredential", "Customer", "EmailVerification", "Enquiry", "MinutePack", "Payment",
    "PinAttempt", "Plan", "RefreshToken", "Service", "StaffMember", "StaffPin", "Subscription", "User", "WebhookEvent",
]
