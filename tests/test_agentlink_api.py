import json

from sqlalchemy import select

from app.core.config import get_settings
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.client_tool_credential import ClientToolCredential
from app.models.enums import UserRole
from app.services.client_tool_credential_service import token_digest
from tests.helpers import (
    auth_headers,
    create_staff,
    elevated_headers,
    login_token,
    make_elevation_token,
    make_user,
    register_ok,
    super_admin_headers,
)


def _client(client, email: str, business: str):
    registration = register_ok(client, email, business)
    return {
        "id": registration["user"]["client_id"],
        "token": registration["tokens"]["access_token"],
    }


def _agent_body(**overrides):
    return {
        "name": "Aria",
        "provider": "sarvam",
        "provider_agent_id": "sarvam-agent-1",
        "phone_number": "+91 98765 43210",
        **overrides,
    }


def _create_agent(client, headers, client_id: int, **overrides):
    return client.post(
        f"/api/v1/admin/clients/{client_id}/agents",
        headers=headers,
        json=_agent_body(**overrides),
    )


def _new_tool_token(client, headers, client_id: int) -> str:
    response = client.post(
        f"/api/v1/admin/clients/{client_id}/tool-token", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def _tool_call(client, client_id: int, token: str, phone: str):
    return client.post(
        f"/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/book",
        json={
            "customer_phone": phone,
            "customer_name": "Caller",
            "appointment_date": "2032-05-01",
            "appointment_time": "10:00",
        },
    )


def test_admin_agent_and_integration_routes_require_super_admin(client, db):
    tenant = _client(client, "agentlink-admin@example.com", "AgentLink Client")
    staff = create_staff(client, tenant["token"], "agentlink-staff@example.com")
    staff_token = login_token(client, "agentlink-staff@example.com")
    agent_path = f"/api/v1/admin/clients/{tenant['id']}/agents"
    token_path = f"/api/v1/admin/clients/{tenant['id']}/tool-token"
    integration_path = f"/api/v1/admin/clients/{tenant['id']}/integration"
    update_path = "/api/v1/admin/agents/999999"
    unlink_path = "/api/v1/admin/agents/999999/unlink"
    agent_body = _agent_body()

    assert client.post(agent_path, json=agent_body).status_code == 401
    assert client.post(token_path).status_code == 401
    assert client.get(integration_path).status_code == 401
    assert client.patch(update_path, json={"name": "No"}).status_code == 401
    assert client.post(unlink_path).status_code == 401

    for token in (tenant["token"], staff_token):
        headers = auth_headers(token)
        assert client.post(agent_path, headers=headers, json=agent_body).status_code == 403
        assert client.post(token_path, headers=headers).status_code == 403
        assert client.get(integration_path, headers=headers).status_code == 403
        assert client.patch(update_path, headers=headers,
                            json={"name": "No"}).status_code == 403
        assert client.post(unlink_path, headers=headers).status_code == 403

    db.expire_all()
    root = make_user(db, None, UserRole.SUPER_ADMIN, "agentlink-root@example.com")
    root_headers = auth_headers(login_token(client, root.email))
    created = client.post(agent_path, headers=root_headers, json=agent_body)
    assert created.status_code == 201
    agent_id = created.json()["data"]["id"]
    assert created.json()["data"]["phone_number"] == "+919876543210"

    updated = client.patch(
        f"/api/v1/admin/agents/{agent_id}", headers=root_headers,
        json={"name": "Aria Updated"},
    )
    assert updated.status_code == 200
    unlinked = client.post(
        f"/api/v1/admin/agents/{agent_id}/unlink", headers=root_headers
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["data"]["status"] == "inactive"
    assert db.get(Agent, agent_id) is not None
    assert client.get(integration_path, headers=root_headers).status_code == 200
    assert client.post(token_path, headers=root_headers).status_code == 200

    audit_rows = db.scalars(
        select(AuditLog).where(
            AuditLog.user_id == root.id,
            AuditLog.action.like("admin.%"),
        )
    ).all()
    actions = {row.action for row in audit_rows}
    assert {"admin.agent.link", "admin.agent.update", "admin.agent.unlink",
            "admin.client_tool_token.create"} <= actions
    assert all(row.client_id == tenant["id"] for row in audit_rows)


def test_agent_phone_provider_uniqueness_and_validation(client):
    tenant_a = _client(client, "agentlink-a@example.com", "Client A")
    tenant_b = _client(client, "agentlink-b@example.com", "Client B")
    root = super_admin_headers(client)
    first = _create_agent(client, root, tenant_a["id"])
    assert first.status_code == 201, first.text
    first_id = first.json()["data"]["id"]

    duplicate_ref = _create_agent(
        client, root, tenant_b["id"], phone_number=None,
    )
    assert duplicate_ref.status_code == 409
    assert duplicate_ref.json()["error_code"] == "AGENT_ID_IN_USE"

    duplicate_phone = _create_agent(
        client, root, tenant_b["id"], provider_agent_id="different-ref",
    )
    assert duplicate_phone.status_code == 409
    assert duplicate_phone.json()["error_code"] == "PHONE_IN_USE"

    invalid_phone = _create_agent(
        client, root, tenant_b["id"],
        provider_agent_id="invalid-phone-ref", phone_number="9876543210",
    )
    assert invalid_phone.status_code == 422

    second = _create_agent(
        client, root, tenant_b["id"],
        provider_agent_id="different-ref", phone_number="+919876543211",
    )
    assert second.status_code == 201, second.text
    conflict = client.patch(
        f"/api/v1/admin/agents/{second.json()['data']['id']}",
        headers=root, json={"phone_number": "+91 98765 43210"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "PHONE_IN_USE"
    ref_conflict = client.patch(
        f"/api/v1/admin/agents/{second.json()['data']['id']}",
        headers=root, json={"provider_agent_id": "sarvam-agent-1"},
    )
    assert ref_conflict.status_code == 409
    assert ref_conflict.json()["error_code"] == "AGENT_ID_IN_USE"
    assert client.get(f"/api/v1/admin/agents", headers=root).status_code == 200
    assert first_id > 0


def test_clients_only_read_agent_links_and_can_keep_status_toggle(client):
    tenant_a = _client(client, "agentlink-read-a@example.com", "Client A")
    tenant_b = _client(client, "agentlink-read-b@example.com", "Client B")
    root = super_admin_headers(client)
    own = _create_agent(client, root, tenant_a["id"], phone_number="+919876543210")
    other = _create_agent(
        client, root, tenant_b["id"], provider_agent_id="client-b-ref",
        phone_number="+919876543211",
    )
    assert own.status_code == other.status_code == 201
    own_id = own.json()["data"]["id"]
    admin_headers = auth_headers(tenant_a["token"])

    assert client.post("/api/v1/agents", headers=admin_headers,
                       json={"name": "Forbidden"}).status_code == 403
    for body in (
        {"provider": "other_provider"},
        {"provider_agent_id": "changed-ref"},
        {"phone_number": "+919876543299"},
        {"name": "Changed"},
    ):
        response = client.patch(
            f"/api/v1/agents/{own_id}", headers=admin_headers, json=body
        )
        assert response.status_code == 403

    staff_data = create_staff(client, tenant_a["token"], "agentlink-read-staff@example.com")
    staff_token = login_token(client, "agentlink-read-staff@example.com")
    staff_headers = auth_headers(staff_token)
    assert client.post("/api/v1/agents", headers=staff_headers,
                       json={"name": "Forbidden"}).status_code == 403
    assert client.patch(f"/api/v1/agents/{own_id}", headers=staff_headers,
                        json={"phone_number": "+919876543298"}).status_code == 403
    elevated_staff_headers = elevated_headers(
        staff_token, make_elevation_token(staff_data["id"], tenant_a["id"])
    )
    assert client.patch(
        f"/api/v1/agents/{own_id}", headers=elevated_staff_headers,
        json={"provider_agent_id": "staff-cannot-link"},
    ).status_code == 403

    power = client.patch(
        f"/api/v1/agents/{own_id}", headers=admin_headers,
        json={"status": "inactive"},
    )
    assert power.status_code == 200
    assert power.json()["data"]["status"] == "inactive"
    staff_power = client.patch(
        f"/api/v1/agents/{own_id}", headers=elevated_staff_headers,
        json={"status": "active"},
    )
    assert staff_power.status_code == 200
    assert staff_power.json()["data"]["status"] == "active"

    listing = client.get("/api/v1/agents", headers=admin_headers).json()["data"]
    assert [agent["id"] for agent in listing] == [own_id]
    assert listing[0]["phone_number"] == "+919876543210"
    assert all(agent["id"] != other.json()["data"]["id"] for agent in listing)
    assert staff_data["id"] > 0


def test_client_tool_tokens_are_scoped_rotated_and_never_logged(client, db, caplog):
    tenant_a = _client(client, "agentlink-token-a@example.com", "Client A")
    tenant_b = _client(client, "agentlink-token-b@example.com", "Client B")
    root = super_admin_headers(client)
    caplog.set_level("WARNING")

    before_invalid = db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()))
    invalid = _tool_call(client, tenant_a["id"], "invalid-random-token", "+919876543201")
    assert invalid.status_code == 404
    assert db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc())) == before_invalid

    token_a = _new_tool_token(client, root, tenant_a["id"])
    assert len(token_a) >= 40
    use_a = _tool_call(client, tenant_a["id"], token_a, "+919876543202")
    assert use_a.status_code == 200, use_a.text
    assert token_a not in use_a.text
    cross_tenant = _tool_call(client, tenant_b["id"], token_a, "+919876543203")
    assert cross_tenant.status_code == 404
    assert token_a not in cross_tenant.text

    integration = client.get(
        f"/api/v1/admin/clients/{tenant_a['id']}/integration", headers=root
    )
    integration_text = integration.text
    assert integration.status_code == 200
    assert token_a not in integration_text
    assert "{TOKEN}" in integration_text

    rotated = _new_tool_token(client, root, tenant_a["id"])
    assert rotated != token_a
    assert token_a not in rotated
    assert _tool_call(client, tenant_a["id"], token_a, "+919876543204").status_code == 404
    assert _tool_call(client, tenant_a["id"], rotated, "+919876543205").status_code == 200

    integration_after_use = client.get(
        f"/api/v1/admin/clients/{tenant_a['id']}/integration", headers=root
    ).json()["data"]
    assert integration_after_use["credential_exists"] is True
    assert integration_after_use["credential_last_used_at"] is not None
    assert integration_after_use["tool_url_patterns"]["book"].endswith(
        f"/{tenant_a['id']}/appointments/book"
    )

    rows = db.scalars(select(AuditLog)).all()
    serialized_rows = json.dumps([
        {"action": row.action, "message": row.message, "details": row.details}
        for row in rows
    ])
    assert token_a not in serialized_rows and rotated not in serialized_rows
    assert token_a not in caplog.text and rotated not in caplog.text
    credentials = db.scalars(
        select(ClientToolCredential).where(
            ClientToolCredential.client_id == tenant_a["id"]
        )
    ).all()
    assert all(credential.token_hash not in (token_a, rotated) for credential in credentials)
    assert any(credential.token_hash == token_digest(token_a) for credential in credentials)
    assert any(credential.revoked_at is not None for credential in credentials)


def test_legacy_shared_token_flag_logs_without_token_and_can_be_disabled(
    client, db, caplog, monkeypatch,
):
    tenant = _client(client, "agentlink-legacy@example.com", "Legacy Client")
    token = get_settings().sarvam_webhook_secret
    assert token
    caplog.set_level("WARNING")
    before = db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()))

    accepted = _tool_call(client, tenant["id"], token, "+919876543206")
    assert accepted.status_code == 200
    assert "Legacy shared Sarvam tool token used" in caplog.text
    assert token not in caplog.text
    legacy_row = db.scalar(
        select(AuditLog).where(
            AuditLog.client_id == tenant["id"],
            AuditLog.action == "sarvam_tool.book",
        )
    )
    assert legacy_row is not None
    assert legacy_row.message == "Legacy shared token used"
    assert legacy_row.details["legacy_shared_token_used"] is True
    assert legacy_row.id > (before or 0)

    monkeypatch.setattr(get_settings(), "sarvam_legacy_shared_token_enabled", False)
    rejected = _tool_call(client, tenant["id"], token, "+919876543207")
    assert rejected.status_code == 404
    assert token not in caplog.text
