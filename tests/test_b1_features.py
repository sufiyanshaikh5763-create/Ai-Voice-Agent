"""Tests for Task B1:
1. Access status enforcement and onboarding dependency
2. Refresh token rotation, replay revocation, and logout
3. Staff PIN encryption, verification, lockouts, and ClientAdminOrElevated dependency
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import (create_access_token, create_elevation_token,
                               create_refresh_token)
from app.models.client import Client
from app.models.enums import AccessStatus, OnboardingStage, UserRole
from app.models.refresh_token import RefreshToken
from app.models.staff_pin import PinAttempt, StaffPin
from app.models.user import User
from tests.helpers import (PASSWORD, auth_headers, create_staff,
                           elevated_headers, login_token, make_elevation_token,
                           create_agent, register, register_ok)


# ---------------- 1. ACCESS STATUS ----------------

def test_register_creates_pending_payment_client(client, db):
    resp = register(client, "pending@test.com", "Pending Biz", phone="+919876543210", country_code="+91")
    assert resp.status_code == 201
    data = resp.json()["data"]
    user = data["user"]
    assert user["access_status"] == "pending_payment"
    assert user["email_verified"] is False
    assert data["tokens"]["access_token"] and data["tokens"]["refresh_token"]

    db_client = db.scalar(select(Client).where(Client.email == "pending@test.com"))
    assert db_client.access_status == AccessStatus.PENDING_PAYMENT
    assert db_client.phone == "+919876543210"
    assert db_client.country_code == "+91"


def test_pending_client_rejected_by_client_admin_and_member_dependencies(client, db):
    # Register client (defaults to pending_payment, active=False in helper)
    resp = register(client, "locked@test.com", "Locked Biz")
    assert resp.status_code == 201
    data = resp.json()["data"]
    token = data["tokens"]["access_token"]
    h = auth_headers(token)

    # Calling an endpoint requiring ClientAdminUser (e.g. GET /api/v1/users)
    res_users = client.get("/api/v1/users", headers=h)
    assert res_users.status_code == 403
    assert res_users.json() == {"detail": "Access not approved", "code": "ACCESS_NOT_APPROVED"}

    # Calling an endpoint requiring ClientMemberUser (e.g. GET /api/v1/appointments)
    res_appts = client.get("/api/v1/appointments", headers=h)
    assert res_appts.status_code == 403
    assert res_appts.json() == {"detail": "Access not approved", "code": "ACCESS_NOT_APPROVED"}

    # Once activated, calls succeed
    cid = data["user"]["client_id"]
    db_client = db.get(Client, cid)
    db_client.access_status = AccessStatus.ACTIVE
    db.commit()

    res_ok = client.get("/api/v1/appointments", headers=h)
    assert res_ok.status_code == 200


def test_user_out_includes_access_fields_on_login_and_me(client, db):
    reg = register_ok(client, "userfields@test.com")
    token = reg["tokens"]["access_token"]

    # /auth/me
    me_resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    assert me_data["access_status"] == "active"
    assert me_data["onboarding_stage"] == "setup_complete"
    assert me_data["email_verified"] is False

    # login
    login_resp = client.post("/api/v1/auth/login", json={"email": "userfields@test.com", "password": PASSWORD})
    assert login_resp.status_code == 200
    u_data = login_resp.json()["data"]["user"]
    assert u_data["access_status"] == "active"
    assert u_data["onboarding_stage"] == "setup_complete"
    assert u_data["email_verified"] is False


# ---------------- 2. REFRESH TOKENS AND LOGOUT ----------------

def test_refresh_token_rotation_and_record_created(client, db):
    reg = register_ok(client, "rot@test.com")
    refresh1 = reg["tokens"]["refresh_token"]

    # Verify record in DB
    settings = get_settings()
    claims1 = jwt.decode(refresh1, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    jti1 = claims1["jti"]
    rec1 = db.get(RefreshToken, jti1)
    assert rec1 is not None and rec1.revoked_at is None

    # Rotate token
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert resp.status_code == 200
    new_tokens = resp.json()["data"]
    refresh2 = new_tokens["refresh_token"]
    claims2 = jwt.decode(refresh2, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    jti2 = claims2["jti"]

    db.refresh(rec1)
    assert rec1.revoked_at is not None
    assert rec1.replaced_by == jti2

    rec2 = db.get(RefreshToken, jti2)
    assert rec2 is not None and rec2.revoked_at is None


def test_replaying_revoked_token_revokes_all_tokens_for_user(client, db):
    reg = register_ok(client, "replay@test.com")
    uid = reg["user"]["id"]
    t1 = reg["tokens"]["refresh_token"]

    # Rotate t1 -> t2
    resp1 = client.post("/api/v1/auth/refresh", json={"refresh_token": t1})
    assert resp1.status_code == 200
    t2 = resp1.json()["data"]["refresh_token"]

    # Rotate t2 -> t3
    resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": t2})
    assert resp2.status_code == 200
    t3 = resp2.json()["data"]["refresh_token"]

    # Replay revoked t1!
    replay_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": t1})
    assert replay_resp.status_code == 401

    # ALL tokens for that user must now be revoked
    active_tokens = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None))
    ).all()
    assert len(active_tokens) == 0

    # Even t3 is now revoked and rejected
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t3}).status_code == 401


def test_logout_revokes_token_and_succeeds_even_if_invalid(client, db):
    reg = register_ok(client, "logout@test.com")
    ref = reg["tokens"]["refresh_token"]

    # Valid logout
    resp = client.post("/api/v1/auth/logout", json={"refresh_token": ref})
    assert resp.status_code == 204

    # Using the token now fails
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": ref}).status_code == 401

    # Logout with invalid token succeeds with 204
    resp_invalid = client.post("/api/v1/auth/logout", json={"refresh_token": "invalid.jwt.token"})
    assert resp_invalid.status_code == 204


# ---------------- 3. STAFF PIN AND ELEVATION ----------------

def test_pin_change_and_verify(client):
    admin = register_ok(client, "pinadmin@test.com")
    admin_token = admin["tokens"]["access_token"]
    h_admin = auth_headers(admin_token)

    # 1. Initially no PIN set: change PIN with empty currentPin
    res = client.post("/api/v1/pin/change", headers=h_admin,
                      json={"currentPin": "", "newPin": "1234", "confirmPin": "1234"})
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # 2. Staff user verifies PIN
    staff_user = create_staff(client, admin_token, "pinstaff@test.com")
    staff_tok = login_token(client, "pinstaff@test.com")
    h_staff = auth_headers(staff_tok)

    v_ok = client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "1234"})
    assert v_ok.status_code == 200
    v_data = v_ok.json()
    assert v_data["ok"] is True
    assert v_data["expires_in"] == 900
    assert "elevation_token" in v_data

    # Verify JWT claims
    claims = jwt.decode(v_data["elevation_token"], get_settings().jwt_secret_key,
                        algorithms=[get_settings().jwt_algorithm])
    assert claims["elev"] is True
    assert claims["sub"] == str(staff_user["id"])
    assert claims["client_id"] == staff_user["client_id"]


def test_wrong_pin_tries_left_and_lockout(client, db):
    admin = register_ok(client, "locktest@test.com")
    admin_token = admin["tokens"]["access_token"]
    client.post("/api/v1/pin/change", headers=auth_headers(admin_token),
                json={"currentPin": "", "newPin": "9999", "confirmPin": "9999"})

    create_staff(client, admin_token, "wrongpin@test.com")
    staff_tok = login_token(client, "wrongpin@test.com")
    h_staff = auth_headers(staff_tok)

    # Attempt 1 -> 4 tries left
    r1 = client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "0000"})
    assert r1.status_code == 400
    assert r1.json() == {"detail": "Wrong PIN. 4 tries left.", "code": "PIN_WRONG", "tries_left": 4}

    # Attempts 2, 3, 4
    client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "0000"})
    client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "0000"})
    r4 = client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "0000"})
    assert r4.status_code == 400
    assert r4.json()["tries_left"] == 1

    # Attempt 5 -> lock for 15 minutes (900 seconds)
    r5 = client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "0000"})
    assert r5.status_code == 400
    assert r5.json()["code"] == "PIN_LOCKED"
    assert r5.json()["retry_after_seconds"] > 800

    # 6th attempt while locked returns PIN_LOCKED immediately
    r6 = client.post("/api/v1/pin/verify", headers=h_staff, json={"pin": "9999"})
    assert r6.status_code == 400
    assert r6.json()["code"] == "PIN_LOCKED"


def test_client_admin_or_elevated_on_mutating_endpoints(client):
    admin = register_ok(client, "elevtest@test.com")
    admin_tok = admin["tokens"]["access_token"]
    cid = admin["user"]["client_id"]

    staff_u = create_staff(client, admin_tok, "staffelev@test.com")
    staff_tok = login_token(client, "staffelev@test.com")

    # Set PIN
    client.post("/api/v1/pin/change", headers=auth_headers(admin_tok),
                json={"currentPin": "", "newPin": "4321", "confirmPin": "4321"})

    # Elevate staff
    elev_resp = client.post("/api/v1/pin/verify", headers=auth_headers(staff_tok), json={"pin": "4321"})
    elev_token = elev_resp.json()["elevation_token"]

    h_staff_plain = auth_headers(staff_tok)
    h_staff_elev = elevated_headers(staff_tok, elev_token)

    # 1. Customers POST and PATCH
    # Without elevation: 403
    assert client.post("/api/v1/customers", headers=h_staff_plain,
                       json={"name": "Cust", "phone": "+919876543001"}).status_code == 403

    # With elevation: 201
    c_resp = client.post("/api/v1/customers", headers=h_staff_elev,
                         json={"name": "Cust", "phone": "+919876543001"})
    assert c_resp.status_code == 201
    cust_id = c_resp.json()["data"]["id"]

    # Customer PATCH without elevation: 403
    assert client.patch(f"/api/v1/customers/{cust_id}", headers=h_staff_plain,
                        json={"name": "Cust Renamed"}).status_code == 403
    # Customer PATCH with elevation: 200
    assert client.patch(f"/api/v1/customers/{cust_id}", headers=h_staff_elev,
                        json={"name": "Cust Renamed"}).status_code == 200

    # 2. Agents POST and PATCH
    assert client.post("/api/v1/agents", headers=h_staff_plain,
                       json={"name": "Agent A"}).status_code == 403
    assert client.post("/api/v1/agents", headers=h_staff_elev,
                       json={"name": "Agent A"}).status_code == 403
    ag = create_agent(client, admin_tok, "Agent A")
    ag_id = ag["id"]

    assert client.patch(f"/api/v1/agents/{ag_id}", headers=h_staff_plain,
                        json={"name": "Agent B"}).status_code == 403
    assert client.patch(f"/api/v1/agents/{ag_id}", headers=h_staff_elev,
                        json={"name": "Agent B"}).status_code == 403
    assert client.get(
        f"/api/v1/agents/{ag_id}", headers=auth_headers(admin_tok)
    ).json()["data"]["name"] == "Agent A"
    assert client.patch(f"/api/v1/agents/{ag_id}", headers=h_staff_elev,
                        json={"status": "inactive"}).status_code == 200

    # 3. Appointments POST and PATCH
    assert client.post("/api/v1/appointments", headers=h_staff_plain,
                       json={"customer_id": cust_id, "appointment_date": "2030-05-01",
                             "appointment_time": "11:00"}).status_code == 403
    apt_resp = client.post("/api/v1/appointments", headers=h_staff_elev,
                           json={"customer_id": cust_id, "appointment_date": "2030-05-01",
                                 "appointment_time": "11:00"})
    assert apt_resp.status_code == 201
    apt_id = apt_resp.json()["data"]["id"]

    assert client.patch(f"/api/v1/appointments/{apt_id}", headers=h_staff_plain,
                        json={"status": "confirmed"}).status_code == 403
    assert client.patch(f"/api/v1/appointments/{apt_id}", headers=h_staff_elev,
                        json={"status": "confirmed"}).status_code == 200

    # 4. Appointments cancel and reschedule
    assert client.post(f"/api/v1/appointments/{apt_id}/reschedule", headers=h_staff_plain,
                       json={"new_date": "2030-05-02", "new_time": "12:00"}).status_code == 403
    assert client.post(f"/api/v1/appointments/{apt_id}/reschedule", headers=h_staff_elev,
                       json={"new_date": "2030-05-02", "new_time": "12:00"}).status_code == 200

    # Cross-tenant / forged elevation token rejected
    forged_elev_token = make_elevation_token(staff_u["id"], "other-tenant-id")
    h_cross_tenant = elevated_headers(staff_tok, forged_elev_token)
    assert client.patch(f"/api/v1/agents/{ag_id}", headers=h_cross_tenant,
                        json={"name": "Agent Cross"}).status_code == 403


    assert client.post(f"/api/v1/appointments/{apt_id}/cancel", headers=h_staff_plain).status_code == 403
    assert client.post(f"/api/v1/appointments/{apt_id}/cancel", headers=h_staff_elev).status_code == 200

    # 5. Delete remains client_admin only
    assert client.delete(f"/api/v1/customers/{cust_id}", headers=h_staff_elev).status_code == 403
    assert client.delete(f"/api/v1/agents/{ag_id}", headers=h_staff_elev).status_code == 403
    assert client.delete(f"/api/v1/appointments/{apt_id}", headers=h_staff_elev).status_code == 403
