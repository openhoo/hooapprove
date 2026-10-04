import logging

import httpx

log = logging.getLogger(__name__)


def notify(store, settings, service, subject):
    # Lock-screen notifications contain no details or approval capability.
    message = {"title": "HooApprove", "body": "Eine Aktion wartet auf deine Entscheidung."}
    with store.connection() as db:
        devices = db.execute(
            "SELECT DISTINCT push_token AS token FROM paired_devices WHERE service=? AND subject=? AND revoked=0 AND push_token IS NOT NULL",
            (service, subject),
        ).fetchall()
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
                    db.execute(
                        "UPDATE paired_devices SET push_token=NULL WHERE push_token=?",
                        (row["token"],),
                    )
            elif data.get("status") == "error":
                log.warning("Native push rejected by delivery provider")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            log.warning("Native push delivery failed")
