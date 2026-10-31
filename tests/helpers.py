import httpx  # noqa: F401  (only referenced in a type comment above)
"""Shared test helpers."""
from fastapi.testclient import TestClient

PASSWORD = "Sup3rSecret1"


def register(client: TestClient, email: str, business: str = "Biz", password: str = PASSWORD,
             phone: str | None = None, country_code: str | None = None):
    body = {"business_name": business, "name": "Owner", "email": email, "password": password}
    if phone:
        body["phone"] = phone
    if country_code:
        body["country_code"] = country_code
    return client.post("/api/v1/auth/register", json=body)


def register_ok(client: TestClient, email: str, business: str = "Biz", active: bool = True) -> dict:
    resp = register(client, email, business)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    if active and data.get("user") and data["user"].get("client_id"):
        from app.core.database import SessionLocal
        from app.models.client import Client
        from app.models.enums import AccessStatus, OnboardingStage
        from app.services.billing_service import BillingService
        from app.services.business_service import BusinessService
        with SessionLocal() as db:
            c = db.get(Client, data["user"]["client_id"])
            if c:
                c.access_status = AccessStatus.ACTIVE
                c.onboarding_stage = OnboardingStage.SETUP_COMPLETE
                BillingService(db).get_or_create_default_subscription(c.id)
                BusinessService(db)._ensure_default_hours(c.id)
                db.commit()
    return data


def auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def elevated_headers(access_token: str, elevation_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Admin-Session": elevation_token,
    }


def make_elevation_token(user_id: int, client_id: int) -> str:
    from app.core.security import create_elevation_token
    return create_elevation_token(user_id, client_id)


def make_user(db, client_id, role, email, password: str = PASSWORD):
    """Insert a user directly (used for SUPER_ADMIN, which the API cannot create)."""
    from app.core.security import hash_password
    from app.models.user import User

    user = User(client_id=client_id, name="Test User", email=email,
                password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    return user


def login_token(client: TestClient, email: str, password: str = PASSWORD) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


def create_staff(client: TestClient, admin_token: str, email: str, role: str = "client_staff") -> dict:
    resp = client.post("/api/v1/users", headers=auth_headers(admin_token), json={
        "name": "Staff", "email": email, "password": PASSWORD, "role": role})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def seed_default_plans(db) -> None:
    """Seed the global plan catalog for tests after the tenant tables are reset."""
    from sqlalchemy import select

    from app.models.plan import Plan

    existing_keys = set(db.scalars(select(Plan.key)).all())
    plans = [
        Plan(key="starter", name="Starter", monthly_price=2250, yearly_price=25200,
             included_minutes=300, max_call_minutes=5, is_custom=False),
        Plan(key="growth", name="Growth", monthly_price=5700, yearly_price=66000,
             included_minutes=1000, max_call_minutes=5, is_custom=False),
        Plan(key="business", name="Business", monthly_price=14250, yearly_price=165000,
             included_minutes=2500, max_call_minutes=5, is_custom=False),
        Plan(key="enterprise", name="Enterprise", monthly_price=None, yearly_price=None,
             included_minutes=0, max_call_minutes=5, is_custom=True),
    ]
    db.add_all([plan for plan in plans if plan.key not in existing_keys])
    db.commit()


def make_customer(client: TestClient, token: str, name: str = "Asha", phone: str = "+919876543210") -> dict:
    resp = client.post("/api/v1/customers", headers=auth_headers(token),
                       json={"name": name, "phone": phone})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def make_appointment(client: TestClient, token: str, customer_id: int,
                     day: str = "2030-01-15", at: str = "10:00", **extra) -> dict:
    resp = client.post("/api/v1/appointments", headers=auth_headers(token), json={
        "customer_id": customer_id, "appointment_date": day, "appointment_time": at, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def make_agent(db, client_id: int, name: str = "Agent", **kw):
    """Insert an agent directly (the agent API arrives in Stage 8)."""
    from app.models.agent import Agent

    agent = Agent(client_id=client_id, name=name, provider="sarvam", **kw)
    db.add(agent)
    db.commit()
    return agent


def make_call(db, client_id: int, **kw):
    """Insert a call directly (calls are created by provider webhooks in Stage 9)."""
    from app.models.call import Call
    from app.models.enums import CallDirection, CallStatus

    defaults = dict(phone_number="+919876543210", direction=CallDirection.INBOUND,
                    status=CallStatus.COMPLETED)
    call = Call(client_id=client_id, **{**defaults, **kw})
    db.add(call)
    db.commit()
    return call


def create_agent(client: TestClient, token: str, name: str = "Zoya", **extra) -> dict:
    client_response = client.get("/api/v1/clients/me", headers=auth_headers(token))
    assert client_response.status_code == 200, client_response.text
    client_id = client_response.json()["data"]["id"]
    resp = create_admin_agent(client, client_id, name=name, **extra)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def super_admin_headers(client: TestClient) -> dict:
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    email = "test-agentlink-superadmin@example.com"
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)) is None:
            make_user(db, None, UserRole.SUPER_ADMIN, email)
    return auth_headers(login_token(client, email))


def create_admin_agent(
    client: TestClient, client_id: int, name: str = "Zoya", **extra,
):
    headers = super_admin_headers(client)
    return client.post(
        f"/api/v1/admin/clients/{client_id}/agents",
        headers=headers,
        json={"name": name, **extra},
    )


def webhook_body(**overrides) -> dict:
    """A minimal, valid Sarvam envelope; override event_type/call/appointment as needed."""
    body = {"event_id": "evt-1", "event_type": "call_started", "agent_id": "agent-ref-1"}
    body.update(overrides)
    return body


def send_webhook(client: TestClient, body: dict, secret: str = "test-sarvam-webhook-secret",
                 signature: str | None = "__compute__") -> "httpx.Response":
    import hashlib
    import hmac
    import json

    raw = json.dumps(body).encode()
    if signature == "__compute__":
        signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Sarvam-Signature"] = signature
    return client.post("/api/v1/webhooks/sarvam", content=raw, headers=headers)
