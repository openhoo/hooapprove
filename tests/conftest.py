import pytest
from fastapi.testclient import TestClient
from test_service import OTHER, TOKEN

from hooapprove.app import create_app
from hooapprove.config import Settings


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database=str(tmp_path / "test.db"),
        public_url="http://testserver",
        demo=True,
        services={
            "rewe": {"token": TOKEN, "subjects": ["demo-human"]},
            "mail": {"token": OTHER, "subjects": ["other-human"]},
        },
    )
    with TestClient(create_app(settings)) as c:
        c.get("/auth/login")
        c.headers.update(
            {"Origin": "http://testserver", "X-CSRF-Token": c.get("/api/me").json()["csrf"]}
        )
        yield c
