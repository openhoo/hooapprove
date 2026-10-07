"""Account-free device pairing and Ed25519 request proofs."""

import hashlib
import secrets
import sqlite3
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException, Request
from nacl.bindings import (
    crypto_core_ed25519_add,
    crypto_core_ed25519_is_valid_point,
    crypto_scalarmult_ed25519_noclamp,
)
from nacl.exceptions import CryptoError
from pydantic import Field

from .models import StrictModel

# See https://doc.libsodium.org/advanced/point-arithmetic. Versions <=1.0.20
# may admit mixed-order points in is_valid_point; the documented subgroup test
# uses (L-1)*P + P == identity. All curve operations stay in libsodium.
ED25519_L_MINUS_ONE = (2**252 + 27742317777372353535851937790883648492).to_bytes(32, "little")
ED25519_IDENTITY = b"\x01" + bytes(31)


class PairingRequest(StrictModel):
    subject: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=100)


class Ticket(StrictModel):
    ticket: str = Field(min_length=32, max_length=128)


class Enrollment(Ticket):
    device_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    public_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def pairing_message(ticket, device_id, public_key):
    return f"hooapprove.pair.v1\n{token_hash(ticket)}\n{device_id}\n{public_key}".encode()


def device_message(device_id, method, path, timestamp, nonce, body):
    digest = hashlib.sha256(body).hexdigest()
    return f"hooapprove.device.v1\n{device_id}\n{method}\n{path}\n{timestamp}\n{nonce}\n{digest}".encode()


def verify(public_key, signature, message):
    try:
        key = bytes.fromhex(public_key)
        if len(key) != 32 or not crypto_core_ed25519_is_valid_point(key):
            raise ValueError("Unsafe device public key")
        multiple = crypto_scalarmult_ed25519_noclamp(ED25519_L_MINUS_ONE, key)
        if crypto_core_ed25519_add(multiple, key) != ED25519_IDENTITY:
            raise ValueError("Unsafe device public key")
        Ed25519PublicKey.from_public_bytes(key).verify(bytes.fromhex(signature), message)
    except (ValueError, InvalidSignature, CryptoError):
        raise HTTPException(401, "Invalid device proof") from None


def issue(store, service, subject, label):
    ticket = secrets.token_urlsafe(48)
    expires = time.time() + 300
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM paired_devices WHERE service=? AND subject=? AND revoked=0",
            (service, subject),
        ).fetchone():
            raise HTTPException(409, "Recipient already paired; unlink the existing device first")
        db.execute("DELETE FROM pairings WHERE expires<=?", (time.time(),))
        db.execute(
            "INSERT INTO pairings VALUES(?,?,?,?,?)",
            (token_hash(ticket), service, subject, label, expires),
        )
    return {"ticket": ticket, "expires": expires}


def preview(store, ticket):
    with store.connection() as db:
        row = db.execute(
            "SELECT * FROM pairings WHERE hash=? AND expires>?", (token_hash(ticket), time.time())
        ).fetchone()
        if not row:
            raise HTTPException(410, "Pairing expired or already used")
        return {key: row[key] for key in ("service", "label", "expires")}


def enroll(store, body):
    verify(
        body.public_key,
        body.signature,
        pairing_message(body.ticket, body.device_id, body.public_key),
    )
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM pairings WHERE hash=? AND expires>?",
            (token_hash(body.ticket), time.time()),
        ).fetchone()
        if not row:
            raise HTTPException(410, "Pairing expired or already used")
        try:
            db.execute(
                "INSERT INTO paired_devices(id,service,subject,label,public_key,created) VALUES(?,?,?,?,?,?)",
                (
                    body.device_id,
                    row["service"],
                    row["subject"],
                    row["label"],
                    body.public_key,
                    time.time(),
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Device or recipient is already paired") from None
        # Invalidate ALL outstanding bootstrap tickets for this recipient.
        db.execute(
            "DELETE FROM pairings WHERE service=? AND subject=?", (row["service"], row["subject"])
        )
        return {"device_id": body.device_id, "service": row["service"], "label": row["label"]}


async def paired_device(request: Request):
    store = request.app.state.store
    device_id = request.headers.get("x-device-id", "")
    timestamp = request.headers.get("x-device-time", "")
    nonce = request.headers.get("x-device-nonce", "")
    signature = request.headers.get("x-device-signature", "")
    try:
        fresh = abs(time.time() - int(timestamp)) <= 60
        valid_nonce = len(nonce) == 32 and len(bytes.fromhex(nonce)) == 16
    except (ValueError, OverflowError):
        fresh = valid_nonce = False
    if not fresh or not valid_nonce or request.url.query:
        raise HTTPException(401, "Invalid or stale device proof")
    body = await request.body()
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = store.active_device(db, device_id)
        verify(
            row["public_key"],
            signature,
            device_message(device_id, request.method, request.url.path, timestamp, nonce, body),
        )
        db.execute("DELETE FROM device_nonces WHERE expires<=?", (time.time(),))
        try:
            db.execute(
                "INSERT INTO device_nonces VALUES(?,?,?)", (device_id, nonce, time.time() + 120)
            )
        except sqlite3.IntegrityError:
            raise HTTPException(401, "Device proof already used") from None
        return dict(row)
