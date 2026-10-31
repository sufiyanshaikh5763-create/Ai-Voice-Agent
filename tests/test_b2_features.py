"""Tests for Task B2:
1. Plans and Subscriptions:
   - minutes_for_call calculation
   - GET /plans (public)
   - GET /billing/me (active client member, usage, alerts, minute packs)
2. Business Profile Bundle:
   - GET /business (structure, hours, services, staff, no PIN)
   - PATCH /business (ClientAdminOrElevated RBAC, validations, atomic replacement, audit log)
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.business_profile import BusinessHour, Service, StaffMember
from app.models.call import Call
from app.models.client import Client
from app.models.enums import AccessStatus, CallDirection, CallStatus, PlanKey
from app.models.plan import MinutePack, Plan, Subscription
from app.services.billing_service import minutes_for_call
from tests.helpers import (auth_headers, create_staff, elevated_headers,
                           login_token, make_elevation_token, register, register_ok)


# ---------------- 1. MINUTES CALCULATION ----------------

def test_minutes_for_call():
    assert minutes_for_call(None) == 0
    assert minutes_for_call(0) == 0
    assert minutes_for_call(-5) == 0
    assert minutes_for_call(1) == 1
    assert minutes_for_call(30) == 1
    assert minutes_for_call(59) == 1
    assert minutes_for_call(60) == 1
    assert minutes_for_call(61) == 2
    assert minutes_for_call(120) == 2
    assert minutes_for_call(121) == 3


# ---------------- 2. GET /plans ----------------

def test_get_plans_public(client, db):
    resp = client.get("/api/v1/plans")
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) == 4

    plans_by_key = {p["key"]: p for p in plans}
    assert "starter" in plans_by_key
    assert "growth" in plans_by_key
    assert "business" in plans_by_key
    assert "enterprise" in plans_by_key

    starter = plans_by_key["starter"]
    assert starter["monthly_price"] == 2250
    assert starter["yearly_price"] == 25200
    assert starter["included_minutes"] == 300
    assert starter["max_call_minutes"] == 5
    assert starter["is_custom"] is False

    growth = plans_by_key["growth"]
    assert growth["monthly_price"] == 5700
    assert growth["yearly_price"] == 66000
    assert growth["included_minutes"] == 1000
    assert growth["max_call_minutes"] == 5
    assert growth["is_custom"] is False

    business = plans_by_key["business"]
    assert business["monthly_price"] == 14250
    assert business["yearly_price"] == 165000
    assert business["included_minutes"] == 2500
    assert business["max_call_minutes"] == 5
    assert business["is_custom"] is False

    enterprise = plans_by_key["enterprise"]
    assert enterprise["monthly_price"] is None
    assert enterprise["yearly_price"] is None
    assert enterprise["is_custom"] is True
    assert enterprise["max_call_minutes"] == 5

    # Also test root mount /plans
    root_resp = client.get("/plans")
    assert root_resp.status_code == 200
    assert len(root_resp.json()) == 4


# ---------------- 3. GET /billing/me ----------------

def test_billing_me_requires_active_client(client, db):
    # Unauthenticated -> 401
    resp_unauth = client.get("/api/v1/billing/me")
    assert resp_unauth.status_code == 401

    # Pending payment client -> 403
    reg_pending = register(client, "pending_bill@test.com", "Pending Biz")
    token = reg_pending.json()["data"]["tokens"]["access_token"]
    resp_pending = client.get("/api/v1/billing/me", headers=auth_headers(token))
    assert resp_pending.status_code == 403
    assert resp_pending.json()["code"] == "ACCESS_NOT_APPROVED"


def test_billing_me_success_and_alerts(client, db):
    reg = register_ok(client, "billing_user@test.com")
    token = reg["tokens"]["access_token"]
    cid = reg["user"]["client_id"]

    resp = client.get("/api/v1/billing/me", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()

    assert data["plan"] == "growth"
    assert data["billing_cycle"] == "monthly"
    assert data["minutes_limit"] == 1000
    assert data["minutes_used"] == 0
    assert data["minutes_remaining"] == 1000
    assert data["usage_percent"] == 0.0
    assert data["alert"] == "none"
    assert data["next_payment_amount"] == 5700
    assert data["renews_on"] is not None

    # Simulate calls to test warning alert (>= 80%)
    # Add a call with 800 minutes = 48000 seconds
    c1 = Call(
        client_id=cid,
        phone_number="+919876543210",
        direction=CallDirection.INBOUND,
        status=CallStatus.COMPLETED,
        duration=48000,
        started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(c1)
    db.commit()

    resp_warn = client.get("/api/v1/billing/me", headers=auth_headers(token))
    data_warn = resp_warn.json()
    assert data_warn["minutes_used"] == 800
    assert data_warn["minutes_remaining"] == 200
    assert data_warn["usage_percent"] == 80.0
    assert data_warn["alert"] == "warning"

    # Simulate limit alert (>= 100%)
    c2 = Call(
        client_id=cid,
        phone_number="+919876543211",
        direction=CallDirection.INBOUND,
        status=CallStatus.COMPLETED,
        duration=12060,  # 201 minutes -> ceil = 201
        started_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(c2)
    db.commit()

    resp_limit = client.get("/api/v1/billing/me", headers=auth_headers(token))
    data_limit = resp_limit.json()
    assert data_limit["minutes_used"] == 1001
    assert data_limit["minutes_remaining"] == 0
    assert data_limit["usage_percent"] == 100.1
    assert data_limit["alert"] == "limit"

    # Add minute pack of 500 minutes
    user_id = reg["user"]["id"]
    pack = MinutePack(client_id=cid, minutes=500, added_by_user_id=user_id, note="Addon pack")
    db.add(pack)
    db.commit()

    resp_pack = client.get("/api/v1/billing/me", headers=auth_headers(token))
    data_pack = resp_pack.json()
    assert data_pack["minutes_limit"] == 1500
    assert data_pack["minutes_remaining"] == 499
    assert data_pack["alert"] == "none"  # 1001 / 1500 = 66.73%


# ---------------- 4. GET /business ----------------

def test_get_business_bundle(client, db):
    reg = register_ok(client, "bizbundle@test.com")
    token = reg["tokens"]["access_token"]

    resp = client.get("/api/v1/business", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()

    # Verify root keys
    assert "business" in data
    assert "hours" in data
    assert "services" in data
    assert "staff" in data
    assert data["timezone"] == "Asia/Kolkata"

    # Verify business info
    b = data["business"]
    assert b["id"] == reg["user"]["client_id"]
    assert b["name"] == "Biz"
    assert b["plan"] == "growth"
    assert b["minutes_used"] == 0
    assert b["minutes_limit"] == 1000
    assert b["status"] == "active"
    assert b["renews_on"] is not None
    # PIN should NEVER be in business info
    assert "pin" not in b
    assert "pin_encrypted" not in b

    # Verify default hours (7 items)
    hours = data["hours"]
    assert len(hours) == 7
    # Mon-Fri: 09:00 - 18:00
    for day in range(5):
        assert hours[day]["open"] == "09:00"
        assert hours[day]["close"] == "18:00"
        assert hours[day]["closed"] is False
    # Sat: 09:00 - 14:00
    assert hours[5]["open"] == "09:00"
    assert hours[5]["close"] == "14:00"
    assert hours[5]["closed"] is False
    # Sun: closed
    assert hours[6]["closed"] is True


# ---------------- 5. PATCH /business ----------------

def test_patch_business_rbac(client, db):
    reg = register_ok(client, "patch_rbac@test.com")
    cid = reg["user"]["client_id"]
    admin_token = reg["tokens"]["access_token"]

    # Create staff user
    staff = create_staff(client, admin_token, "staff_patch@test.com", "client_staff")
    staff_token = login_token(client, "staff_patch@test.com")
    staff_id = staff["id"]

    valid_payload = {
        "services": ["Consultation", "Follow-up"]
    }

    # Staff without elevation -> 403
    resp_staff_no_elev = client.patch(
        "/api/v1/business",
        headers=auth_headers(staff_token),
        json=valid_payload,
    )
    assert resp_staff_no_elev.status_code == 403

    # Staff with elevation -> 200
    elev_tok = make_elevation_token(staff_id, cid)
    resp_staff_elev = client.patch(
        "/api/v1/business",
        headers=elevated_headers(staff_token, elev_tok),
        json=valid_payload,
    )
    assert resp_staff_elev.status_code == 200
    assert resp_staff_elev.json()["services"] == ["Consultation", "Follow-up"]

    # Admin -> 200
    admin_payload = {
        "services": ["Consultation", "Follow-up", "VIP Service"]
    }
    resp_admin = client.patch(
        "/api/v1/business",
        headers=auth_headers(admin_token),
        json=admin_payload,
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["services"] == ["Consultation", "Follow-up", "VIP Service"]


def test_patch_business_validations(client, db):
    reg = register_ok(client, "biz_val@test.com")
    token = reg["tokens"]["access_token"]
    h = auth_headers(token)

    # 1. Hours must have exactly 7 entries
    resp_bad_len = client.patch("/api/v1/business", headers=h, json={
        "hours": [{"open": "09:00", "close": "18:00", "closed": False}] * 6
    })
    assert resp_bad_len.status_code == 422

    # 2. open >= close when not closed
    bad_hours = [{"open": "09:00", "close": "18:00", "closed": False}] * 6 + [
        {"open": "18:00", "close": "09:00", "closed": False}
    ]
    resp_bad_times = client.patch("/api/v1/business", headers=h, json={"hours": bad_hours})
    assert resp_bad_times.status_code == 422

    # 3. Services duplicate
    resp_dup_svc = client.patch("/api/v1/business", headers=h, json={
        "services": ["Service A", "Service A"]
    })
    assert resp_dup_svc.status_code == 422

    # 4. Service name > 60 chars
    resp_long_svc = client.patch("/api/v1/business", headers=h, json={
        "services": ["A" * 61]
    })
    assert resp_long_svc.status_code == 422

    # 5. Services count > 50
    resp_too_many_svc = client.patch("/api/v1/business", headers=h, json={
        "services": [f"Service {i}" for i in range(51)]
    })
    assert resp_too_many_svc.status_code == 422

    # 6. Staff days must have exactly 7 flags
    resp_bad_days = client.patch("/api/v1/business", headers=h, json={
        "staff": [{"name": "Doc", "title": "Doctor", "days": [True, True]}]
    })
    assert resp_bad_days.status_code == 422

    # 7. Staff count > 50
    resp_too_many_staff = client.patch("/api/v1/business", headers=h, json={
        "staff": [{"name": f"Staff {i}", "title": "Role", "days": [True]*7} for i in range(51)]
    })
    assert resp_too_many_staff.status_code == 422


def test_patch_business_atomic_replacement_and_audit_log(client, db):
    reg = register_ok(client, "biz_atomic@test.com")
    cid = reg["user"]["client_id"]
    token = reg["tokens"]["access_token"]
    h = auth_headers(token)

    new_hours = [
        {"open": "10:00", "close": "19:00", "closed": False},  # Mon
        {"open": "10:00", "close": "19:00", "closed": False},  # Tue
        {"open": "10:00", "close": "19:00", "closed": False},  # Wed
        {"open": "10:00", "close": "19:00", "closed": False},  # Thu
        {"open": "10:00", "close": "19:00", "closed": False},  # Fri
        {"open": "11:00", "close": "15:00", "closed": False},  # Sat
        {"open": "00:00", "close": "00:00", "closed": True},   # Sun
    ]
    new_services = ["General Consultation", "Dental Cleaning"]
    new_staff = [
        {"name": "Dr. Sarah", "title": "Senior Dentist", "days": [True, True, True, True, True, False, False]},
        {"name": "Nurse Joy", "title": "Head Nurse", "days": [True, True, True, True, True, True, False]}
    ]

    resp = client.patch("/api/v1/business", headers=h, json={
        "hours": new_hours,
        "services": new_services,
        "staff": new_staff,
    })
    assert resp.status_code == 200
    bundle = resp.json()

    # Check response contents
    assert len(bundle["hours"]) == 7
    assert bundle["hours"][0]["open"] == "10:00"
    assert bundle["hours"][0]["close"] == "19:00"
    assert bundle["services"] == new_services
    assert len(bundle["staff"]) == 2
    assert bundle["staff"][0]["name"] == "Dr. Sarah"
    assert bundle["staff"][0]["days"] == [True, True, True, True, True, False, False]

    # Verify DB persistence
    db_services = db.scalars(
        select(Service).where(Service.client_id == cid).order_by(Service.sort_order)
    ).all()
    assert [s.name for s in db_services] == new_services

    db_staff = db.scalars(
        select(StaffMember).where(StaffMember.client_id == cid).order_by(StaffMember.id)
    ).all()
    assert len(db_staff) == 2
    assert db_staff[0].name == "Dr. Sarah"
    assert db_staff[0].available_days == [True, True, True, True, True, False, False]

    # Verify audit log entry
    audit = db.scalars(
        select(AuditLog)
        .where(AuditLog.client_id == cid, AuditLog.action == "business.update")
    ).all()
    assert len(audit) >= 1
    last_entry = audit[-1]
    assert last_entry.details["updated_fields"] == ["hours", "services", "staff"]


# ---------------- 6. TENANT ISOLATION TESTS ----------------

def test_billing_me_tenant_isolation(client, db):
    # Register Tenant A
    reg_a = register_ok(client, "tenant_a@test.com")
    token_a = reg_a["tokens"]["access_token"]
    cid_a = reg_a["user"]["client_id"]

    # Register Tenant B
    reg_b = register_ok(client, "tenant_b@test.com")
    token_b = reg_b["tokens"]["access_token"]
    cid_b = reg_b["user"]["client_id"]

    # Add call to Tenant A only (100 minutes = 6000 seconds)
    c_a = Call(
        client_id=cid_a,
        phone_number="+919876543210",
        direction=CallDirection.INBOUND,
        status=CallStatus.COMPLETED,
        duration=6000,
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(c_a)
    db.commit()

    # Query Tenant A -> 100 minutes used
    resp_a = client.get("/api/v1/billing/me", headers=auth_headers(token_a))
    assert resp_a.status_code == 200
    assert resp_a.json()["minutes_used"] == 100

    # Query Tenant B -> 0 minutes used (isolated from Tenant A)
    resp_b = client.get("/api/v1/billing/me", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    assert resp_b.json()["minutes_used"] == 0


def test_business_bundle_tenant_isolation(client, db):
    # Register Tenant A and patch custom services
    reg_a = register_ok(client, "biz_tenant_a@test.com")
    token_a = reg_a["tokens"]["access_token"]
    cid_a = reg_a["user"]["client_id"]

    client.patch(
        "/api/v1/business",
        headers=auth_headers(token_a),
        json={"services": ["Tenant A Service 1", "Tenant A Service 2"]},
    )

    # Register Tenant B
    reg_b = register_ok(client, "biz_tenant_b@test.com")
    token_b = reg_b["tokens"]["access_token"]
    cid_b = reg_b["user"]["client_id"]

    # Tenant B queries business bundle
    resp_b = client.get("/api/v1/business", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    bundle_b = resp_b.json()

    assert bundle_b["business"]["id"] == cid_b
    assert bundle_b["business"]["id"] != cid_a
    # Tenant B has no services seeded by default, isolated from Tenant A
    assert bundle_b["services"] == []
