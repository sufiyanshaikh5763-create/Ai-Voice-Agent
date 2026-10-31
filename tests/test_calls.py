from datetime import datetime, timezone

from app.models.enums import CallDirection, CallStatus, UserRole
from tests.helpers import (auth_headers, create_staff, login_token, make_agent, make_call,
                           make_customer, make_user, register_ok)


def utc(y, m, d, hh=10, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _setup(client, db):
    data = register_ok(client, "admin@a.com", "Tenant A")
    tok, cid = data["tokens"]["access_token"], data["user"]["client_id"]
    return tok, cid, make_agent(db, cid, "Zoya"), make_customer(client, tok)


def _ids(client, token, qs=""):
    resp = client.get(f"/api/v1/calls?{qs}", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return [c["id"] for c in resp.json()["data"]]


def test_list_is_newest_first_paginated_and_omits_transcript(client, db):
    tok, cid, agent, cust = _setup(client, db)
    old = make_call(db, cid, started_at=utc(2030, 1, 1), transcript="hello", recording_url="https://r/1")
    new = make_call(db, cid, started_at=utc(2030, 1, 2), agent_id=agent.id, customer_id=cust["id"])
    body = client.get("/api/v1/calls?limit=1", headers=auth_headers(tok)).json()
    assert [c["id"] for c in body["data"]] == [new.id]
    assert body["pagination"] == {"page": 1, "limit": 1, "total": 2}
    item = body["data"][0]
    assert item["agent"] == {"id": agent.id, "name": "Zoya"} and item["customer"]["id"] == cust["id"]
    assert "transcript" not in item and "recording_url" not in item
    listed_old = client.get("/api/v1/calls?page=2&limit=1", headers=auth_headers(tok)).json()["data"][0]
    assert listed_old["id"] == old.id and listed_old["has_transcript"] and listed_old["has_recording"]


def test_filters_status_direction_agent_customer(client, db):
    tok, cid, agent, cust = _setup(client, db)
    a = make_call(db, cid, status=CallStatus.COMPLETED, agent_id=agent.id, customer_id=cust["id"])
    b = make_call(db, cid, status=CallStatus.MISSED, direction=CallDirection.OUTBOUND)
    assert _ids(client, tok, "status=missed") == [b.id]
    assert _ids(client, tok, "direction=outbound") == [b.id]
    assert _ids(client, tok, f"agent={agent.id}") == [a.id]
    assert _ids(client, tok, f"customer={cust['id']}") == [a.id]
    assert client.get("/api/v1/calls?status=bogus", headers=auth_headers(tok)).status_code == 422


def test_date_filter_uses_client_timezone(client, db):
    tok, cid, _agent, _c = _setup(client, db)
    # 20:00 UTC on Jan 15 is 01:30 on Jan 16 in India.
    call = make_call(db, cid, started_at=utc(2030, 1, 15, 20, 0))
    assert _ids(client, tok, "date=2030-01-15") == []
    assert _ids(client, tok, "date=2030-01-16") == [call.id]
    client.patch("/api/v1/clients/me", headers=auth_headers(tok), json={"timezone": "UTC"})
    assert _ids(client, tok, "date=2030-01-15") == [call.id]
    assert _ids(client, tok, "date=2030-01-16") == []


def test_date_range_filter_and_fallback_to_created_at(client, db):
    tok, cid, _a, _c = _setup(client, db)
    c1 = make_call(db, cid, started_at=utc(2030, 3, 1))
    c2 = make_call(db, cid, started_at=utc(2030, 3, 5))
    make_call(db, cid, started_at=utc(2030, 3, 9))
    assert set(_ids(client, tok, "date_from=2030-03-01&date_to=2030-03-05")) == {c1.id, c2.id}
    never_started = make_call(db, cid, status=CallStatus.INITIATED)  # created_at = now
    assert never_started.id in _ids(client, tok, f"date_from={datetime.now(timezone.utc).date()}")


def test_admin_sees_transcript_and_recording_but_staff_does_not(client, db):
    tok, cid, _a, _c = _setup(client, db)
    call = make_call(db, cid, transcript="Caller: hi", recording_url="https://rec/1", duration=42)
    admin = client.get(f"/api/v1/calls/{call.id}", headers=auth_headers(tok)).json()["data"]
    assert admin["transcript"] == "Caller: hi" and admin["recording_url"] == "https://rec/1"
    create_staff(client, tok, "staff@a.com")
    staff = client.get(f"/api/v1/calls/{call.id}", headers=auth_headers(login_token(client, "staff@a.com")))
    data = staff.json()["data"]
    assert staff.status_code == 200 and data["duration"] == 42
    assert data["transcript"] is None and data["recording_url"] is None
    assert data["has_transcript"] is True and data["has_recording"] is True


def test_unknown_call_404_and_auth_required(client, db):
    tok, *_ = _setup(client, db)
    resp = client.get("/api/v1/calls/99999", headers=auth_headers(tok))
    assert resp.status_code == 404 and resp.json()["error_code"] == "CALL_NOT_FOUND"
    assert client.get("/api/v1/calls").status_code == 401
    assert client.get("/api/v1/calls/1").status_code == 401


def test_super_admin_sees_all_clients_and_can_narrow_by_client(client, db):
    a = register_ok(client, "a@a.com", "Tenant A")
    b = register_ok(client, "b@b.com", "Tenant B")
    ca = make_call(db, a["user"]["client_id"])
    cb = make_call(db, b["user"]["client_id"])
    make_user(db, None, UserRole.SUPER_ADMIN, "root@platform.com")
    root = login_token(client, "root@platform.com")
    assert set(_ids(client, root)) == {ca.id, cb.id}
    assert _ids(client, root, f"client_id={b['user']['client_id']}") == [cb.id]
    detail = client.get(f"/api/v1/calls/{cb.id}", headers=auth_headers(root))
    assert detail.status_code == 200 and detail.json()["data"]["client_id"] == b["user"]["client_id"]
