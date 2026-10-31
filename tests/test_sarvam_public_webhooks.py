from sqlalchemy import select

from app.models.call_attempt import CallAttempt
from app.models.enums import AppointmentStatus
from tests.helpers import make_appointment, make_customer, register_ok


SECRET = "test-sarvam-webhook-secret"


def _tenant(client, email="admin@example.com"):
    data = register_ok(client, email)
    return data["tokens"]["access_token"], data["user"]["client_id"]


def _url(client_id, action, token=SECRET):
    return f"/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/{action}"


def test_public_sarvam_routes_reject_wrong_token(client):
    response = client.post("/api/v1/webhooks/sarvam/wrong/outbound",
                           json={"attempt_id": "attempt-1", "status": "connected"})
    assert response.status_code == 404


def test_outbound_connected_is_idempotent(client, db):
    _, client_id = _tenant(client, "admin@sarvam-example.com")
    body = {
        "attempt_id": "attempt-1",
        "status": "connected",
        "duration": 12,
        "interaction_id": "interaction-1",
        "final_agent_variables": {"booked": True},
        "interaction_transcript": [{"role": "agent", "en_text": "Hello"}],
        "webhook_config": {"metadata": {"client_id": client_id}},
    }
    first = client.post(f"/api/v1/webhooks/sarvam/{SECRET}/outbound", json=body)
    second = client.post(f"/api/v1/webhooks/sarvam/{SECRET}/outbound", json=body)
    assert first.json() == {"ok": True}
    assert second.json() == {"ok": True}
    attempts = db.scalars(select(CallAttempt).where(CallAttempt.attempt_id == "attempt-1")).all()
    assert len(attempts) == 1
    assert attempts[0].client_id == client_id


def test_public_sarvam_appointment_operations_are_tenant_scoped(client):
    token_a, client_a = _tenant(client, "a@sarvam-example.com")
    token_b, client_b = _tenant(client, "b@sarvam-example.com")
    customer_a = make_customer(client, token_a, "A", "+919876543201")
    customer_b = make_customer(client, token_b, "B", "+919876543202")
    appointment_b = make_appointment(client, token_b, customer_b["id"])

    body = {
        "customer_phone": customer_a["phone"],
        "appointment_date": "2030-01-15",
        "appointment_time": "10:00",
    }
    check = client.post(_url(client_a, "check-slot"), json=body)
    assert check.status_code == 200 and check.json()["data"]["available"] is True

    booked = client.post(_url(client_a, "book"), json=body)
    assert booked.status_code == 200
    appointment_a = booked.json()["data"]

    foreign_cancel = client.post(_url(client_a, "cancel"), json={
        "customer_phone": customer_a["phone"], "appointment_id": appointment_b["id"],
        "reason": "not mine"})
    assert foreign_cancel.status_code == 404

    rescheduled = client.post(_url(client_a, "reschedule"), json={
        "customer_phone": customer_a["phone"], "appointment_id": appointment_a["id"],
        "new_date": "2030-01-16", "new_time": "11:00"})
    assert rescheduled.status_code == 200
    cancelled = client.post(_url(client_a, "cancel"), json={
        "customer_phone": customer_a["phone"], "appointment_id": appointment_a["id"]})
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == AppointmentStatus.CANCELLED.value
