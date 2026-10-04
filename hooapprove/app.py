import base64
import hashlib
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .body_limit import BodyLimitMiddleware
from .config import Settings
from .models import ActionRequest, Claim, Decision, Result, StrictModel
from .push import notify
from .store import Store

STATIC = Path(__file__).parent / "static"


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge_for(verifier):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


class MobileExchange(StrictModel):
    ticket: str = Field(min_length=32, max_length=128)
    verifier: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")


class Device(StrictModel):
    token: str = Field(pattern=r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{8,200}\]$")


class Subscription(StrictModel):
    endpoint: str = Field(max_length=2000)
    keys: dict[str, str]


def create_app(settings=None):
    settings = settings or Settings.from_env()
    settings.validate()
    if settings.demo and not settings.session_secret:
        settings.session_secret = secrets.token_urlsafe(48)
    store = Store(settings.database)
    app = FastAPI(
        title="HooApprove", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="hooapprove_session",
        max_age=43200,
        same_site="lax",
        https_only=not settings.demo,
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=[urlparse(settings.public_url).hostname]
    )
    app.add_middleware(BodyLimitMiddleware)
    oauth = OAuth()
    if not settings.demo:
        oauth.register(
            "openhoo",
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            server_metadata_url=settings.issuer + "/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
        )

    @app.middleware("http")
    async def security_headers(request, call_next):
        if settings.demo and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Demo is loopback-only"}, status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        if not settings.demo:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def user(request: Request):
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            with store.connection() as db:
                row = db.execute(
                    "SELECT * FROM mobile_sessions WHERE hash=? AND expires>?",
                    (token_hash(auth[7:]), time.time()),
                ).fetchone()
            if row:
                return {"sub": row["subject"], "name": row["name"], "mobile": True}
            raise HTTPException(401, "Mobile session expired")
        identity = request.session.get("user")
        if not identity:
            raise HTTPException(401, "Sign in to OpenHoo")
        return identity

    def human_write(request: Request, identity=Depends(user)):
        if not identity.get("mobile"):
            csrf = request.headers.get("x-csrf-token", "")
            if (
                request.headers.get("origin") != settings.public_url
                or not csrf
                or not secrets.compare_digest(
                    csrf.encode(), request.session.get("csrf", "").encode()
                )
            ):
                raise HTTPException(403, "Invalid origin or CSRF token")
        return identity

    def service(request: Request):
        bearer = request.headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            for name, config in settings.services.items():
                if secrets.compare_digest(bearer[7:].encode(), config["token"].encode()):
                    return name
        raise HTTPException(401, "Service authentication required")

    @app.get("/healthz")
    def health():
        with store.connection() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "mode": "demo" if settings.demo else "production"}

    @app.get("/auth/login")
    async def login(request: Request, mobile_challenge: str = ""):
        if mobile_challenge and not re.fullmatch(r"[A-Za-z0-9_-]{43}", mobile_challenge):
            raise HTTPException(400, "Invalid mobile challenge")
        if mobile_challenge:
            request.session["mobile_challenge"] = mobile_challenge
        else:
            request.session.pop("mobile_challenge", None)
        if settings.demo:
            request.session["user"] = {"sub": "demo-human", "name": "Alex · Demo"}
            request.session["csrf"] = secrets.token_urlsafe(32)
            return finish_login(request)
        return await oauth.openhoo.authorize_redirect(
            request, settings.public_url + "/auth/callback"
        )

    def finish_login(request):
        challenge = request.session.pop("mobile_challenge", None)
        if not challenge:
            return RedirectResponse("/")
        identity = request.session["user"]
        ticket = secrets.token_urlsafe(48)
        with store.connection() as db:
            db.execute("DELETE FROM mobile_tickets WHERE expires<=?", (time.time(),))
            db.execute(
                "INSERT INTO mobile_tickets VALUES(?,?,?,?,?)",
                (
                    token_hash(ticket),
                    identity["sub"],
                    identity["name"],
                    challenge,
                    time.time() + 60,
                ),
            )
        return RedirectResponse("hooapprove://callback?ticket=" + ticket)

    @app.get("/auth/callback")
    async def callback(request: Request):
        if settings.demo:
            raise HTTPException(404)
        try:
            token = await oauth.openhoo.authorize_access_token(request)
            identity = token["userinfo"]
            if identity.get("iss") != settings.issuer or not identity.get("sub"):
                raise HTTPException(401, "Invalid OpenHoo identity")
            # Authlib validates state, signature, audience, expiration and OIDC nonce.
            challenge = request.session.get("mobile_challenge")
            request.session.clear()
            if challenge:
                request.session["mobile_challenge"] = challenge
            request.session["user"] = {
                "sub": identity["sub"],
                "name": identity.get("name", "OpenHoo"),
            }
            request.session["csrf"] = secrets.token_urlsafe(32)
            return finish_login(request)
        except (OAuthError, KeyError, ValueError):
            raise HTTPException(401, "OpenHoo sign-in failed") from None

    @app.post("/api/mobile/session")
    def mobile_session(body: MobileExchange):
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM mobile_tickets WHERE hash=? AND expires>?",
                (token_hash(body.ticket), time.time()),
            ).fetchone()
            if not row or not secrets.compare_digest(
                row["challenge"], challenge_for(body.verifier)
            ):
                raise HTTPException(401, "Invalid or expired sign-in ticket")
            db.execute("DELETE FROM mobile_tickets WHERE hash=?", (token_hash(body.ticket),))
            value = secrets.token_urlsafe(48)
            expires = time.time() + 43200
            db.execute("DELETE FROM mobile_sessions WHERE expires<=?", (time.time(),))
            db.execute(
                "INSERT INTO mobile_sessions VALUES(?,?,?,?)",
                (token_hash(value), row["subject"], row["name"], expires),
            )
            return {"token": value, "expires": expires}

    @app.get("/api/me")
    def me(request: Request, identity=Depends(user)):
        return {
            **identity,
            "csrf": request.session.get("csrf", ""),
            "demo": settings.demo,
            "push_public_key": settings.vapid_public_key,
        }

    @app.post("/api/logout")
    def logout(request: Request, identity=Depends(human_write)):
        if identity.get("mobile"):
            with store.connection() as db:
                db.execute(
                    "DELETE FROM mobile_sessions WHERE hash=?",
                    (token_hash(request.headers["authorization"][7:]),),
                )
        request.session.clear()
        return {"ok": True}

    @app.get("/api/requests")
    def inbox(identity=Depends(user)):
        return store.list_for(identity["sub"])

    @app.post("/api/requests/{rid}/decision")
    def decide(rid: str, body: Decision, identity=Depends(human_write)):
        return store.decide(rid, identity["sub"], body)

    @app.get("/api/requests/{rid}/events")
    def events(rid: str, identity=Depends(user)):
        return store.events(rid, identity["sub"])

    @app.post("/api/native-devices")
    def native_device(body: Device, identity=Depends(human_write)):
        with store.connection() as db:
            old = db.execute(
                "SELECT subject FROM native_devices WHERE token=?", (body.token,)
            ).fetchone()
            if old and old["subject"] != identity["sub"]:
                raise HTTPException(409, "Device belongs to another identity; unregister it first")
            db.execute(
                "INSERT OR IGNORE INTO native_devices VALUES(?,?)", (body.token, identity["sub"])
            )
        return {"ok": True}

    @app.delete("/api/native-devices")
    def remove_device(body: Device, identity=Depends(human_write)):
        with store.connection() as db:
            db.execute(
                "DELETE FROM native_devices WHERE token=? AND subject=?",
                (body.token, identity["sub"]),
            )
        return {"ok": True}

    @app.post("/api/push-subscriptions")
    def subscribe(body: Subscription, identity=Depends(human_write)):
        if not settings.vapid_public_key:
            raise HTTPException(503, "Web push is not configured")
        host = urlparse(body.endpoint).hostname or ""
        # Never let an arbitrary subscription URL turn notification delivery into SSRF.
        allowed = {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}
        if urlparse(body.endpoint).scheme != "https" or host not in allowed:
            raise HTTPException(400, "Unsupported push provider")
        if set(body.keys) != {"auth", "p256dh"} or any(len(v) > 200 for v in body.keys.values()):
            raise HTTPException(400, "Invalid push keys")
        with store.connection() as db:
            old = db.execute(
                "SELECT subject FROM subscriptions WHERE endpoint=?", (body.endpoint,)
            ).fetchone()
            if old and old["subject"] != identity["sub"]:
                raise HTTPException(409, "Subscription belongs to another identity")
            import json

            db.execute(
                "INSERT OR REPLACE INTO subscriptions VALUES(?,?,?)",
                (identity["sub"], body.endpoint, json.dumps(body.model_dump())),
            )
        return {"ok": True}

    @app.post("/v1/requests", status_code=201)
    def create(body: ActionRequest, background: BackgroundTasks, name=Depends(service)):
        if body.subject not in settings.services[name]["subjects"]:
            raise HTTPException(403, "Service is not allowed to request approval from this subject")
        value, created = store.create(name, body)
        if created:
            background.add_task(notify, store, settings, body.subject)
        return {**value, "approval_url": settings.public_url + "/?request=" + value["id"]}

    @app.get("/v1/requests/{rid}")
    def status(rid: str, name=Depends(service)):
        return store.get(rid, name)

    @app.post("/v1/requests/{rid}/claim")
    def claim(rid: str, body: Claim, name=Depends(service)):
        return store.claim(rid, name, body.digest)

    @app.post("/v1/requests/{rid}/result")
    def result(rid: str, body: Result, name=Depends(service)):
        return store.result(rid, name, body)

    @app.post("/v1/requests/{rid}/cancel")
    def cancel(rid: str, name=Depends(service)):
        return store.cancel(rid, name)

    @app.post("/api/demo/request")
    def demo_request(identity=Depends(human_write)):
        if not settings.demo:
            raise HTTPException(404)
        value, _ = store.create(
            "rewe-demo",
            ActionRequest(
                subject=identity["sub"],
                action="order.place",
                title="Deinen Einkauf bestellen",
                summary="Dein Einkaufsassistent hat alles vorbereitet. Prüfe die Bestellung und gib sie frei.",
                details=[
                    {"label": "Gesamtbetrag", "value": "47,83 € · inklusive Lieferung"},
                    {"label": "Warenkorb", "value": "12 Artikel · Milch, Brot, Gemüse und mehr"},
                    {"label": "Lieferung", "value": "Morgen, 18–20 Uhr"},
                    {"label": "Lieferadresse", "value": "Beispielstraße 12, 10115 Berlin"},
                    {"label": "Zahlung", "value": "Visa · endet auf 4242"},
                ],
                payload={
                    "cart_id": "demo-cart",
                    "cart_version": 3,
                    "total_minor": 4783,
                    "currency": "EUR",
                    "address_id": "demo-address",
                    "slot_id": "demo-slot",
                },
                idempotency_key="demo-" + secrets.token_hex(12),
            ),
        )
        return value

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/sw.js")
    def worker():
        return FileResponse(STATIC / "sw.js", media_type="application/javascript")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
