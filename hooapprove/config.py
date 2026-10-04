import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Settings:
    database: str = "data/hooapprove.db"
    public_url: str = "http://127.0.0.1:8097"
    session_secret: str = ""
    issuer: str = "https://auth.openhoo.ai"
    client_id: str = ""
    client_secret: str = ""
    services: dict = field(default_factory=dict)
    demo: bool = False
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_contact: str = "mailto:ops@openhoo.ai"

    @classmethod
    def from_env(cls):
        secrets_path = os.environ.get("HOOAPPROVE_SECRETS_FILE", "")
        values = json.loads(Path(secrets_path).read_text()) if secrets_path else {}
        return cls(
            database=os.environ.get("HOOAPPROVE_DATABASE", "data/hooapprove.db"),
            public_url=os.environ.get("HOOAPPROVE_PUBLIC_URL", "http://127.0.0.1:8097").rstrip("/"),
            issuer=os.environ.get("HOOAPPROVE_ISSUER", "https://auth.openhoo.ai"),
            demo=os.environ.get("HOOAPPROVE_DEMO") == "1",
            **values,
        )

    def validate(self):
        url = urlparse(self.public_url)
        if self.demo:
            if url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
                raise ValueError("Demo mode is restricted to loopback")
        elif (
            url.scheme != "https"
            or len(self.session_secret) < 32
            or not self.client_id
            or not self.client_secret
            or not self.issuer.startswith("https://")
        ):
            raise ValueError("Production requires HTTPS, OIDC and a strong session secret")
        for name, service in self.services.items():
            if len(service.get("token", "")) < 32 or not service.get("subjects"):
                raise ValueError(f"Service {name} requires a strong token and explicit subjects")
