import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from .body_limit import BodyLimitMiddleware
from .config import Settings
from .devices import Enrollment, PairingRequest, Ticket, enroll, issue, paired_device, preview
from .host_limit import OriginHostMiddleware
from .models import ActionRequest, Claim, Decision, Result, StrictModel
from .push import notify
from .store import Store

STATIC = Path(__file__).parent / "static"


class Device(StrictModel):
    token: str = Field(pattern=r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{8,200}\]$")


def create_app(settings=None):
    settings = settings or Settings.from_env()
    settings.validate()
    store = Store(settings.database)
    app = FastAPI(
        title="HooApprove", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(OriginHostMiddleware, hostname=urlparse(settings.public_url).hostname)
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Default validation responses echo private tickets, proofs and action payloads.
        # Locations may also contain attacker-controlled JSON keys, so omit them too.
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    @app.middleware("http")
    async def security_headers(request, call_next):
        if settings.demo and (
            request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}
        ):
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

    @app.post("/v1/pairings", status_code=201)
    def create_pairing(body: PairingRequest, name=Depends(service)):
        if body.subject not in settings.services[name]["subjects"]:
            raise HTTPException(403, "Recipient is not allowed")
        value = issue(store, name, body.subject, body.label)
        return {**value, "uri": "hooapprove://pair?token=" + value["ticket"]}

    @app.post("/api/pairings/preview")
    def pairing_preview(body: Ticket):
        return preview(store, body.ticket)

    @app.post("/api/pairings/enroll", status_code=201)
    def pairing_enroll(body: Enrollment):
        return enroll(store, body)

    @app.post("/api/demo/pairing", status_code=201)
    def demo_pairing():
        if not settings.demo:
            raise HTTPException(404)
        return issue(store, "rewe-demo", "demo-human", "Mein Einkaufsassistent · Demo")

    @app.get("/api/me")
    def me(identity=Depends(paired_device)):
        return {
            "device_id": identity["id"],
            "service": identity["service"],
            "label": identity["label"],
            "demo": settings.demo,
        }

    @app.get("/api/requests")
    def inbox(identity=Depends(paired_device)):
        return store.list_for(identity["subject"], identity["service"], identity["id"])

    @app.post("/api/requests/{rid}/decision")
    def decide(rid: str, body: Decision, identity=Depends(paired_device)):
        return store.decide(rid, identity["subject"], body, identity["service"], identity["id"])

    @app.get("/api/requests/{rid}/events")
    def events(rid: str, identity=Depends(paired_device)):
        return store.events(rid, identity["subject"], identity["service"], identity["id"])

    @app.post("/api/device/unlink")
    def unlink(identity=Depends(paired_device)):
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            store.active_device(db, identity["id"])
            db.execute(
                "UPDATE paired_devices SET revoked=1,push_token=NULL WHERE id=?", (identity["id"],)
            )
            db.execute(
                "DELETE FROM pairings WHERE service=? AND subject=?",
                (identity["service"], identity["subject"]),
            )
        return {"ok": True}

    @app.post("/api/native-devices")
    def native_device(body: Device, identity=Depends(paired_device)):
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            store.active_device(db, identity["id"])
            db.execute(
                "UPDATE paired_devices SET push_token=? WHERE id=? AND revoked=0",
                (body.token, identity["id"]),
            )
        return {"ok": True}

    @app.post("/v1/requests", status_code=201)
    def create(body: ActionRequest, background: BackgroundTasks, name=Depends(service)):
        if body.subject not in settings.services[name]["subjects"]:
            raise HTTPException(403, "Service is not allowed to request approval from this subject")
        value, created = store.create(name, body)
        if created:
            background.add_task(notify, store, settings, name, body.subject)
        return {**value, "approval_url": settings.public_url + "/?request=" + value["id"]}

    @app.get("/v1/requests/{rid}")
    def status(rid: str, name=Depends(service)):
        return store.get(rid, name)

    @app.post("/v1/requests/{rid}/claim")
    def claim(rid: str, body: Claim, name=Depends(service)):
        return store.claim(rid, name, body.digest, settings.services[name]["subjects"])

    @app.post("/v1/requests/{rid}/result")
    def result(rid: str, body: Result, name=Depends(service)):
        return store.result(rid, name, body)

    @app.post("/v1/requests/{rid}/cancel")
    def cancel(rid: str, name=Depends(service)):
        return store.cancel(rid, name)

    @app.post("/api/demo/request")
    def demo_request(identity=Depends(paired_device)):
        if not settings.demo:
            raise HTTPException(404)
        value, _ = store.create(
            identity["service"],
            ActionRequest(
                subject=identity["subject"],
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
