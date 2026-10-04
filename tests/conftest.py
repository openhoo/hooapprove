import json
import secrets
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from test_service import OTHER, TOKEN

from hooapprove.app import create_app
from hooapprove.config import Settings
from hooapprove.devices import device_message, pairing_message


def proof(key, device_id, method, path, content=b"", **changes):
    timestamp = changes.get("timestamp", str(int(time.time())))
    nonce = changes.get("nonce", secrets.token_hex(16))
    signature = key.sign(device_message(device_id, method, path, timestamp, nonce, content)).hex()
    return {
        "X-Device-Id": device_id,
        "X-Device-Time": timestamp,
        "X-Device-Nonce": nonce,
        "X-Device-Signature": signature,
    }


def enrollment(ticket, key=None):
    key = key or Ed25519PrivateKey.generate()
    device_id = secrets.token_hex(16)
    public_key = key.public_key().public_bytes_raw().hex()
    body = {
        "ticket": ticket,
        "device_id": device_id,
        "public_key": public_key,
        "signature": key.sign(pairing_message(ticket, device_id, public_key)).hex(),
    }
    return body, key


class DeviceClient(TestClient):
    def request(self, method, url, **kwargs):
        headers = kwargs.get("headers") or {}
        if hasattr(self, "device_key") and url.startswith("/api/") and not headers:
            content = b""
            if "json" in kwargs:
                content = json.dumps(
                    kwargs.pop("json"), separators=(",", ":"), ensure_ascii=False
                ).encode()
                kwargs["content"] = content
                headers["Content-Type"] = "application/json"
            headers.update(proof(self.device_key, self.device_id, method, url, content))
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database=str(tmp_path / "test.db"),
        public_url="http://testserver",
        demo=True,
        services={
            "rewe": {"token": TOKEN, "subjects": ["demo-human"]},
            "mail": {"token": OTHER, "subjects": ["other-human", "demo-human"]},
        },
    )
    with DeviceClient(create_app(settings)) as c:
        ticket = c.post(
            "/v1/pairings",
            json={"subject": "demo-human", "label": "Mein REWE"},
            headers={"Authorization": "Bearer " + TOKEN},
        ).json()["ticket"]
        body, key = enrollment(ticket)
        assert c.post("/api/pairings/enroll", json=body).status_code == 201
        c.device_key, c.device_id = key, body["device_id"]
        yield c
