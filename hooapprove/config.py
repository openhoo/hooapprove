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
        if any(character.isspace() or ord(character) < 33 for character in self.public_url):
            raise ValueError("Public URL must not contain whitespace or control characters")
        url = urlparse(self.public_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError("Public URL must be an HTTP(S) origin without credentials")
        try:
            _ = url.port
        except ValueError:
            raise ValueError("Public URL has an invalid port") from None
        host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
        authority = url.netloc.lower()
        if not host.isascii() or not (
            authority == host
            or (
                authority.startswith(host + ":")
                and authority[len(host) + 1 :].isascii()
                and authority[len(host) + 1 :].isdigit()
            )
        ):
            raise ValueError("Public URL must have a valid ASCII host and optional numeric port")
        if self.demo:
            if url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
                raise ValueError("Demo mode is restricted to loopback")
        elif url.scheme != "https" or not url.hostname:
            raise ValueError("Production requires HTTPS")
        if not isinstance(self.services, dict):
            raise ValueError("Services must be a mapping")
        tokens = set()
        for name, service in self.services.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(service, dict):
                raise ValueError("Services require nonempty names and configuration mappings")
            token, subjects = service.get("token"), service.get("subjects")
            if (
                not isinstance(token, str)
                or len(token) < 32
                or not token.isascii()
                or any(ord(character) < 33 or ord(character) > 126 for character in token)
                or not isinstance(subjects, list)
                or not subjects
                or any(
                    not isinstance(subject, str) or not subject.strip() or len(subject) > 200
                    for subject in subjects
                )
            ):
                raise ValueError("Each service requires a strong token and explicit subject list")
            if token in tokens:
                raise ValueError("Service tokens must be unique")
            tokens.add(token)
