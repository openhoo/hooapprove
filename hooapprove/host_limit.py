from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse


class OriginHostMiddleware:
    """Check the configured host, including bracketed IPv6 HTTP authorities."""

    def __init__(self, app, hostname):
        self.app = app
        self.hostname = hostname.lower()
        self.authority = f"[{self.hostname}]" if ":" in self.hostname else self.hostname

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        hosts = [value for key, value in scope["headers"] if key.lower() == b"host"]
        valid = False
        if len(hosts) == 1:
            try:
                authority = urlsplit("//" + hosts[0].decode("ascii"))
                _ = authority.port
                netloc = authority.netloc.lower()
                expected_authority = netloc == self.authority or (
                    netloc.startswith(self.authority + ":")
                    and netloc[len(self.authority) + 1 :].isascii()
                    and netloc[len(self.authority) + 1 :].isdigit()
                )
                valid = (
                    expected_authority
                    and authority.hostname is not None
                    and authority.hostname.lower() == self.hostname
                    and authority.username is None
                    and authority.password is None
                    and not authority.path
                    and not authority.query
                    and not authority.fragment
                    and not any(character.isspace() for character in authority.netloc)
                )
            except (ValueError, UnicodeError):
                pass
        if valid:
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
