from concurrent.futures import ThreadPoolExecutor

from conftest import enrollment, proof
from fastapi.testclient import TestClient
from test_service import OTHER, approve, body, create, service_headers

from hooapprove.app import create_app
from hooapprove.config import Settings


def ticket(client, subject="other-human", token=OTHER):
    r = client.post(
        "/v1/pairings",
        json={"subject": subject, "label": "Meine Verbindung"},
        headers=service_headers(token),
    )
    assert r.status_code == 201
    return r.json()["ticket"]


def raw(client):
    return TestClient(client.app)


def test_no_login_or_account_required(tmp_path):
    app = create_app(Settings(database=str(tmp_path / "prod.db"), public_url="https://testserver"))
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/auth/login").status_code == 404
        assert c.post("/api/mobile/session", json={}).status_code == 404
        assert c.get("/api/requests").status_code == 401
        assert not c.cookies


def test_pairing_preview_possession_one_use_and_expiry(client):
    t = ticket(client)
    c = raw(client)
    assert c.post("/api/pairings/preview", json={"ticket": t}).json()["service"] == "mail"
    b, _ = enrollment(t)
    altered = {**b, "signature": "00" * 64}
    assert c.post("/api/pairings/enroll", json=altered).status_code == 401
    assert c.post("/api/pairings/enroll", json=b).status_code == 201
    assert c.post("/api/pairings/enroll", json=b).status_code == 410
    assert c.post("/api/pairings/preview", json={"ticket": t}).status_code == 410
    t = ticket(client, subject="demo-human")
    with client.app.state.store.connection() as db:
        db.execute("UPDATE pairings SET expires=0")
    b, _ = enrollment(t)
    assert c.post("/api/pairings/enroll", json=b).status_code == 410


def test_pairing_consumption_is_atomic(client):
    b, _ = enrollment(ticket(client))
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(
            pool.map(
                lambda _: raw(client).post("/api/pairings/enroll", json=b).status_code, range(8)
            )
        )
    assert codes.count(201) == 1
    assert codes.count(410) == 7


def test_service_cannot_replace_or_pair_unassigned_device(client):
    assert (
        client.post(
            "/v1/pairings",
            json={"subject": "demo-human", "label": "Replacement"},
            headers=service_headers(),
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/v1/pairings",
            json={"subject": "other-human", "label": "Other"},
            headers=service_headers(),
        ).status_code
        == 403
    )


def test_outstanding_tickets_cannot_replace_device(client):
    first, second = ticket(client), ticket(client)
    c = raw(client)
    b, _ = enrollment(first)
    assert c.post("/api/pairings/enroll", json=b).status_code == 201
    b, _ = enrollment(second)
    assert c.post("/api/pairings/enroll", json=b).status_code == 410


def test_proof_binds_method_path_body_and_is_one_use(client):
    c = raw(client)
    h = proof(client.device_key, client.device_id, "GET", "/api/me")
    assert c.get("/api/requests", headers=h).status_code == 401
    assert c.get("/api/me", headers=h).status_code == 200
    assert c.get("/api/me", headers=h).status_code == 401
    value = create(client)
    path = f"/api/requests/{value['id']}/decision"
    h = proof(client.device_key, client.device_id, "POST", path, b"{}")
    assert (
        c.post(path, headers=h, json={"decision": "approve", "digest": value["digest"]}).status_code
        == 401
    )
    h = proof(client.device_key, client.device_id, "GET", "/api/me", timestamp="0")
    assert c.get("/api/me", headers=h).status_code == 401


def test_revocation_blocks_old_key_and_repair_is_explicit(client):
    assert client.post("/api/device/unlink", json={}).status_code == 200
    assert client.get("/api/me").status_code == 401
    value = create(client)
    assert approve(client, value).status_code == 401
    assert (
        client.post(
            "/v1/pairings",
            json={"subject": "demo-human", "label": "New"},
            headers=service_headers(),
        ).status_code
        == 201
    )


def test_same_recipient_different_service_is_isolated(client):
    r = client.post("/v1/requests", json=body(), headers=service_headers(OTHER))
    assert r.status_code == 201
    value = r.json()
    assert client.get("/api/requests").json() == []
    assert approve(client, value).status_code == 404
    assert client.get(f"/api/requests/{value['id']}/events").status_code == 404


def test_wrong_key_and_concurrent_replay(client):
    _, key = enrollment("x" * 48)
    c = raw(client)
    assert (
        c.get("/api/me", headers=proof(key, client.device_id, "GET", "/api/me")).status_code == 401
    )
    h = proof(client.device_key, client.device_id, "GET", "/api/me")
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(
            pool.map(lambda _: raw(client).get("/api/me", headers=h).status_code, range(8))
        )
    assert codes.count(200) == 1
    assert codes.count(401) == 7


def test_migration_removes_login_capabilities_preserves_decisions(client):
    from hooapprove.store import Store

    value = create(client)
    assert approve(client, value).status_code == 200
    with client.app.state.store.connection() as db:
        db.execute("CREATE TABLE mobile_sessions (hash TEXT)")
        db.execute("INSERT INTO mobile_sessions VALUES('obsolete-credential')")
    migrated = Store(client.app.state.settings.database)
    assert migrated.get(value["id"], "rewe")["status"] == "approved"
    with migrated.connection() as db:
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name='mobile_sessions'"
        ).fetchone()
        assert migrated.active_device(db, client.device_id)["service"] == "rewe"


def test_revocation_rechecked_inside_decision_transaction(client):
    import pytest
    from fastapi import HTTPException

    from hooapprove.models import Decision

    value = create(client)
    assert client.post("/api/device/unlink", json={}).status_code == 200
    with pytest.raises(HTTPException) as failure:
        client.app.state.store.decide(
            value["id"],
            "demo-human",
            Decision(decision="approve", digest=value["digest"]),
            "rewe",
            client.device_id,
        )
    assert failure.value.status_code == 401
    assert client.app.state.store.get(value["id"], "rewe")["status"] == "pending"
