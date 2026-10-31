import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.enums import CallDirection, CallStatus, UserRole, WebhookEventStatus
from app.models.webhook_event import WebhookEvent
from app.services.audit_service import record_audit
from tests.helpers import (auth_headers, create_staff, login_token,
                           make_appointment, make_call, make_customer, make_user,
                           register_ok, send_webhook, webhook_body)

TOOL_TOKEN = "test-sarvam-webhook-secret"


@pytest.fixture
def watch_tenants(client, db):
    a = register_ok(client, "watch-a@example.com", "Watch A")
    b = register_ok(client, "watch-b@example.com", "Watch B")
    make_user(db, None, UserRole.SUPER_ADMIN, "watch-root@example.com")
    return {
        "a": {
            "id": a["user"]["client_id"],
            "token": a["tokens"]["access_token"],
            "staff": create_staff(client, a["tokens"]["access_token"], "watch-staff-a@example.com"),
        },
        "b": {"id": b["user"]["client_id"], "token": b["tokens"]["access_token"]},
        "staff_token": login_token(client, "watch-staff-a@example.com"),
        "root_token": login_token(client, "watch-root@example.com"),
    }


def _event(db, event_id, client_id, event_type, status, payload=None, created_at=None):
    event = WebhookEvent(
        provider="sarvam", event_id=event_id, event_type=event_type,
        client_id=client_id, status=status, payload=payload or {},
    )
    if created_at:
        event.created_at = created_at
    db.add(event)
    db.commit()
    return event


def _tool_log(db, client_id, tool, success, *, request_id=None, message=None):
    record_audit(
        db, f"sarvam_tool.{tool}", client_id=client_id,
        level="info" if success else "warning", message=message,
        details={
            "tool": tool, "success": success,
            "error_code": None if success else "APPOINTMENT_CONFLICT",
            "duration_ms": 8, "appointment_id": None, "request_id": request_id,
        },
    )
    db.commit()


@pytest.fixture
def watch_records(client, db, watch_tenants):
    event_a = _event(db, "watch-event-a", watch_tenants["a"]["id"], "call_completed",
                     WebhookEventStatus.PROCESSED, {"call": {"phone_number": "+919876543210"}})
    event_b = _event(db, "watch-event-b", watch_tenants["b"]["id"], "appointment_created",
                     WebhookEventStatus.FAILED, {"secret": "not-returned"})
    _tool_log(db, watch_tenants["a"]["id"], "book", True, request_id="watch-req-a")
    _tool_log(db, watch_tenants["b"]["id"], "book", False, message="Slot unavailable")
    customer_a = make_customer(client, watch_tenants["a"]["token"], "A Customer",
                               "+919811111111")
    customer_b = make_customer(client, watch_tenants["b"]["token"], "B Customer",
                               "+919822222222")
    appointment_a = make_appointment(
        client, watch_tenants["a"]["token"], customer_a["id"], "2031-02-01", "09:00")
    appointment_b = make_appointment(
        client, watch_tenants["b"]["token"], customer_b["id"], "2031-02-02", "10:00")
    return {
        "event_a": event_a.id, "event_b": event_b.id,
        "appointment_a": appointment_a["id"], "appointment_b": appointment_b["id"],
    }


def test_all_logwatch_routes_enforce_super_admin_authentication(
    client, watch_tenants, watch_records,
):
    paths = [
        "/api/v1/admin/webhook-events",
        f"/api/v1/admin/webhook-events/{watch_records['event_a']}",
        "/api/v1/admin/tool-calls",
        "/api/v1/admin/appointments",
        "/api/v1/admin/monitoring",
        "/api/v1/admin/health/details",
    ]
    for path in paths:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth_headers(watch_tenants["a"]["token"])).status_code == 403
        assert client.get(path, headers=auth_headers(watch_tenants["staff_token"])).status_code == 403
        assert client.get(path, headers=auth_headers(watch_tenants["root_token"])).status_code == 200


def test_webhook_event_filters_pagination_and_detail_redaction(
    client, db, watch_tenants, watch_records,
):
    client_id = watch_tenants["a"]["id"]
    _event(db, "watch-event-a2", client_id, "call_started", WebhookEventStatus.FAILED,
           {"nested": {
               "customer_phone": "+919876543210", "api_key": "do-not-return",
               "trace": TOOL_TOKEN, "AuthorizationHeader": "private",
               "signature": "signed-value",
           }})
    response = client.get(
        f"/api/v1/admin/webhook-events?client_id={client_id}&status=failed"
        "&event_type=call_started&page=1&limit=1",
        headers=auth_headers(watch_tenants["root_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"] == {"page": 1, "limit": 1, "total": 1}
    assert body["data"][0]["event_id"] == "watch-event-a2"
    assert "payload" not in body["data"][0]

    detail = client.get(
        f"/api/v1/admin/webhook-events/{body['data'][0]['id']}",
        headers=auth_headers(watch_tenants["root_token"]),
    )
    serialized = detail.text
    assert detail.status_code == 200
    assert "do-not-return" not in serialized and "api_key" not in serialized
    assert TOOL_TOKEN not in serialized
    assert "AuthorizationHeader" not in serialized and "signed-value" not in serialized
    assert "+919876543210" not in serialized
    assert detail.json()["payload"]["nested"]["customer_phone"].endswith("3210")


def test_tool_call_filters_pagination_and_no_sensitive_data(
    client, db, watch_tenants, watch_records,
):
    response = client.get(
        f"/api/v1/admin/tool-calls?client_id={watch_tenants['a']['id']}"
        "&tool=book&success=true&page=1&limit=1",
        headers=auth_headers(watch_tenants["root_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["tool"] == "book"
    assert body["data"][0]["request_id"] == "watch-req-a"
    assert TOOL_TOKEN not in response.text


def test_admin_appointments_filters_order_and_pagination(
    client, watch_tenants, watch_records,
):
    response = client.get(
        f"/api/v1/admin/appointments?client_id={watch_tenants['a']['id']}"
        "&status=scheduled&source=manual&page=1&limit=1",
        headers=auth_headers(watch_tenants["root_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"] == {"page": 1, "limit": 1, "total": 1}
    item = body["data"][0]
    assert item["client_id"] == watch_tenants["a"]["id"]
    assert item["business_name"] == "Watch A"
    assert item["source"] == "manual"
    assert item["date"] == "2031-02-01"


def test_monitoring_is_tenant_scoped_and_paginated(client, db, watch_tenants):
    agent_a = Agent(client_id=watch_tenants["a"]["id"], name="A agent",
                    provider="sarvam", provider_agent_id="provider-a")
    agent_b = Agent(client_id=watch_tenants["b"]["id"], name="B agent",
                    provider="sarvam", provider_agent_id=None)
    db.add_all([agent_a, agent_b])
    db.commit()
    make_call(db, watch_tenants["a"]["id"], agent_id=agent_a.id,
              direction=CallDirection.INBOUND, status=CallStatus.COMPLETED)
    _event(db, "monitor-a-failed", watch_tenants["a"]["id"], "call_started",
           WebhookEventStatus.FAILED)
    _event(db, "monitor-b-processed", watch_tenants["b"]["id"], "call_started",
           WebhookEventStatus.PROCESSED)
    _tool_log(db, watch_tenants["a"]["id"], "cancel", False, message="A-only error")
    _tool_log(db, watch_tenants["b"]["id"], "book", False, message="B-only error")

    response = client.get(
        "/api/v1/admin/monitoring?page=1&limit=1",
        headers=auth_headers(watch_tenants["root_token"]),
    )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 2
    rows = client.get(
        "/api/v1/admin/monitoring?page=1&limit=100",
        headers=auth_headers(watch_tenants["root_token"]),
    ).json()["data"]
    by_id = {row["client_id"]: row for row in rows}
    assert by_id[watch_tenants["a"]["id"]]["provider_agent_id_present"] is True
    assert by_id[watch_tenants["b"]["id"]]["provider_agent_id_present"] is False
    assert by_id[watch_tenants["a"]["id"]]["failed_webhook_events_24h"] == 1
    assert by_id[watch_tenants["b"]["id"]]["failed_webhook_events_24h"] == 0
    assert by_id[watch_tenants["a"]["id"]]["last_call_time"] is not None
    assert by_id[watch_tenants["a"]["id"]]["minutes_limit"] == 1000
    assert by_id[watch_tenants["a"]["id"]]["minutes_used"] == 0
    assert by_id[watch_tenants["a"]["id"]]["last_tool_call_error"] == "A-only error"
    assert by_id[watch_tenants["b"]["id"]]["last_tool_call_error"] == "B-only error"
    assert "provider-a" not in response.text


def test_health_details_exposes_presence_booleans_not_secret_values(
    client, watch_tenants,
):
    response = client.get(
        "/api/v1/admin/health/details",
        headers=auth_headers(watch_tenants["root_token"]),
    )
    assert response.status_code == 200
    assert isinstance(response.json()["database_ok"], bool)
    assert isinstance(response.json()["sarvam_webhook_secret_set"], bool)
    assert response.json()["email_backend"] == "console"
    assert TOOL_TOKEN not in response.text


def _tool_url(client_id, action, token=TOOL_TOKEN):
    return f"/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/{action}"


def test_tool_call_audit_records_success_failure_masking_and_request_id(
    client, db, watch_tenants,
):
    client_id = watch_tenants["a"]["id"]
    request_id = "tool-request-123"
    payload = {
        "customer_phone": "+919833344444", "customer_name": "Caller",
        "appointment_date": "2032-05-01", "appointment_time": "11:00",
    }
    booked = client.post(_tool_url(client_id, "book"), json=payload,
                         headers={"X-Request-ID": request_id})
    assert booked.status_code == 200
    conflict = client.post(_tool_url(client_id, "book"), json=payload)
    assert conflict.status_code == 409

    logs = db.scalars(select(AuditLog).where(AuditLog.action == "sarvam_tool.book")).all()
    assert len(logs) == 2
    success = next(log for log in logs if log.details["success"])
    failure = next(log for log in logs if not log.details["success"])
    assert success.client_id == failure.client_id == client_id
    assert success.details["appointment_id"] == booked.json()["data"]["id"]
    assert success.details["request_id"] == request_id
    assert failure.details["error_code"] == "APPOINTMENT_CONFLICT"
    stored = str([(log.action, log.message, log.details) for log in logs])
    assert TOOL_TOKEN not in stored
    assert "+919833344444" not in stored


def test_invalid_tool_token_creates_no_audit_row(client, db, watch_tenants):
    response = client.post(
        _tool_url(watch_tenants["a"]["id"], "book", token="not-the-token"),
        json={"customer_phone": "invalid"},
    )
    assert response.status_code == 404
    assert db.scalar(select(AuditLog.id).where(AuditLog.action.like("sarvam_tool.%"))) is None


def test_valid_tool_failures_are_capped_without_changing_response(
    client, db, watch_tenants, monkeypatch,
):
    from app.services import tool_call_log_service

    monkeypatch.setattr(tool_call_log_service, "MAX_TOOL_LOGS_PER_MINUTE", 1)
    url = _tool_url(watch_tenants["a"]["id"], "book")
    payload = {
        "customer_phone": "invalid", "appointment_date": "2032-05-01",
        "appointment_time": "11:00",
    }
    first = client.post(url, json=payload)
    second = client.post(url, json=payload)
    assert first.status_code == second.status_code == 422
    assert first.json() == second.json()
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "sarvam_tool.book")).all()
    assert len(logs) == 1
    assert logs[0].client_id == watch_tenants["a"]["id"]
    assert logs[0].details["error_code"] == "INVALID_PHONE"


def test_valid_token_schema_validation_failure_is_audited(client, db, watch_tenants):
    response = client.post(
        _tool_url(watch_tenants["a"]["id"], "book"),
        json={"appointment_date": "2032-05-01", "appointment_time": "11:00"},
    )
    assert response.status_code == 422
    log = db.scalar(select(AuditLog).where(AuditLog.action == "sarvam_tool.book"))
    assert log is not None
    assert log.details["error_code"] == "VALIDATION_ERROR"
    assert log.details["request_id"]


def test_unknown_client_failure_uses_shared_null_tenant_log_bucket(
    client, db, watch_tenants,
):
    response = client.post(
        _tool_url(999999, "book"),
        json={
            "customer_phone": "+919877766655",
            "appointment_date": "2032-05-01", "appointment_time": "11:00",
        },
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"
    log = db.scalar(select(AuditLog).where(AuditLog.action == "sarvam_tool.book"))
    assert log is not None and log.client_id is None
    assert log.details["requested_client_id"] == 999999
    assert log.details["tenant_resolution"] == "unknown_client_id"


def test_unknown_client_tool_audits_share_the_cap(client, db, monkeypatch):
    from app.services import tool_call_log_service

    monkeypatch.setattr(tool_call_log_service, "MAX_TOOL_LOGS_PER_MINUTE", 1)
    payload = {
        "customer_phone": "+919877766655",
        "appointment_date": "2032-05-01", "appointment_time": "11:00",
    }
    first = client.post(_tool_url(999991, "book"), json=payload)
    second = client.post(_tool_url(999992, "book"), json=payload)
    assert first.status_code == second.status_code == 404
    assert first.json() == second.json()
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "sarvam_tool.book")).all()
    assert len(logs) == 1
    assert logs[0].client_id is None


def test_tool_logging_failure_does_not_change_tool_response(
    client, monkeypatch, watch_tenants,
):
    from app.api.routes import sarvam_webhooks

    def fail_logging(**_kwargs):
        raise RuntimeError("log backend unavailable")

    monkeypatch.setattr(sarvam_webhooks, "record_tool_call", fail_logging)
    response = client.post(
        _tool_url(watch_tenants["a"]["id"], "book"),
        json={
            "customer_phone": "+919844455555",
            "appointment_date": "2032-06-01", "appointment_time": "12:00",
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Appointment booked successfully"


def test_webhook_events_capture_processing_outcomes_and_request_ids(
    client, db, watch_tenants,
):
    from app.models.agent import Agent

    agent = Agent(client_id=watch_tenants["a"]["id"], name="Known",
                  provider="sarvam", provider_agent_id="known-watch-agent")
    db.add(agent)
    db.commit()
    processed_body = webhook_body(
        event_id="watch-processed", agent_id="known-watch-agent",
        call={"provider_call_id": "watch-call", "phone_number": "+919855566666"},
    )
    raw = json.dumps(processed_body).encode()
    signature = hmac.new(TOOL_TOKEN.encode(), raw, hashlib.sha256).hexdigest()
    processed = client.post(
        "/api/v1/webhooks/sarvam", content=raw,
        headers={
            "Content-Type": "application/json", "X-Sarvam-Signature": signature,
            "X-Request-ID": "webhook-request-1",
        },
    )
    assert processed.status_code == 200
    initial_event = db.scalar(select(WebhookEvent).where(
        WebhookEvent.event_id == "watch-processed"))
    assert initial_event.request_id == "webhook-request-1"

    failed_body = webhook_body(
        event_id="watch-failed", event_type="appointment_created",
        agent_id="known-watch-agent", appointment={"customer_phone": "bad"},
    )
    failed = send_webhook(client, failed_body)
    assert failed.status_code == 200 and failed.json()["data"]["status"] == "failed"

    unknown_body = webhook_body(
        event_id="watch-unknown", agent_id="unknown-watch-agent",
        call={"provider_call_id": "watch-unknown-call", "phone_number": "+919855566667"},
    )
    send_webhook(client, unknown_body)
    duplicate = send_webhook(client, processed_body)
    assert duplicate.json()["data"]["status"] == "duplicate"

    db.expire_all()
    events = {
        event.event_id: event
        for event in db.scalars(select(WebhookEvent).where(
            WebhookEvent.event_id.in_(
                ["watch-processed", "watch-failed", "watch-unknown"]
            )
        )).all()
    }
    assert events["watch-processed"].processed_at is not None
    assert events["watch-processed"].request_id is not None
    assert events["watch-failed"].processed_at is not None
    assert events["watch-failed"].client_id == watch_tenants["a"]["id"]
    assert events["watch-unknown"].processed_at is not None
    assert events["watch-unknown"].client_id is None
    assert events["watch-unknown"].error_message.startswith("Unknown agent")

    duplicate_event = db.scalar(select(WebhookEvent).where(
        WebhookEvent.event_id == "watch-processed"))
    assert duplicate_event.status == WebhookEventStatus.DUPLICATE
    assert duplicate_event.processed_at is not None


def test_tenant_appointment_desc_order_is_opt_in(client, watch_tenants):
    token = watch_tenants["a"]["token"]
    customer = make_customer(client, token, "Order Customer", "+919866677777")
    older = make_appointment(client, token, customer["id"], "2032-01-01", "09:00")
    newer = make_appointment(client, token, customer["id"], "2032-01-02", "09:00")
    default = client.get("/api/v1/appointments", headers=auth_headers(token)).json()["data"]
    descending = client.get(
        "/api/v1/appointments?order=desc", headers=auth_headers(token)
    ).json()["data"]
    assert [item["id"] for item in default[:2]] == [older["id"], newer["id"]]
    assert [item["id"] for item in descending[:2]] == [newer["id"], older["id"]]
