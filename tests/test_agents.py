from tests.helpers import (PASSWORD, auth_headers, create_admin_agent, create_agent,
                           create_staff, login_token, register_ok, super_admin_headers)


def _admin(client):
    return register_ok(client, "admin@a.com", "Tenant A")["tokens"]["access_token"]


def test_create_returns_defaults(client):
    token = _admin(client)
    agent = create_agent(client, token, "Zoya")
    assert agent["provider"] == "sarvam" and agent["status"] == "active"
    assert agent["configuration"] == {} and agent["provider_agent_id"] is None


def test_create_with_full_fields(client):
    token = _admin(client)
    agent = create_agent(client, token, "Zoya", description="Salon booking bot",
                         phone_number="+91 98765 43210", provider_agent_id="sarvam-xyz-1",
                         configuration={"voice": "female", "language": "en-IN"})
    assert agent["phone_number"] == "+919876543210"
    assert agent["configuration"] == {"voice": "female", "language": "en-IN"}
    assert agent["provider_agent_id"] == "sarvam-xyz-1"


def test_create_validation(client):
    token = _admin(client)
    h = auth_headers(token)
    assert client.post("/api/v1/agents", headers=h, json={"name": ""}).status_code == 422
    assert client.post("/api/v1/agents", headers=h, json={"name": "X", "phone_number": "abc"}).status_code == 422


def test_provider_agent_id_unique_platform_wide(client):
    a_token = _admin(client)
    b_token = register_ok(client, "admin@b.com", "Tenant B")["tokens"]["access_token"]
    create_agent(client, a_token, "A1", provider_agent_id="dup-ref")
    b_id = client.get("/api/v1/clients/me", headers=auth_headers(b_token)).json()["data"]["id"]
    resp = create_admin_agent(client, b_id, "B1", provider_agent_id="dup-ref")
    assert resp.status_code == 409 and resp.json()["error_code"] == "AGENT_ID_IN_USE"


def test_update_fields_and_config(client):
    token = _admin(client)
    agent = create_agent(client, token, configuration={"voice": "female"})
    resp = client.patch(f"/api/v1/admin/agents/{agent['id']}",
                        headers=super_admin_headers(client), json={
        "name": "Zoya updated", "provider_agent_id": "agent-updated",
        "status": "inactive"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Zoya updated"
    assert data["provider_agent_id"] == "agent-updated" and data["status"] == "inactive"
    assert data["configuration"] == {"voice": "female"}


def test_update_to_taken_provider_ref_conflicts(client):
    token = _admin(client)
    create_agent(client, token, "A1", provider_agent_id="ref-1")
    a2 = create_agent(client, token, "A2", provider_agent_id="ref-2")
    resp = client.patch(f"/api/v1/admin/agents/{a2['id']}",
                        headers=super_admin_headers(client),
                        json={"provider_agent_id": "ref-1"})
    assert resp.status_code == 409 and resp.json()["error_code"] == "AGENT_ID_IN_USE"


def test_admin_update_null_clears_optional_provider_id(client):
    token = _admin(client)
    agent = create_agent(client, token, provider_agent_id="ref-9")
    resp = client.patch(f"/api/v1/admin/agents/{agent['id']}",
                        headers=super_admin_headers(client), json={"provider_agent_id": None})
    data = resp.json()["data"]
    assert data["provider_agent_id"] is None
    assert data["name"] == agent["name"]


def test_list_filters_and_pagination(client):
    token = _admin(client)
    create_agent(client, token, "Active1")
    inactive = create_agent(client, token, "Inactive1")
    client.patch(f"/api/v1/agents/{inactive['id']}", headers=auth_headers(token), json={"status": "inactive"})
    h = auth_headers(token)
    assert len(client.get("/api/v1/agents?status=inactive", headers=h).json()["data"]) == 1
    assert client.get("/api/v1/agents", headers=h).json()["pagination"]["total"] == 2
    assert client.get("/api/v1/agents?provider=sarvam", headers=h).json()["pagination"]["total"] == 2


def test_delete_agent(client):
    token = _admin(client)
    agent = create_agent(client, token)
    resp = client.post(f"/api/v1/admin/agents/{agent['id']}/unlink",
                       headers=super_admin_headers(client))
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "inactive"
    assert client.get(f"/api/v1/agents/{agent['id']}",
                      headers=auth_headers(token)).status_code == 200


def test_staff_can_view_but_not_manage_agents(client):
    token = _admin(client)
    agent = create_agent(client, token)
    create_staff(client, token, "staff@a.com")
    staff = auth_headers(login_token(client, "staff@a.com"))
    assert client.get("/api/v1/agents", headers=staff).status_code == 200
    assert client.get(f"/api/v1/agents/{agent['id']}", headers=staff).status_code == 200
    assert client.post("/api/v1/agents", headers=staff, json={"name": "X"}).status_code == 403
    assert client.patch(f"/api/v1/agents/{agent['id']}", headers=staff, json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/v1/agents/{agent['id']}", headers=staff).status_code == 403


def test_unknown_agent_404_and_auth_required(client):
    token = _admin(client)
    resp = client.get("/api/v1/agents/99999", headers=auth_headers(token))
    assert resp.status_code == 404 and resp.json()["error_code"] == "AGENT_NOT_FOUND"
    assert client.get("/api/v1/agents").status_code == 401


def test_super_admin_lists_a_clients_agents(client, db):
    from app.models.enums import UserRole
    from tests.helpers import make_user

    a_token = _admin(client)
    agent = create_agent(client, a_token)
    b = register_ok(client, "admin@b.com", "Tenant B")
    a_client_id = client.get("/api/v1/clients/me", headers=auth_headers(a_token)).json()["data"]["id"]
    make_user(db, None, UserRole.SUPER_ADMIN, "root@platform.com")
    root = auth_headers(login_token(client, "root@platform.com"))

    resp = client.get(f"/api/v1/clients/{a_client_id}/agents", headers=root)
    assert resp.status_code == 200
    assert [a["id"] for a in resp.json()["data"]] == [agent["id"]]

    b_client_id = b["user"]["client_id"]
    empty = client.get(f"/api/v1/clients/{b_client_id}/agents", headers=root)
    assert empty.json()["data"] == []

    denied = client.get(f"/api/v1/clients/{a_client_id}/agents", headers=auth_headers(a_token))
    assert denied.status_code == 403


def test_update_phone_number_is_normalized(client):
    token = _admin(client)
    agent = create_agent(client, token, phone_number="+91 90000 00000")
    resp = client.patch(f"/api/v1/admin/agents/{agent['id']}",
                        headers=super_admin_headers(client),
                        json={"phone_number": "+91 90000 00001"})
    assert resp.json()["data"]["phone_number"] == "+919000000001"
