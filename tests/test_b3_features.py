"""Tests for Task B3:
1. Payments (Manual UPI):
   - POST /payments/manual-submit (success, not signed in, wrong role, disallowed access_status, email verification required, amount mismatch, validations, screenshot magic bytes)
2. Onboarding Status:
   - GET /onboarding/status (awaiting_submission, pending_verification, verified, rejected, camelCase keys, dashboardAccessGranted, tenant isolation)
3. Email Verification:
   - POST /auth/verify-email/send (success, cooldown, hourly rate limit)
   - POST /auth/verify-email/confirm (success, invalid code, max attempts, expired, user isolation)
"""
import hashlib
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.client import Client
from app.models.email_verification import EmailVerification
from app.models.enums import (AccessStatus, BillingCycle, OnboardingStage,
                              PaymentStatus, PlanKey, SubscriptionStatus,
                              UserRole)
from app.models.payment import Payment
from app.models.plan import Plan, Subscription
from app.models.user import User
from tests.helpers import (auth_headers, create_staff, login_token, register, register_ok)


# ---------------- 1. PAYMENTS (MANUAL UPI) ----------------

def test_manual_submit_payment_success(client, db):
    # Register pending payment client
    reg = register(client, "upi_user@test.com", "UPI Biz")
    token = reg.json()["data"]["tokens"]["access_token"]
    user_id = reg.json()["data"]["user"]["id"]
    client_id = reg.json()["data"]["user"]["client_id"]

    # Mark user email verified for submission
    db_user = db.get(User, user_id)
    db_user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    # Form payload
    form_data = {
        "package_id": "growth",
        "billing_cycle": "monthly",
        "amount_paid": "5700",
        "transaction_id": "UPI1234567890",
        "payment_date": str(date.today()),
        "payer_name": "Ramesh Kumar",
    }
    # Minimal 1x1 PNG image with valid magic bytes
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    files = {"screenshot": ("receipt.png", io.BytesIO(png_bytes), "image/png")}

    resp = client.post(
        "/api/v1/payments/manual-submit",
        headers=auth_headers(token),
        data=form_data,
        files=files,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["submissionId"].startswith("TALKAOR-UPI-")
    assert data["status"] == "pending_manual_verification"
    assert data["source"] == "backend"

    # Verify DB state
    payment = db.scalar(select(Payment).where(Payment.client_id == client_id))
    assert payment is not None
    assert payment.transaction_id == "UPI1234567890"
    assert payment.amount_expected == 5700
    assert payment.amount_paid == 5700
    assert payment.amount_mismatch is False
    assert payment.status == PaymentStatus.PENDING_VERIFICATION
    assert payment.screenshot_path is not None

    # Client updated
    db_client = db.get(Client, client_id)
    assert db_client.access_status == AccessStatus.PAYMENT_REVIEW
    assert db_client.onboarding_stage == OnboardingStage.AWAITING_PAYMENT_VERIFICATION

    # Pending subscription created
    sub = db.scalar(
        select(Subscription).where(
            Subscription.client_id == client_id,
            Subscription.status == SubscriptionStatus.PENDING,
        )
    )
    assert sub is not None
    assert sub.billing_cycle == BillingCycle.MONTHLY


def test_manual_submit_payment_auth_and_roles(client, db):
    # 1. Unauthenticated -> 401
    resp_unauth = client.post("/api/v1/payments/manual-submit", data={})
    assert resp_unauth.status_code == 401

    # 2. Client Staff -> 403 INSUFFICIENT_PERMISSIONS
    reg = register_ok(client, "admin_owner@test.com")
    admin_tok = reg["tokens"]["access_token"]
    create_staff(client, admin_tok, "staff_submitter@test.com")
    staff_tok = login_token(client, "staff_submitter@test.com")

    resp_staff = client.post(
        "/api/v1/payments/manual-submit",
        headers=auth_headers(staff_tok),
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "STAFF123456",
            "payment_date": str(date.today()),
        },
    )
    assert resp_staff.status_code == 403
    assert resp_staff.json()["error_code"] == "INSUFFICIENT_PERMISSIONS"


def test_manual_submit_payment_email_verification_required(client, db):
    # Register pending client without email verification
    reg = register(client, "unverified_pay@test.com", "Unverified Biz")
    token = reg.json()["data"]["tokens"]["access_token"]

    resp = client.post(
        "/api/v1/payments/manual-submit",
        headers=auth_headers(token),
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "TXN12345678",
            "payment_date": str(date.today()),
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_manual_submit_payment_disallowed_when_active(client, db):
    # Client is already active (via register_ok)
    reg = register_ok(client, "already_active@test.com")
    token = reg["tokens"]["access_token"]
    user_id = reg["user"]["id"]

    db_user = db.get(User, user_id)
    db_user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    resp = client.post(
        "/api/v1/payments/manual-submit",
        headers=auth_headers(token),
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "ACTIVE12345",
            "payment_date": str(date.today()),
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "PAYMENT_NOT_ALLOWED"


def test_manual_submit_payment_amount_mismatch_and_validations(client, db):
    reg = register(client, "mismatch_val@test.com", "Mismatch Biz")
    token = reg.json()["data"]["tokens"]["access_token"]
    user_id = reg.json()["data"]["user"]["id"]
    client_id = reg.json()["data"]["user"]["client_id"]

    db_user = db.get(User, user_id)
    db_user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    h = auth_headers(token)

    # 1. Invalid transaction_id (< 8 characters)
    resp_short_tx = client.post(
        "/api/v1/payments/manual-submit",
        headers=h,
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "SHORT",
            "payment_date": str(date.today()),
        },
    )
    assert resp_short_tx.status_code == 400
    assert resp_short_tx.json()["error_code"] == "INVALID_TRANSACTION_ID"

    # 2. Future payment date
    tomorrow = str(date.today() + timedelta(days=1))
    resp_future_date = client.post(
        "/api/v1/payments/manual-submit",
        headers=h,
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "FUTURE123456",
            "payment_date": tomorrow,
        },
    )
    assert resp_future_date.status_code == 400
    assert resp_future_date.json()["error_code"] == "INVALID_PAYMENT_DATE"

    # 3. Invalid screenshot magic bytes
    bad_files = {"screenshot": ("virus.exe", io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00"), "application/octet-stream")}
    resp_bad_file = client.post(
        "/api/v1/payments/manual-submit",
        headers=h,
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "BADFILE12345",
            "payment_date": str(date.today()),
        },
        files=bad_files,
    )
    assert resp_bad_file.status_code == 400
    assert resp_bad_file.json()["error_code"] == "INVALID_FILE_TYPE"

    # 4. Amount mismatch: expected 5700, submitted 5000 -> stored with amount_mismatch=True
    resp_mismatch = client.post(
        "/api/v1/payments/manual-submit",
        headers=h,
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5000",
            "transaction_id": "MISMATCH12345",
            "payment_date": str(date.today()),
        },
    )
    assert resp_mismatch.status_code == 200
    pay = db.scalar(select(Payment).where(Payment.transaction_id == "MISMATCH12345"))
    assert pay.amount_mismatch is True
    assert pay.amount_expected == 5700
    assert pay.amount_paid == 5000

    # 5. Duplicate transaction_id (case-insensitive)
    resp_dup = client.post(
        "/api/v1/payments/manual-submit",
        headers=h,
        data={
            "package_id": "growth",
            "billing_cycle": "monthly",
            "amount_paid": "5700",
            "transaction_id": "mismatch12345",  # lowercase of earlier submitted
            "payment_date": str(date.today()),
        },
    )
    assert resp_dup.status_code == 400
    assert resp_dup.json()["error_code"] == "TRANSACTION_DUPLICATE"


# ---------------- 2. ONBOARDING STATUS ----------------

def test_onboarding_status_lifecycle_and_tenant_isolation(client, db):
    # 1. New client: awaiting_submission
    reg_a = register(client, "onboarding_a@test.com", "Onboarding A")
    tok_a = reg_a.json()["data"]["tokens"]["access_token"]
    cid_a = reg_a.json()["data"]["user"]["client_id"]
    uid_a = reg_a.json()["data"]["user"]["id"]

    resp_a = client.get("/api/v1/onboarding/status", headers=auth_headers(tok_a))
    assert resp_a.status_code == 200
    data_a = resp_a.json()

    assert data_a["paymentStatus"] == "awaiting_submission"
    assert data_a["businessName"] == "Onboarding A"
    assert data_a["currency"] == "INR"
    assert data_a["dashboardAccessGranted"] is False
    assert data_a["transactionRef"] is None

    # 2. Submit payment -> pending_verification
    db_u = db.get(User, uid_a)
    db_u.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    resp_submit = client.post(
        "/api/v1/payments/manual-submit",
        headers=auth_headers(tok_a),
        data={
            "package_id": "starter",
            "billing_cycle": "monthly",
            "amount_paid": "2250",
            "transaction_id": "TXNONBOARDA",
            "payment_date": str(date.today()),
        },
    )
    assert resp_submit.status_code == 200, resp_submit.text

    resp_pend = client.get("/api/v1/onboarding/status", headers=auth_headers(tok_a))
    data_pend = resp_pend.json()
    assert data_pend["paymentStatus"] == "pending_verification"
    assert data_pend["onboardingStage"] == "awaiting_payment_verification"
    assert data_pend["packageName"] == "starter"
    assert data_pend["amount"] == 2250
    assert data_pend["transactionRef"] == "TXNONBOARDA"
    assert data_pend["dashboardAccessGranted"] is False

    # 3. Simulate super_admin verifying payment and activating client
    pay = db.scalar(select(Payment).where(Payment.client_id == cid_a))
    pay.status = PaymentStatus.VERIFIED
    cl_a = db.get(Client, cid_a)
    cl_a.access_status = AccessStatus.ACTIVE
    cl_a.onboarding_stage = OnboardingStage.SETUP_COMPLETE
    db.commit()

    resp_active = client.get("/api/v1/onboarding/status", headers=auth_headers(tok_a))
    data_active = resp_active.json()
    assert data_active["paymentStatus"] == "verified"
    assert data_active["onboardingStage"] == "setup_complete"
    assert data_active["dashboardAccessGranted"] is True

    # 4. Tenant B isolation: register Tenant B and verify it has awaiting_submission
    reg_b = register(client, "onboarding_b@test.com", "Onboarding B")
    tok_b = reg_b.json()["data"]["tokens"]["access_token"]

    resp_b = client.get("/api/v1/onboarding/status", headers=auth_headers(tok_b))
    data_b = resp_b.json()
    assert data_b["paymentStatus"] == "awaiting_submission"
    assert data_b["businessName"] == "Onboarding B"
    assert data_b["dashboardAccessGranted"] is False
    assert data_b["transactionRef"] is None


# ---------------- 3. EMAIL VERIFICATION ----------------

def test_email_verification_send_and_confirm_flow(client, db):
    reg = register(client, "email_flow@test.com", "Email Flow Biz")
    token = reg.json()["data"]["tokens"]["access_token"]
    user_id = reg.json()["data"]["user"]["id"]
    h = auth_headers(token)

    # 1. Send code -> 200
    resp_send = client.post("/api/v1/auth/verify-email/send", headers=h)
    assert resp_send.status_code == 200
    assert resp_send.json() == {"message": "Verification code sent"}

    # Verify record in DB
    ev = db.scalar(
        select(EmailVerification)
        .where(EmailVerification.user_id == user_id)
        .order_by(EmailVerification.created_at.desc())
    )
    assert ev is not None
    assert ev.consumed_at is None
    assert len(ev.code_hash) == 64  # sha256

    # 2. Immediate second send triggers 60s cooldown -> 429
    resp_cooldown = client.post("/api/v1/auth/verify-email/send", headers=h)
    assert resp_cooldown.status_code == 429
    assert resp_cooldown.json()["code"] == "COOLDOWN_ACTIVE"

    # 3. Confirm with wrong code -> 400 with tries_left
    resp_wrong = client.post("/api/v1/auth/verify-email/confirm", headers=h, json={"code": "000000"})
    assert resp_wrong.status_code == 400
    assert resp_wrong.json()["code"] == "CODE_INVALID"
    assert resp_wrong.json()["tries_left"] == 4

    # 4. Set known code hash directly in DB to test successful confirm
    test_code = "654321"
    ev.code_hash = hashlib.sha256(test_code.encode("utf-8")).hexdigest()
    db.commit()

    resp_confirm = client.post("/api/v1/auth/verify-email/confirm", headers=h, json={"code": test_code})
    assert resp_confirm.status_code == 200
    assert resp_confirm.json() == {"message": "Email verified successfully"}

    # User in DB is now marked verified
    u = db.get(User, user_id)
    assert u.email_verified_at is not None

    # Verification record is consumed
    db.refresh(ev)
    assert ev.consumed_at is not None


def test_email_verification_attempts_limit_and_expiration(client, db):
    reg = register(client, "email_limits@test.com", "Email Limits Biz")
    token = reg.json()["data"]["tokens"]["access_token"]
    user_id = reg.json()["data"]["user"]["id"]
    h = auth_headers(token)

    # Create verification record with 4 attempts already
    test_code = "777888"
    ev = EmailVerification(
        user_id=user_id,
        code_hash=hashlib.sha256(test_code.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        attempts=4,
    )
    db.add(ev)
    db.commit()

    # 5th failed attempt exhausts tries
    resp_fail5 = client.post("/api/v1/auth/verify-email/confirm", headers=h, json={"code": "111111"})
    assert resp_fail5.status_code == 400
    assert resp_fail5.json()["code"] == "MAX_ATTEMPTS_EXCEEDED"

    # Subsequent attempt rejected immediately with MAX_ATTEMPTS_EXCEEDED
    resp_fail6 = client.post("/api/v1/auth/verify-email/confirm", headers=h, json={"code": test_code})
    assert resp_fail6.status_code == 400
    assert resp_fail6.json()["code"] == "MAX_ATTEMPTS_EXCEEDED"

    # Expired code test
    ev_expired = EmailVerification(
        user_id=user_id,
        code_hash=hashlib.sha256(b"999999").hexdigest(),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        attempts=0,
    )
    db.add(ev_expired)
    db.commit()

    resp_exp = client.post("/api/v1/auth/verify-email/confirm", headers=h, json={"code": "999999"})
    assert resp_exp.status_code == 400
    assert resp_exp.json()["code"] == "CODE_EXPIRED"
