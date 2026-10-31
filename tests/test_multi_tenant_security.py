"""Tenant isolation: Client A must never see or change Client B's data.

Stage 4 covers users and clients. Later stages add customers, appointments,
calls and agents to this same file (see the TODO markers at the bottom).
"""
from datetime import date, time

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.database import Base, engine
from app.core.dependencies import get_current_user
from app.main import create_app
from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus, UserRole
from app.models.user import User
from tests.helpers import (PASSWORD, auth_headers, create_agent, create_staff, login_token,
                           make_agent, make_appointment, make_call, make_customer, make_user,
                           register_ok, send_webhook, webhook_body)


@pytest.fixture
def tenants(client):
    """Two independent clients, each with an admin and a staff member."""
    a = register_ok(client, "admin@a.com", "Tenant A")
    b = register_ok(client, "admin@b.com", "Tenant B")
    a_tok, b_tok = a["tokens"]["access_token"], b["tokens"]["access_token"]
    return {
        "a": {"client_id": a["user"]["client_id"], "admin_id": a["user"]["id"], "token": a_tok,
              "staff": create_staff(client, a_tok, "staff@a.com")},
        "b": {"client_id": b["user"]["client_id"], "admin_id": b["user"]["id"], "token": b_tok,
              "staff": create_staff(client, b_tok, "staff@b.com")},
    }


# ---------------- users ----------------
def test_user_list_only_contains_own_tenant(client, tenants):
    resp = client.get("/api/v1/users", headers=auth_headers(tenants["a"]["token"]))
    emails = {u["email"] for u in resp.json()["data"]}
    assert emails == {"admin@a.com", "staff@a.com"}
    assert resp.json()["pagination"]["total"] == 2


def test_client_id_query_param_cannot_override_tenant(client, tenants):
    b_id = tenants["b"]["client_id"]
    resp = client.get(f"/api/v1/users?client_id={b_id}", headers=auth_headers(tenants["a"]["token"]))
    assert {u["email"] for u in resp.json()["data"]} == {"admin@a.com", "staff@a.com"}


def test_cannot_read_other_tenants_user(client, tenants):
    b_staff = tenants["b"]["staff"]["id"]
    resp = client.get(f"/api/v1/users/{b_staff}", headers=auth_headers(tenants["a"]["token"]))
    assert resp.status_code == 404 and resp.json()["error_code"] == "USER_NOT_FOUND"


def test_cannot_modify_other_tenants_user(client, db, tenants):
    b_staff = tenants["b"]["staff"]["id"]
    resp = client.patch(f"/api/v1/users/{b_staff}", headers=auth_headers(tenants["a"]["token"]),
                        json={"is_active": False, "name": "hacked", "role": "client_admin"})
    assert resp.status_code == 404
    victim = db.get(User, b_staff)
    assert victim.is_active and victim.name == "Staff" and victim.role == UserRole.CLIENT_STAFF


def test_other_tenant_user_is_indistinguishable_from_nonexistent(client, tenants):
    headers = auth_headers(tenants["a"]["token"])
    real_but_foreign = client.get(f"/api/v1/users/{tenants['b']['staff']['id']}", headers=headers)
    missing = client.get("/api/v1/users/999999", headers=headers)
    assert real_but_foreign.status_code == missing.status_code == 404
    assert real_but_foreign.json() == missing.json()


def test_body_client_id_is_ignored_when_creating_user(client, db, tenants):
    resp = client.post("/api/v1/users", headers=auth_headers(tenants["a"]["token"]), json={
        "name": "New", "email": "new@a.com", "password": PASSWORD,
        "client_id": tenants["b"]["client_id"]})
    assert resp.status_code == 201
    assert resp.json()["data"]["client_id"] == tenants["a"]["client_id"]
    assert db.scalar(select(User).where(User.email == "new@a.com")).client_id == tenants["a"]["client_id"]


def test_enumerating_ids_never_reveals_other_tenant(client, tenants):
    headers = auth_headers(tenants["a"]["token"])
    own = {tenants["a"]["admin_id"], tenants["a"]["staff"]["id"]}
    for user_id in range(1, 30):
        status = client.get(f"/api/v1/users/{user_id}", headers=headers).status_code
        assert status == (200 if user_id in own else 404)


# ---------------- privilege boundaries ----------------
def test_staff_cannot_manage_users(client, tenants):
    staff_tok = login_token(client, "staff@a.com")
    assert client.get("/api/v1/users", headers=auth_headers(staff_tok)).status_code == 403
    resp = client.post("/api/v1/users", headers=auth_headers(staff_tok), json={
        "name": "X", "email": "x@a.com", "password": PASSWORD})
    assert resp.status_code == 403


def test_client_admin_cannot_create_super_admin(client, tenants):
    resp = client.post("/api/v1/users", headers=auth_headers(tenants["a"]["token"]), json={
        "name": "X", "email": "root@a.com", "password": PASSWORD, "role": "super_admin"})
    assert resp.status_code == 422


def test_admin_cannot_change_own_role_or_deactivate_self(client, tenants):
    me = tenants["a"]["admin_id"]
    for body in ({"role": "client_staff"}, {"is_active": False}):
        resp = client.patch(f"/api/v1/users/{me}", headers=auth_headers(tenants["a"]["token"]),
                            json=body)
        assert resp.status_code == 403 and resp.json()["error_code"] == "CANNOT_MODIFY_SELF"


def test_deactivated_staff_loses_access(client, tenants):
    staff_tok = login_token(client, "staff@a.com")
    staff_id = tenants["a"]["staff"]["id"]
    resp = client.patch(f"/api/v1/users/{staff_id}", headers=auth_headers(tenants["a"]["token"]),
                        json={"is_active": False})
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth_headers(staff_tok)).status_code == 403


def test_duplicate_user_email_across_tenants_conflicts(client, tenants):
    resp = client.post("/api/v1/users", headers=auth_headers(tenants["a"]["token"]), json={
        "name": "Dup", "email": "staff@b.com", "password": PASSWORD})
    assert resp.status_code == 409


# ---------------- clients ----------------
def test_client_admin_cannot_use_platform_client_endpoints(client, tenants):
    headers = auth_headers(tenants["a"]["token"])
    b_id = tenants["b"]["client_id"]
    assert client.get("/api/v1/clients", headers=headers).status_code == 403
    assert client.get(f"/api/v1/clients/{b_id}", headers=headers).status_code == 403
    assert client.patch(f"/api/v1/clients/{b_id}", headers=headers, json={"business_name": "X"}).status_code == 403
    assert client.post(f"/api/v1/clients/{b_id}/disable", headers=headers).status_code == 403
    assert client.get(f"/api/v1/clients/{b_id}/users", headers=headers).status_code == 403


def test_my_client_returns_only_own_profile(client, tenants):
    resp = client.get("/api/v1/clients/me", headers=auth_headers(tenants["a"]["token"]))
    assert resp.json()["data"]["id"] == tenants["a"]["client_id"]
    assert resp.json()["data"]["business_name"] == "Tenant A"


def test_profile_update_touches_only_own_client_and_safe_fields(client, tenants):
    a_headers, b_headers = auth_headers(tenants["a"]["token"]), auth_headers(tenants["b"]["token"])
    resp = client.patch("/api/v1/clients/me", headers=a_headers, json={
        "business_name": "A Renamed", "status": "disabled", "email": "evil@a.com", "id": 99})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["business_name"] == "A Renamed"
    assert data["status"] == "active" and data["email"] == "admin@a.com"
    assert data["id"] == tenants["a"]["client_id"]
    assert client.get("/api/v1/clients/me", headers=b_headers).json()["data"]["business_name"] == "Tenant B"


def test_staff_can_view_but_not_edit_business_profile(client, tenants):
    staff_headers = auth_headers(login_token(client, "staff@a.com"))
    assert client.get("/api/v1/clients/me", headers=staff_headers).status_code == 200
    assert client.patch("/api/v1/clients/me", headers=staff_headers,
                        json={"business_name": "Nope"}).status_code == 403


# ---------------- super admin ----------------
@pytest.fixture
def super_headers(client, db):
    make_user(db, None, UserRole.SUPER_ADMIN, "root@platform.com")
    return auth_headers(login_token(client, "root@platform.com"))


def test_super_admin_lists_and_reads_all_clients(client, tenants, super_headers):
    resp = client.get("/api/v1/clients", headers=super_headers)
    assert resp.json()["pagination"]["total"] == 2
    b_id = tenants["b"]["client_id"]
    assert client.get(f"/api/v1/clients/{b_id}", headers=super_headers).status_code == 200
    users = client.get(f"/api/v1/clients/{b_id}/users", headers=super_headers).json()["data"]
    assert {u["email"] for u in users} == {"admin@b.com", "staff@b.com"}


def test_super_admin_creates_client_with_admin(client, super_headers):
    resp = client.post("/api/v1/clients", headers=super_headers, json={
        "business_name": "Created Co", "email": "hello@created.com",
        "admin": {"name": "Boss", "email": "boss@created.com", "password": PASSWORD}})
    assert resp.status_code == 201
    token = login_token(client, "boss@created.com")
    me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()["data"]
    assert me["role"] == "client_admin" and me["client_id"] == resp.json()["data"]["id"]


def test_disabling_client_blocks_only_that_client(client, tenants, super_headers):
    b_id = tenants["b"]["client_id"]
    resp = client.post(f"/api/v1/clients/{b_id}/disable", headers=super_headers)
    assert resp.json()["data"]["status"] == "disabled"
    # B's existing token stops working immediately, and B cannot log in again.
    b_me = client.get("/api/v1/auth/me", headers=auth_headers(tenants["b"]["token"]))
    assert b_me.status_code == 403 and b_me.json()["error_code"] == "CLIENT_DISABLED"
    relogin = client.post("/api/v1/auth/login", json={"email": "admin@b.com", "password": PASSWORD})
    assert relogin.status_code == 403
    # A is unaffected.
    assert client.get("/api/v1/auth/me", headers=auth_headers(tenants["a"]["token"])).status_code == 200
    # Re-enable restores access.
    client.post(f"/api/v1/clients/{b_id}/enable", headers=super_headers)
    assert client.get("/api/v1/auth/me", headers=auth_headers(tenants["b"]["token"])).status_code == 200


def test_super_admin_cannot_use_tenant_user_endpoints(client, super_headers):
    """SUPER_ADMIN has no tenant, so it is not silently handed one."""
    assert client.get("/api/v1/users", headers=super_headers).status_code == 403


def test_super_admin_actions_are_audited(client, db, tenants, super_headers):
    from app.models.audit_log import AuditLog
    client.post(f"/api/v1/clients/{tenants['b']['client_id']}/disable", headers=super_headers)
    log = db.scalar(select(AuditLog).where(AuditLog.action == "client.disable"))
    assert log is not None and log.client_id == tenants["b"]["client_id"] and log.user_id


# ---------------- customers & appointments ----------------
@pytest.fixture
def records(client, tenants):
    """One customer and one appointment for each tenant."""
    out = {}
    for key in ("a", "b"):
        tok = tenants[key]["token"]
        cust = make_customer(client, tok, f"Customer {key.upper()}", "+91900000000" + ("1" if key == "a" else "2"))
        out[key] = {"customer": cust, "appointment": make_appointment(client, tok, cust["id"])}
    return out


def test_customer_list_only_contains_own_tenant(client, tenants, records):
    body = client.get("/api/v1/customers", headers=auth_headers(tenants["a"]["token"])).json()
    assert [c["id"] for c in body["data"]] == [records["a"]["customer"]["id"]]
    b_id = tenants["b"]["client_id"]
    leak = client.get(f"/api/v1/customers?client_id={b_id}", headers=auth_headers(tenants["a"]["token"])).json()
    assert [c["id"] for c in leak["data"]] == [records["a"]["customer"]["id"]]


def test_cannot_read_modify_or_delete_other_tenants_customer(client, db, tenants, records):
    from app.models.customer import Customer
    h = auth_headers(tenants["a"]["token"])
    b_cust = records["b"]["customer"]["id"]
    assert client.get(f"/api/v1/customers/{b_cust}", headers=h).status_code == 404
    assert client.patch(f"/api/v1/customers/{b_cust}", headers=h, json={"name": "hacked"}).status_code == 404
    assert client.delete(f"/api/v1/customers/{b_cust}", headers=h).status_code == 404
    victim = db.get(Customer, b_cust)
    assert victim is not None and victim.name == "Customer B"


def test_appointment_list_only_contains_own_tenant(client, tenants, records):
    h = auth_headers(tenants["a"]["token"])
    body = client.get("/api/v1/appointments", headers=h).json()
    assert [a["id"] for a in body["data"]] == [records["a"]["appointment"]["id"]]
    # Filtering by the other tenant's customer or client id must reveal nothing.
    b_cust = records["b"]["customer"]["id"]
    assert client.get(f"/api/v1/appointments?customer={b_cust}", headers=h).json()["data"] == []
    b_id = tenants["b"]["client_id"]
    leak = client.get(f"/api/v1/appointments?client_id={b_id}", headers=h).json()
    assert [a["id"] for a in leak["data"]] == [records["a"]["appointment"]["id"]]


def test_cannot_read_modify_or_delete_other_tenants_appointment(client, db, tenants, records):
    h = auth_headers(tenants["a"]["token"])
    b_appt = records["b"]["appointment"]["id"]
    assert client.get(f"/api/v1/appointments/{b_appt}", headers=h).status_code == 404
    assert client.get(f"/api/v1/appointments/{b_appt}/history", headers=h).status_code == 404
    assert client.patch(f"/api/v1/appointments/{b_appt}", headers=h,
                        json={"status": "completed", "notes": "hacked"}).status_code == 404
    assert client.delete(f"/api/v1/appointments/{b_appt}", headers=h).status_code == 404
    victim = db.get(Appointment, b_appt)
    assert victim.status == AppointmentStatus.SCHEDULED and victim.notes is None


def test_cannot_book_appointment_for_other_tenants_customer(client, db, tenants, records):
    resp = client.post("/api/v1/appointments", headers=auth_headers(tenants["a"]["token"]), json={
        "customer_id": records["b"]["customer"]["id"],
        "appointment_date": "2030-05-05", "appointment_time": "10:00"})
    assert resp.status_code == 404 and resp.json()["error_code"] == "CUSTOMER_NOT_FOUND"
    assert db.scalar(select(Appointment).where(Appointment.appointment_date == date(2030, 5, 5))) is None


def test_cannot_move_appointment_to_other_tenants_customer(client, db, tenants, records):
    a_appt = records["a"]["appointment"]["id"]
    resp = client.patch(f"/api/v1/appointments/{a_appt}", headers=auth_headers(tenants["a"]["token"]),
                        json={"customer_id": records["b"]["customer"]["id"]})
    assert resp.status_code == 404
    assert db.get(Appointment, a_appt).customer_id == records["a"]["customer"]["id"]


def test_body_client_id_is_ignored_for_customers_and_appointments(client, tenants, records):
    h = auth_headers(tenants["a"]["token"])
    b_id = tenants["b"]["client_id"]
    cust = client.post("/api/v1/customers", headers=h, json={
        "name": "New", "phone": "+919111111111", "client_id": b_id}).json()["data"]
    assert cust["client_id"] == tenants["a"]["client_id"]
    appt = client.post("/api/v1/appointments", headers=h, json={
        "customer_id": cust["id"], "appointment_date": "2030-06-06",
        "appointment_time": "10:00", "client_id": b_id}).json()["data"]
    assert appt["client_id"] == tenants["a"]["client_id"]


def test_same_phone_and_slot_can_exist_in_two_tenants(client, tenants):
    """Uniqueness is per tenant, so one tenant can't probe another's customers via conflicts."""
    a = make_customer(client, tenants["a"]["token"], "Same", "+919222222222")
    b = make_customer(client, tenants["b"]["token"], "Same", "+919222222222")
    assert a["id"] != b["id"]
    make_appointment(client, tenants["a"]["token"], a["id"], "2030-07-07", "10:00")
    make_appointment(client, tenants["b"]["token"], b["id"], "2030-07-07", "10:00")


def test_database_rejects_cross_tenant_appointment_even_without_the_api(db, tenants, records):
    """Composite FK is the last line of defence if application code ever has a bug."""
    db.add(Appointment(client_id=tenants["a"]["client_id"],
                       customer_id=records["b"]["customer"]["id"],
                       appointment_date=date(2030, 8, 8), appointment_time=time(9, 0)))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("me,other", [("a", "b"), ("b", "a")])
def test_acceptance_scenario_both_directions(client, tenants, records, me, other):
    """Mandatory scenario: a user sees/modifies only their own appointment, from either side.

    Cancel and the calls/agents checks are added in stages 6-8.
    """
    h = auth_headers(tenants[me]["token"])
    mine, theirs = records[me]["appointment"]["id"], records[other]["appointment"]["id"]
    assert client.get(f"/api/v1/appointments/{mine}", headers=h).status_code == 200
    assert client.patch(f"/api/v1/appointments/{mine}", headers=h, json={"notes": "ok"}).status_code == 200
    assert client.get(f"/api/v1/appointments/{theirs}", headers=h).status_code == 404
    assert client.patch(f"/api/v1/appointments/{theirs}", headers=h, json={"notes": "x"}).status_code == 404
    their_cust = records[other]["customer"]["id"]
    assert client.get(f"/api/v1/customers/{their_cust}", headers=h).status_code == 404


def test_staff_of_one_tenant_is_also_isolated(client, tenants, records):
    staff = auth_headers(login_token(client, "staff@a.com"))
    assert client.get(f"/api/v1/appointments/{records['b']['appointment']['id']}", headers=staff).status_code == 404
    assert client.get(f"/api/v1/customers/{records['b']['customer']['id']}", headers=staff).status_code == 404
    listed = client.get("/api/v1/appointments", headers=staff).json()["data"]
    assert [a["id"] for a in listed] == [records["a"]["appointment"]["id"]]


# ---------------- cancellation, rescheduling, agent requests ----------------
def test_cannot_cancel_or_reschedule_other_tenants_appointment(client, db, tenants, records):
    h = auth_headers(tenants["a"]["token"])
    b_appt = records["b"]["appointment"]["id"]
    assert client.post(f"/api/v1/appointments/{b_appt}/cancel", headers=h).status_code == 404
    resched = client.post(f"/api/v1/appointments/{b_appt}/reschedule", headers=h,
                          json={"new_date": "2030-09-09", "new_time": "10:00"})
    assert resched.status_code == 404
    victim = db.get(Appointment, b_appt)
    assert victim.status == AppointmentStatus.SCHEDULED and victim.appointment_date == date(2030, 1, 15)


def test_cancellations_list_is_tenant_scoped(client, tenants, records):
    for key in ("a", "b"):
        client.post(f"/api/v1/appointments/{records[key]['appointment']['id']}/cancel",
                    headers=auth_headers(tenants[key]["token"]))
    a = client.get("/api/v1/cancellations", headers=auth_headers(tenants["a"]["token"])).json()
    assert [c["appointment_id"] for c in a["data"]] == [records["a"]["appointment"]["id"]]
    b_cancel_id = client.get("/api/v1/cancellations", headers=auth_headers(tenants["b"]["token"])).json()["data"][0]["id"]
    assert client.get(f"/api/v1/cancellations/{b_cancel_id}", headers=auth_headers(tenants["a"]["token"])).status_code == 404
    leak = client.get(f"/api/v1/cancellations?client_id={tenants['b']['client_id']}", headers=auth_headers(tenants["a"]["token"])).json()
    assert len(leak["data"]) == 1


def test_appointment_history_only_shows_own_tenant(client, tenants, records):
    h = auth_headers(tenants["a"]["token"])
    mine = client.get(f"/api/v1/appointments/{records['a']['appointment']['id']}/history", headers=h)
    assert mine.status_code == 200
    theirs = client.get(f"/api/v1/appointments/{records['b']['appointment']['id']}/history", headers=h)
    assert theirs.status_code == 404


def test_ai_agent_of_one_tenant_cannot_cancel_other_tenants_appointment(db, tenants, records):
    """Even with the right phone number AND appointment id of tenant B, tenant A's agent gets nothing."""
    from app.core.exceptions import AppError
    from app.services.agent_request_service import AgentRequestService
    agent_a = AgentRequestService(db, tenants["a"]["client_id"])
    with pytest.raises(AppError) as err:
        agent_a.cancel(customer_phone=records["b"]["customer"]["phone"],
                       appointment_id=records["b"]["appointment"]["id"])
    assert err.value.status_code == 404
    assert db.get(Appointment, records["b"]["appointment"]["id"]).status == AppointmentStatus.SCHEDULED


def test_database_rejects_cross_tenant_cancellation_row(db, tenants, records):
    from app.models.cancellation import Cancellation
    db.add(Cancellation(client_id=tenants["a"]["client_id"],
                        appointment_id=records["b"]["appointment"]["id"],
                        customer_id=records["a"]["customer"]["id"],
                        appointment_date=date(2030, 1, 15), appointment_time=time(10, 0)))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_acceptance_scenario_cancel_from_both_sides(client, tenants, records):
    """Mandatory scenario, cancel step: each user cancels only their own appointment."""
    for me, other in (("a", "b"), ("b", "a")):
        h = auth_headers(tenants[me]["token"])
        theirs = records[other]["appointment"]["id"]
        assert client.post(f"/api/v1/appointments/{theirs}/cancel", headers=h).status_code == 404
        mine = records[me]["appointment"]["id"]
        assert client.post(f"/api/v1/appointments/{mine}/cancel", headers=h).status_code == 200
    for key in ("a", "b"):  # and neither was affected by the other side's attempts
        appt = client.get(f"/api/v1/appointments/{records[key]['appointment']['id']}",
                          headers=auth_headers(tenants[key]["token"])).json()["data"]
        assert appt["status"] == "cancelled"


# ---------------- calls ----------------
@pytest.fixture
def calls(db, tenants, records):
    """One agent and one call (with transcript) for each tenant."""
    out = {}
    for key in ("a", "b"):
        cid = tenants[key]["client_id"]
        agent = make_agent(db, cid, f"Agent {key.upper()}")
        call = make_call(db, cid, agent_id=agent.id, customer_id=records[key]["customer"]["id"],
                         transcript=f"secret transcript of {key}", recording_url=f"https://rec/{key}")
        out[key] = {"agent": agent.id, "call": call.id}
    return out


def test_call_list_only_contains_own_tenant(client, tenants, calls):
    h = auth_headers(tenants["a"]["token"])
    body = client.get("/api/v1/calls", headers=h).json()
    assert [c["id"] for c in body["data"]] == [calls["a"]["call"]]
    assert "secret transcript of b" not in client.get("/api/v1/calls", headers=h).text


def test_cannot_read_other_tenants_call(client, tenants, calls):
    resp = client.get(f"/api/v1/calls/{calls['b']['call']}", headers=auth_headers(tenants["a"]["token"]))
    assert resp.status_code == 404 and "secret" not in resp.text
    missing = client.get("/api/v1/calls/999999", headers=auth_headers(tenants["a"]["token"]))
    assert resp.json() == missing.json()


def test_call_filters_cannot_reach_other_tenants_records(client, tenants, records, calls):
    h = auth_headers(tenants["a"]["token"])
    assert client.get(f"/api/v1/calls?agent={calls['b']['agent']}", headers=h).json()["data"] == []
    assert client.get(f"/api/v1/calls?customer={records['b']['customer']['id']}", headers=h).json()["data"] == []


def test_client_user_cannot_use_client_id_param_to_read_other_tenant_calls(client, tenants, calls):
    b_id = tenants["b"]["client_id"]
    for who in ("a", "staff"):
        token = tenants["a"]["token"] if who == "a" else login_token(client, "staff@a.com")
        body = client.get(f"/api/v1/calls?client_id={b_id}", headers=auth_headers(token)).json()
        assert [c["id"] for c in body["data"]] == [calls["a"]["call"]]


def test_staff_cannot_read_other_tenants_call(client, calls):
    staff = auth_headers(login_token(client, "staff@a.com"))
    assert client.get(f"/api/v1/calls/{calls['b']['call']}", headers=staff).status_code == 404


def test_database_rejects_call_linking_other_tenants_agent_or_customer(db, tenants, records, calls):
    from app.models.call import Call
    from app.models.enums import CallDirection, CallStatus
    for extra in ({"agent_id": calls["b"]["agent"]}, {"customer_id": records["b"]["customer"]["id"]}):
        db.add(Call(client_id=tenants["a"]["client_id"], phone_number="+919999999999",
                    direction=CallDirection.INBOUND, status=CallStatus.COMPLETED, **extra))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


@pytest.mark.parametrize("me,other", [("a", "b"), ("b", "a")])
def test_acceptance_scenario_calls_both_directions(client, tenants, calls, me, other):
    """Mandatory scenario: 'User must NOT access the other client's calls'."""
    h = auth_headers(tenants[me]["token"])
    assert client.get(f"/api/v1/calls/{calls[me]['call']}", headers=h).status_code == 200
    assert client.get(f"/api/v1/calls/{calls[other]['call']}", headers=h).status_code == 404


# ---------------- agents ----------------
def test_agent_list_only_contains_own_tenant(client, tenants):
    a_agent = create_agent(client, tenants["a"]["token"], "Agent A")
    create_agent(client, tenants["b"]["token"], "Agent B")
    body = client.get("/api/v1/agents", headers=auth_headers(tenants["a"]["token"])).json()
    assert [a["id"] for a in body["data"]] == [a_agent["id"]]


def test_cannot_read_modify_or_delete_other_tenants_agent(client, db, tenants):
    from app.models.agent import Agent

    b_agent = create_agent(client, tenants["b"]["token"], "Agent B")
    h = auth_headers(tenants["a"]["token"])
    assert client.get(f"/api/v1/agents/{b_agent['id']}", headers=h).status_code == 404
    patched = client.patch(f"/api/v1/agents/{b_agent['id']}", headers=h,
                           json={"name": "hacked"})
    assert patched.status_code == 403
    db.expire_all()
    assert db.get(Agent, b_agent["id"]).name == "Agent B"
    deleted = client.delete(f"/api/v1/agents/{b_agent['id']}", headers=h)
    assert deleted.status_code == 403
    db.expire_all()
    assert db.get(Agent, b_agent["id"]).name == "Agent B"
    assert client.get(f"/api/v1/agents/{b_agent['id']}", headers=h).status_code == 404


def test_client_cannot_create_agent_even_with_forged_client_id(client, tenants):
    resp = client.post("/api/v1/agents", headers=auth_headers(tenants["a"]["token"]),
                       json={"name": "New", "client_id": tenants["b"]["client_id"]})
    assert resp.status_code == 403
    tenant_a_agents = client.get(
        "/api/v1/agents", headers=auth_headers(tenants["a"]["token"])
    ).json()["data"]
    tenant_b_agents = client.get(
        "/api/v1/agents", headers=auth_headers(tenants["b"]["token"])
    ).json()["data"]
    assert tenant_a_agents == []
    assert tenant_b_agents == []


def test_admin_agent_creation_uses_path_tenant_not_body(client, tenants):
    from tests.helpers import super_admin_headers

    resp = client.post(
        f"/api/v1/admin/clients/{tenants['a']['client_id']}/agents",
        headers=super_admin_headers(client),
        json={"name": "New", "client_id": tenants["b"]["client_id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["client_id"] == tenants["a"]["client_id"]
    assert len(client.get(
        "/api/v1/agents", headers=auth_headers(tenants["a"]["token"])
    ).json()["data"]) == 1
    assert client.get(
        "/api/v1/agents", headers=auth_headers(tenants["b"]["token"])
    ).json()["data"] == []


def test_only_super_admin_can_list_a_clients_agents(client, tenants):
    a_id = tenants["a"]["client_id"]
    denied = client.get(f"/api/v1/clients/{a_id}/agents", headers=auth_headers(tenants["a"]["token"]))
    assert denied.status_code == 403


# ---------------- webhooks ----------------
def test_webhook_call_is_attributed_to_the_correct_tenant_via_agent_id(client, db, tenants):
    from app.models.call import Call

    a_agent = create_agent(client, tenants["a"]["token"], "Agent A", provider_agent_id="ref-a")
    create_agent(client, tenants["b"]["token"], "Agent B", provider_agent_id="ref-b")
    resp = send_webhook(client, webhook_body(agent_id="ref-a", call={
        "provider_call_id": "call-iso-1", "phone_number": "+919876543210", "direction": "inbound"}))
    assert resp.json()["data"]["status"] == "processed"
    call = db.scalar(select(Call).where(Call.provider_call_id == "call-iso-1"))
    assert call.client_id == tenants["a"]["client_id"] and call.agent_id == a_agent["id"]


def test_webhook_cannot_cancel_other_tenants_appointment_via_shared_phone_format(client, db, tenants):
    """Even a well-formed request naming a real appointment id only affects its own tenant,
    because the tenant comes from agent_id, and the phone+appointment must match that tenant."""
    create_agent(client, tenants["a"]["token"], "Agent A", provider_agent_id="ref-a")
    cust_b = make_customer(client, tenants["b"]["token"], "Bala", "+919888888888")
    appt_b = make_appointment(client, tenants["b"]["token"], cust_b["id"])
    resp = send_webhook(client, webhook_body(event_type="appointment_cancelled", agent_id="ref-a",
                                             appointment={"customer_phone": "+919888888888",
                                                         "appointment_id": appt_b["id"]}))
    assert resp.json()["data"]["status"] == "failed"
    from app.models.appointment import Appointment

    assert db.get(Appointment, appt_b["id"]).status == AppointmentStatus.SCHEDULED


def test_webhook_event_client_id_is_set_from_resolved_agent_never_the_payload(client, db, tenants):
    from app.models.webhook_event import WebhookEvent

    create_agent(client, tenants["a"]["token"], "Agent A", provider_agent_id="ref-a2")
    send_webhook(client, webhook_body(event_id="evt-iso-2", agent_id="ref-a2", call={
        "provider_call_id": "call-iso-2", "phone_number": "+919876543210", "direction": "inbound"}))
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == "evt-iso-2"))
    assert event.client_id == tenants["a"]["client_id"]


# ---------------- dashboard ----------------
def test_dashboard_summary_matches_only_own_tenants_data(client, tenants, records, calls):
    a_summary = client.get("/api/v1/dashboard/summary",
                           headers=auth_headers(tenants["a"]["token"])).json()["data"]
    assert a_summary["total_appointments"] == 1 and a_summary["total_customers"] == 1
    assert a_summary["total_calls"] == 1 and a_summary["total_agents"] == 1


def test_dashboard_stays_independent_as_the_other_tenant_grows(client, db, tenants, records, calls):
    before = client.get("/api/v1/dashboard/summary",
                        headers=auth_headers(tenants["a"]["token"])).json()["data"]
    make_customer(client, tenants["b"]["token"], "Extra", "+919333333333")
    make_call(db, tenants["b"]["client_id"])
    after = client.get("/api/v1/dashboard/summary",
                       headers=auth_headers(tenants["a"]["token"])).json()["data"]
    assert before == after


def test_client_cannot_reach_platform_or_other_clients_dashboard(client, tenants):
    h = auth_headers(tenants["a"]["token"])
    assert client.get("/api/v1/dashboard/admin/summary", headers=h).status_code == 403
    b_id = tenants["b"]["client_id"]
    assert client.get(f"/api/v1/dashboard/admin/clients/{b_id}/summary", headers=h).status_code == 403


def test_super_admin_per_client_summary_matches_that_clients_own_view(client, db, tenants, records):
    make_user(db, None, UserRole.SUPER_ADMIN, "root@platform.com")
    root = auth_headers(login_token(client, "root@platform.com"))
    own_view = client.get("/api/v1/dashboard/summary",
                          headers=auth_headers(tenants["a"]["token"])).json()["data"]
    admin_view = client.get(f"/api/v1/dashboard/admin/clients/{tenants['a']['client_id']}/summary",
                            headers=root).json()["data"]
    assert own_view == admin_view


# ---------------- structural guards (fail when a future stage forgets isolation) ----------------
# Global catalog tables are not tenant-owned and do not have client_id.
GLOBAL_TABLES = {"plans"}
# These records belong to users and intentionally have no direct tenant key.
USER_SCOPED_TABLES = {"email_verifications", "refresh_tokens"}
# client_id may be NULL for super-admin/platform records and public contact enquiries.
NULLABLE_TENANT_TABLES = {
    "users", "audit_logs", "webhook_events", "call_attempts", "enquiries"
}


def test_every_table_has_client_id():
    for table in Base.metadata.sorted_tables:
        if table.name == "clients" or table.name in GLOBAL_TABLES | USER_SCOPED_TABLES:
            continue
        assert "client_id" in table.c, f"{table.name} has no client_id column"
        if table.name not in NULLABLE_TENANT_TABLES:
            assert not table.c.client_id.nullable, f"{table.name}.client_id must be NOT NULL"


def test_tenant_tables_have_client_id_index_or_fk():
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if table.name == "clients" or table.name in GLOBAL_TABLES | USER_SCOPED_TABLES:
            continue
        fks = insp.get_foreign_keys(table.name)
        fk_cols = {c for fk in fks for c in fk["constrained_columns"]}
        assert "client_id" in fk_cols, f"{table.name}.client_id is not a foreign key"

    for table_name in USER_SCOPED_TABLES:
        user_scoped_fks = insp.get_foreign_keys(table_name)
        assert any(
            "user_id" in fk["constrained_columns"] and fk["referred_table"] == "users"
            for fk in user_scoped_fks
        ), f"{table_name}.user_id must be a foreign key to users"


def _requires_auth(dependant) -> bool:
    if dependant.call is get_current_user:
        return True
    return any(_requires_auth(d) for d in dependant.dependencies)


# Webhooks authenticate via provider signature (see integrations/sarvam/webhook.py), not JWT.
PUBLIC_ROUTES = {"/api/v1/health", "/api/v1/auth/register", "/api/v1/auth/login",
                 "/api/v1/auth/refresh", "/api/v1/webhooks/sarvam",
                 "/api/v1/webhooks/sarvam/{token}/outbound",
                 "/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/check-slot",
                 "/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/book",
                 "/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/reschedule",
                 "/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/cancel"}
# Logout revokes the refresh token in its request body and intentionally has no access-token dependency.
PUBLIC_ROUTES.add("/api/v1/auth/logout")
# Forgot-password is public and rate-limited; the admin reset-password route remains super-admin-only.
PUBLIC_ROUTES.add("/api/v1/auth/forgot-password")
# Public plan catalog and rate-limited contact form are used before sign-in.
PUBLIC_ROUTES.update({"/api/v1/plans", "/api/v1/contact"})


def test_every_api_route_requires_authentication_unless_allowlisted():
    app = create_app()
    checked = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1") or path in PUBLIC_ROUTES:
            continue
        checked += 1
        assert _requires_auth(route.dependant), f"{path} is missing authentication"
    assert checked > 10




# ---------------- mandatory acceptance scenario (spec section 28, run literally) ----------------
def test_mandatory_acceptance_scenario_end_to_end(client, db):
    """Create Client A, Client B, a user and an appointment for each, then verify the exact
    checklist: User A sees/modifies/cancels only Appointment A, and never Appointment B."""
    # Create Client A, Client B (each with its first user, User A / User B)
    a = register_ok(client, "usera@a.com", "Client A")
    b = register_ok(client, "userb@b.com", "Client B")
    a_h, b_h = auth_headers(a["tokens"]["access_token"]), auth_headers(b["tokens"]["access_token"])

    # Create Appointment A -> Client A, Appointment B -> Client B
    cust_a = make_customer(client, a["tokens"]["access_token"], "Customer A", "+919000000101")
    cust_b = make_customer(client, b["tokens"]["access_token"], "Customer B", "+919000000102")
    appt_a = make_appointment(client, a["tokens"]["access_token"], cust_a["id"], "2031-01-10", "09:00")
    appt_b = make_appointment(client, b["tokens"]["access_token"], cust_b["id"], "2031-01-11", "11:00")

    # Login as User A (already have the token from registration)
    # User A must SEE Appointment A
    assert client.get(f"/api/v1/appointments/{appt_a['id']}", headers=a_h).status_code == 200
    # User A must MODIFY Appointment A
    mod = client.patch(f"/api/v1/appointments/{appt_a['id']}", headers=a_h, json={"notes": "confirmed by A"})
    assert mod.status_code == 200 and mod.json()["data"]["notes"] == "confirmed by A"
    # User A must CANCEL Appointment A
    assert client.post(f"/api/v1/appointments/{appt_a['id']}/cancel", headers=a_h).status_code == 200

    # User A must NOT see, modify or cancel Appointment B
    assert client.get(f"/api/v1/appointments/{appt_b['id']}", headers=a_h).status_code == 404
    assert client.patch(f"/api/v1/appointments/{appt_b['id']}", headers=a_h,
                        json={"notes": "hacked"}).status_code == 404
    assert client.post(f"/api/v1/appointments/{appt_b['id']}/cancel", headers=a_h).status_code == 404
    # User A must NOT access Client B customers, calls, or agents
    assert client.get(f"/api/v1/customers/{cust_b['id']}", headers=a_h).status_code == 404
    agent_b = create_agent(client, b["tokens"]["access_token"], "Agent B")
    assert client.get(f"/api/v1/agents/{agent_b['id']}", headers=a_h).status_code == 404
    call_b = make_call(db, b["user"]["client_id"])
    assert client.get(f"/api/v1/calls/{call_b.id}", headers=a_h).status_code == 404
    # And Appointment B is untouched by every attempt User A made against it
    unaffected = client.get(f"/api/v1/appointments/{appt_b['id']}", headers=b_h).json()["data"]
    assert unaffected["status"] == "scheduled" and unaffected["notes"] is None

    # Then the same, from Client B's side
    assert client.get(f"/api/v1/appointments/{appt_b['id']}", headers=b_h).status_code == 200
    assert client.patch(f"/api/v1/appointments/{appt_b['id']}", headers=b_h,
                        json={"notes": "confirmed by B"}).status_code == 200
    assert client.post(f"/api/v1/appointments/{appt_b['id']}/cancel", headers=b_h).status_code == 200
    assert client.get(f"/api/v1/appointments/{appt_a['id']}", headers=b_h).status_code == 404
    assert client.get(f"/api/v1/customers/{cust_a['id']}", headers=b_h).status_code == 404
