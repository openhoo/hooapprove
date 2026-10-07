from concurrent.futures import ThreadPoolExecutor

import pytest
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


@pytest.mark.parametrize("timestamp", ["1" * 400, "-" + "1" * 400, "1" * 4301])
def test_oversized_timestamp_is_rejected_without_server_error(client, timestamp):
    response = raw(client).get(
        "/api/me", headers={"X-Device-Time": timestamp, "X-Device-Nonce": "a" * 32}
    )
    assert response.status_code == 401


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


@pytest.mark.parametrize(
    "public_key",
    [
        bytes(32),
        b"\x01" + bytes(31),
        bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"),
        bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"),
        (2**255 - 20).to_bytes(32, "little"),
        (2**255 - 19).to_bytes(32, "little"),
        (2**255 - 18).to_bytes(32, "little"),
        b"\x01" + bytes(30) + b"\x80",
    ],
)
def test_unsafe_public_keys_cannot_enroll(client, public_key):
    t = ticket(client)
    b, _ = enrollment(t)
    b.update(public_key=public_key.hex(), signature=(b"\x01" + bytes(63)).hex())
    assert raw(client).post("/api/pairings/enroll", json=b).status_code == 401
    # Failed key validation must not consume the bootstrap ticket.
    valid, _ = enrollment(t)
    assert raw(client).post("/api/pairings/enroll", json=valid).status_code == 201


def test_previously_paired_identity_key_cannot_forge_decisions(client):
    value = create(client)
    with client.app.state.store.connection() as db:
        db.execute(
            "UPDATE paired_devices SET public_key=? WHERE id=?",
            ((b"\x01" + bytes(31)).hex(), client.device_id),
        )
    # This constant signature verifies for any message with this unsafe public
    # key in some OpenSSL versions. Recheck the key on every proof, not only enroll.
    path = f"/api/requests/{value['id']}/decision"
    h = proof(client.device_key, client.device_id, "POST", path)
    h["X-Device-Signature"] = (b"\x01" + bytes(63)).hex()
    assert (
        raw(client)
        .post(path, headers=h, json={"decision": "approve", "digest": value["digest"]})
        .status_code
        == 401
    )
    assert client.app.state.store.get(value["id"], "rewe")["status"] == "pending"


def test_mixed_order_key_rejected_even_with_older_libsodium(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from fastapi import HTTPException
    from nacl.bindings import crypto_core_ed25519_add

    from hooapprove import devices

    key = Ed25519PrivateKey.generate()
    mixed = crypto_core_ed25519_add(key.public_key().public_bytes_raw(), bytes(32))
    # Simulate libsodium <=1.0.20's permissive initial membership check.
    monkeypatch.setattr(devices, "crypto_core_ed25519_is_valid_point", lambda _: True)

    class PermissiveVerifier:
        @classmethod
        def from_public_bytes(cls, _):
            pytest.fail("A mixed-order key reached signature verification")

    monkeypatch.setattr(devices, "Ed25519PublicKey", PermissiveVerifier)
    with pytest.raises(HTTPException) as failure:
        devices.verify(mixed.hex(), key.sign(b"message").hex(), b"message")
    assert failure.value.status_code == 401


@pytest.mark.parametrize("operation", ["list", "decide", "events"])
@pytest.mark.parametrize("subject,service", [("other-human", "rewe"), ("demo-human", "mail")])
def test_store_enforces_device_recipient_and_service(client, operation, subject, service):
    from fastapi import HTTPException

    from hooapprove.models import Decision

    value = create(client)
    store = client.app.state.store
    with pytest.raises(HTTPException) as failure:
        if operation == "list":
            store.list_for(subject, service, client.device_id)
        elif operation == "decide":
            store.decide(
                value["id"],
                subject,
                Decision(decision="approve", digest=value["digest"]),
                service,
                client.device_id,
            )
        else:
            store.events(value["id"], subject, service, client.device_id)
    assert failure.value.status_code == 401
    assert store.get(value["id"], "rewe")["status"] == "pending"
