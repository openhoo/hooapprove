import asyncio

import pytest
from fastapi.testclient import TestClient
from test_service import approve, claim, create, service_headers

from hooapprove.app import create_app
from hooapprove.body_limit import BodyLimitMiddleware
from hooapprove.config import Settings


@pytest.mark.parametrize(
    "url",
    [
        "https://operator:private@approve.example",
        "https://approve.example/api",
        "https://approve.example?token=private",
        "https://approve.example#private",
        "https://approve.example:invalid",
        "file://localhost",
        "https:///missing-host",
        "https://approve.\nexample",
        "https://[::1]evil",
        "https://approve.example:",
    ],
)
def test_configuration_rejects_non_origin_urls(url):
    with pytest.raises(ValueError):
        Settings(public_url=url).validate()


@pytest.mark.parametrize(
    "services",
    [
        [],
        {"example": None},
        {"": {"token": "a" * 40, "subjects": ["owner"]}},
        {"example": {"token": "a" * 40, "subjects": "owner"}},
        {"example": {"token": "a" * 40, "subjects": [""]}},
        {"example": {"token": "a" * 40, "subjects": [42]}},
        {"example": {"token": 42, "subjects": ["owner"]}},
        {"example": {"token": "a" * 40 + "\n", "subjects": ["owner"]}},
        {"example": {"token": "ü" * 40, "subjects": ["owner"]}},
        {"example": {"token": "a" * 40 + "\x7f", "subjects": ["owner"]}},
        {
            "first": {"token": "a" * 40, "subjects": ["owner"]},
            "second": {"token": "a" * 40, "subjects": ["other"]},
        },
    ],
)
def test_configuration_fails_closed_for_ambiguous_service_credentials(services):
    with pytest.raises(ValueError):
        Settings(public_url="https://approve.example", services=services).validate()


def test_validation_does_not_echo_pairing_secrets(client):
    sensitive = "private-pairing-material"
    response = client.post("/api/pairings/preview", json={"ticket": sensitive})
    assert response.status_code == 422
    assert sensitive not in response.text
    response = client.post("/api/pairings/enroll", json={"ticket": sensitive * 2})
    assert response.status_code == 422
    assert sensitive not in response.text
    response = client.post("/api/pairings/preview", content='{"ticket":"' + sensitive)
    assert response.status_code == 422
    assert sensitive not in response.text


def test_validation_does_not_echo_unknown_private_fields(client):
    response = client.post(
        "/api/pairings/preview",
        json={"ticket": "a" * 64, "private-unknown-key": "private-unknown-value"},
    )
    assert response.status_code == 422
    assert "private-unknown" not in response.text


def test_untrusted_host_is_rejected(client):
    response = client.get("/healthz", headers={"Host": "untrusted.example"})
    assert response.status_code == 400


def test_ipv6_loopback_origin_is_supported(tmp_path):
    app = create_app(
        Settings(database=str(tmp_path / "ipv6.db"), public_url="http://[::1]:8097", demo=True)
    )
    with TestClient(app, base_url="http://[::1]:8097") as client:
        assert client.get("/healthz").status_code == 200
        for host in (
            "[::2]:8097",
            "operator@[::1]:8097",
            "[::1]:invalid",
            "[::1]/bad",
            "[::1]evil",
            "[::1]:",
            "[::1]:999999",
        ):
            assert client.get("/healthz", headers={"Host": host}).status_code == 400


def test_removed_recipient_cannot_claim_old_approval(client):
    value = create(client)
    assert approve(client, value).status_code == 200
    client.app.state.settings.services["rewe"]["subjects"] = ["new-owner"]
    assert claim(client, value).status_code == 403
    assert client.app.state.store.get(value["id"], "rewe")["status"] == "approved"
    assert (
        client.post(f"/v1/requests/{value['id']}/cancel", headers=service_headers()).status_code
        == 200
    )


def test_removed_recipient_can_finalize_already_claimed_action(client):
    value = create(client)
    assert approve(client, value).status_code == 200
    receipt = claim(client, value).json()
    client.app.state.settings.services["rewe"]["subjects"] = ["new-owner"]
    response = client.post(
        f"/v1/requests/{value['id']}/result",
        headers=service_headers(),
        json={
            "execution_id": receipt["execution_id"],
            "outcome": "completed",
            "reference": "synthetic-completed-action",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_chunked_body_limit_without_content_length():
    async def exercise():
        messages = iter(
            [
                {"type": "http.request", "body": b"12345", "more_body": True},
                {"type": "http.request", "body": b"67890", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        async def downstream(scope, receive, send):
            pytest.fail("Oversized body reached application")

        await BodyLimitMiddleware(downstream, limit=8)(
            {"type": "http", "method": "POST", "headers": []}, receive, send
        )
        assert sent[0]["status"] == 413

    asyncio.run(exercise())


def test_body_limit_replays_exact_signed_bytes():
    async def exercise():
        messages = iter(
            [
                {"type": "http.request", "body": b'{"x":', "more_body": True},
                {"type": "http.request", "body": b'"y"}', "more_body": False},
            ]
        )

        async def receive():
            return next(messages)

        async def send(message):
            pass

        async def downstream(scope, receive, send):
            assert await receive() == {
                "type": "http.request",
                "body": b'{"x":"y"}',
                "more_body": False,
            }

        await BodyLimitMiddleware(downstream, limit=9)(
            {"type": "http", "method": "POST", "headers": []}, receive, send
        )

    asyncio.run(exercise())
