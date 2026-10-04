import json
import logging

import httpx
from pywebpush import WebPushException, webpush

log = logging.getLogger(__name__)


def notify(store, settings, subject):
    # Lock-screen notifications deliberately contain no action details or approval capability.
    message = {"title": "HooApprove", "body": "Eine Aktion wartet auf deine Entscheidung."}
    with store.connection() as db:
        subscriptions = db.execute(
            "SELECT * FROM subscriptions WHERE subject=?", (subject,)
        ).fetchall()
        devices = db.execute(
            "SELECT token FROM native_devices WHERE subject=?", (subject,)
        ).fetchall()
    if settings.vapid_private_key:
        for row in subscriptions:
            try:
                webpush(
                    json.loads(row["value"]),
                    json.dumps(message),
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_contact},
                    timeout=10,
                )
            except WebPushException as error:
                if error.response is not None and error.response.status_code in (404, 410):
                    with store.connection() as db:
                        db.execute("DELETE FROM subscriptions WHERE endpoint=?", (row["endpoint"],))
                log.warning("Web push delivery failed")
            except (ValueError, OSError, TypeError):
                log.warning("Web push configuration unavailable")
    for row in devices:
        try:
            response = httpx.post(
                "https://exp.host/--/api/v2/push/send",
                json={
                    "to": row["token"],
                    "sound": "default",
                    **message,
                    "data": {"screen": "inbox"},
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            if data.get("details", {}).get("error") == "DeviceNotRegistered":
                with store.connection() as db:
                    db.execute("DELETE FROM native_devices WHERE token=?", (row["token"],))
            elif data.get("status") == "error":
                log.warning("Native push rejected by delivery provider")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            log.warning("Native push delivery failed")
