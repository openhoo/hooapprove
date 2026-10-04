from concurrent.futures import ThreadPoolExecutor

import pytest

from hooapprove.app import create_app
from hooapprove.config import Settings
from hooapprove.models import ActionRequest, action_digest

TOKEN = "test-service-token-" + "a" * 40
OTHER = "test-other-token-" + "b" * 40


def body(**changes):
    return {
        "subject": "demo-human",
        "action": "order.place",
        "title": "Einkauf bestellen",
        "summary": "Eine Bestellung über 12,00 €",
        "details": [{"label": "Betrag", "value": "12,00 €"}],
        "payload": {"cart_id": "1", "total_minor": 1200, "currency": "EUR"},
        "idempotency_key": "cart-1-v1",
        **changes,
    }


def service_headers(token=TOKEN):
    return {"Authorization": "Bearer " + token}


def create(client, **changes):
    response = client.post("/v1/requests", json=body(**changes), headers=service_headers())
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, value):
    return client.post(
        f"/api/requests/{value['id']}/decision",
        json={"decision": "approve", "digest": value["digest"]},
    )


def claim(client, value, token=TOKEN, digest=None):
    return client.post(
        f"/v1/requests/{value['id']}/claim",
        json={"digest": digest or value["digest"]},
        headers=service_headers(token),
    )


def test_human_approval_execution_result_and_history(client):
    value = create(client)
    assert "payload" not in value
    assert claim(client, value).status_code == 409
    assert approve(client, value).status_code == 200
    receipt = claim(client, value).json()
    assert receipt["status"] == "executing"
    assert receipt["payload"]["total_minor"] == 1200
    result = {
        "execution_id": receipt["execution_id"],
        "outcome": "completed",
        "reference": "order-123",
    }
    url = f"/v1/requests/{value['id']}/result"
    assert client.post(url, json=result, headers=service_headers()).status_code == 200
    assert client.post(url, json=result, headers=service_headers()).status_code == 200
    events = client.get(f"/api/requests/{value['id']}/events").json()
    assert [e["event"] for e in events] == ["requested", "approved", "claimed", "completed"]


def test_cannot_double_claim_under_concurrency(client):
    value = create(client)
    approve(client, value)
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(lambda _: claim(client, value).status_code, range(8)))
    assert statuses.count(200) == 1
    assert statuses.count(409) == 7


@pytest.mark.parametrize(
    "field,new",
    [
        ("payload", {"cart_id": "1", "total_minor": 1300, "currency": "EUR"}),
        ("title", "Anderer Einkauf"),
        ("summary", "Andere Beschreibung"),
        ("details", [{"label": "Betrag", "value": "13,00 €"}]),
    ],
)
def test_changed_action_cannot_reuse_idempotency_key(client, field, new):
    create(client)
    response = client.post("/v1/requests", json=body(**{field: new}), headers=service_headers())
    assert response.status_code == 409


def test_duplicate_request_does_not_refresh_expiry(client):
    first = create(client)
    second = create(client, expires_in=1800)
    assert first["id"] == second["id"]
    assert first["expires"] == second["expires"]


def test_changed_live_snapshot_cannot_execute(client):
    value = create(client)
    approve(client, value)
    changed = ActionRequest(**body(payload={"total_minor": 1300}))
    assert claim(client, value, digest=action_digest("rewe", changed)).status_code == 409
    assert claim(client, value).status_code == 200


def test_agent_credentials_cannot_approve(client):
    value = create(client)
    response = client.post(
        f"/api/requests/{value['id']}/decision",
        headers=service_headers(),
        json={"decision": "approve", "digest": value["digest"]},
    )
    assert response.status_code == 401


def test_foreign_service_cannot_read_or_execute(client):
    value = create(client)
    approve(client, value)
    assert claim(client, value, token=OTHER).status_code == 404
    assert (
        client.get(f"/v1/requests/{value['id']}", headers=service_headers(OTHER)).status_code == 404
    )


def test_service_cannot_choose_unassigned_human(client):
    assert (
        client.post(
            "/v1/requests", json=body(subject="other-human"), headers=service_headers()
        ).status_code
        == 403
    )


def test_human_cannot_read_or_decide_another_users_request(client):
    response = client.post(
        "/v1/requests", json=body(subject="other-human"), headers=service_headers(OTHER)
    )
    value = response.json()
    assert client.get("/api/requests").json() == []
    assert approve(client, value).status_code == 404
    assert client.get(f"/api/requests/{value['id']}/events").status_code == 404


@pytest.mark.parametrize("state", ["pending", "approved"])
def test_expiry_enforced_without_polling(client, state):
    value = create(client)
    if state == "approved":
        approve(client, value)
    with client.app.state.store.connection() as db:
        db.execute("UPDATE requests SET expires=0 WHERE id=?", (value["id"],))
    assert approve(client, value).status_code == 409
    assert claim(client, value).status_code == 409
    assert client.get("/api/requests").json()[0]["status"] == "expired"


@pytest.mark.parametrize("decision", ["reject", "approve"])
def test_decision_cannot_be_changed(client, decision):
    value = create(client)
    client.post(
        f"/api/requests/{value['id']}/decision",
        json={"decision": decision, "digest": value["digest"]},
    )
    assert approve(client, value).status_code == 409
    if decision == "reject":
        assert claim(client, value).status_code == 409


def test_wrong_digest_cannot_approve(client):
    value = create(client)
    assert (
        client.post(
            f"/api/requests/{value['id']}/decision",
            json={"decision": "approve", "digest": "a" * 64},
        ).status_code
        == 409
    )


def test_cancel_before_execution(client):
    value = create(client)
    approve(client, value)
    assert (
        client.post(f"/v1/requests/{value['id']}/cancel", headers=service_headers()).status_code
        == 200
    )
    assert claim(client, value).status_code == 409


def test_uncertain_outcome_is_not_retryable(client):
    value = create(client)
    approve(client, value)
    receipt = claim(client, value).json()
    url = f"/v1/requests/{value['id']}/result"
    assert (
        client.post(
            url,
            json={"execution_id": receipt["execution_id"], "outcome": "uncertain"},
            headers=service_headers(),
        ).status_code
        == 200
    )
    assert claim(client, value).status_code == 409
    assert (
        client.post(
            url,
            json={"execution_id": receipt["execution_id"], "outcome": "completed"},
            headers=service_headers(),
        ).status_code
        == 409
    )


def test_result_requires_claim_and_correct_execution_id(client):
    value = create(client)
    url = f"/v1/requests/{value['id']}/result"
    assert (
        client.post(
            url, json={"execution_id": "fake", "outcome": "completed"}, headers=service_headers()
        ).status_code
        == 409
    )
    approve(client, value)
    claim(client, value)
    assert (
        client.post(
            url, json={"execution_id": "fake", "outcome": "completed"}, headers=service_headers()
        ).status_code
        == 409
    )


def test_production_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        create_app(Settings(database=str(tmp_path / "bad.db")))
    with pytest.raises(ValueError):
        create_app(
            Settings(
                database=str(tmp_path / "bad.db"),
                demo=True,
                public_url="https://approve.openhoo.dev",
            )
        )


def test_payload_size_and_schema_validation(client):
    assert (
        client.post(
            "/v1/requests", json=body(payload={"huge": "a" * 65_000}), headers=service_headers()
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/requests", json={**body(), "approved": True}, headers=service_headers()
        ).status_code
        == 422
    )


def test_static_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/sw.js").status_code == 200


def test_persistent_decision_survives_reopen(client):
    from hooapprove.store import Store

    value = create(client)
    approve(client, value)
    store = Store(client.app.state.settings.database)
    assert store.get(value["id"], "rewe")["status"] == "approved"


def test_digest_is_stable_across_dictionary_order():
    first = ActionRequest(**body(payload={"a": 1, "b": 2}))
    second = ActionRequest(**body(payload={"b": 2, "a": 1}))
    assert action_digest("rewe", first) == action_digest("rewe", second)
