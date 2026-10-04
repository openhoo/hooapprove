import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Settings:
    database: str = "data/hooapprove.db"
    public_url: str = "http://127.0.0.1:8097"
    services: dict = field(default_factory=dict)
    demo: bool = False

    @classmethod
    def from_env(cls):
        secrets_path = os.environ.get("HOOAPPROVE_SECRETS_FILE", "")
        values = json.loads(Path(secrets_path).read_text()) if secrets_path else {}
        # Rolling migration: obsolete login/push fields are ignored, never used.
        for obsolete in (
            "session_secret",
            "issuer",
            "client_id",
            "client_secret",
            "vapid_private_key",
            "vapid_public_key",
            "vapid_contact",
        ):
            values.pop(obsolete, None)
        return cls(
            database=os.environ.get("HOOAPPROVE_DATABASE", "data/hooapprove.db"),
            public_url=os.environ.get("HOOAPPROVE_PUBLIC_URL", "http://127.0.0.1:8097").rstrip("/"),
            demo=os.environ.get("HOOAPPROVE_DEMO") == "1",
            **values,
        )

    def validate(self):
        url = urlparse(self.public_url)
        if self.demo:
            if url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
                raise ValueError("Demo mode is restricted to loopback")
        elif url.scheme != "https" or not url.hostname:
            raise ValueError("Production requires HTTPS")
        for name, service in self.services.items():
            if len(service.get("token", "")) < 32 or not service.get("subjects"):
                raise ValueError(f"Service {name} requires a strong token and explicit subjects")
