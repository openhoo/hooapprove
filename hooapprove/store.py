import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from .models import action_digest, canonical


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                DROP TABLE IF EXISTS mobile_sessions;
                DROP TABLE IF EXISTS mobile_tickets;
                DROP TABLE IF EXISTS native_devices;
                DROP TABLE IF EXISTS subscriptions;
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, service TEXT NOT NULL, subject TEXT NOT NULL,
                    idem TEXT NOT NULL, digest TEXT NOT NULL, envelope TEXT NOT NULL,
                    status TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
                    decided REAL, execution_id TEXT, reference TEXT,
                    UNIQUE(service, subject, idem)
                );
                CREATE INDEX IF NOT EXISTS requests_subject ON requests(subject, created);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL, actor TEXT NOT NULL,
                    event TEXT NOT NULL, occurred REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pairings (
                    hash TEXT PRIMARY KEY, service TEXT NOT NULL, subject TEXT NOT NULL,
                    label TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paired_devices (
                    id TEXT PRIMARY KEY, service TEXT NOT NULL, subject TEXT NOT NULL,
                    label TEXT NOT NULL, public_key TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                    push_token TEXT, created REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS paired_recipient
                    ON paired_devices(service,subject) WHERE revoked=0;
                CREATE TABLE IF NOT EXISTS device_nonces (
                    device_id TEXT NOT NULL, nonce TEXT NOT NULL, expires REAL NOT NULL,
                    PRIMARY KEY(device_id,nonce)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, rid, actor, event):
        db.execute(
            "INSERT INTO events(request_id,actor,event,occurred) VALUES(?,?,?,?)",
            (rid, actor, event, time.time()),
        )

    def expire(self, db):
        rows = db.execute(
            "SELECT id FROM requests WHERE status IN ('pending','approved') AND expires<=?",
            (time.time(),),
        ).fetchall()
        for row in rows:
            db.execute("UPDATE requests SET status='expired' WHERE id=?", (row["id"],))
            self.event(db, row["id"], "system", "expired")

    def public(self, row, include_payload=False):
        value = json.loads(row["envelope"])
        if not include_payload:
            value.pop("payload")
        value.pop("idempotency_key")
        value.pop("expires_in")
        return {
            **value,
            **{
                key: row[key]
                for key in (
                    "id",
                    "service",
                    "digest",
                    "status",
                    "created",
                    "expires",
                    "decided",
                    "execution_id",
                    "reference",
                )
            },
        }

    def create(self, service, request):
        digest = action_digest(service, request)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db)
            old = db.execute(
                "SELECT * FROM requests WHERE service=? AND subject=? AND idem=?",
                (service, request.subject, request.idempotency_key),
            ).fetchone()
            if old:
                if old["digest"] != digest:
                    raise HTTPException(409, "Idempotency key belongs to a different action")
                return self.public(old), False
            rid, now = str(uuid.uuid4()), time.time()
            db.execute(
                """INSERT INTO requests
                (id,service,subject,idem,digest,envelope,status,created,expires)
                VALUES(?,?,?,?,?,?,'pending',?,?)""",
                (
                    rid,
                    service,
                    request.subject,
                    request.idempotency_key,
                    digest,
                    canonical(request.model_dump()),
                    now,
                    now + request.expires_in,
                ),
            )
            self.event(db, rid, service, "requested")
            return self.public(
                db.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
            ), True

    def owned(self, db, rid, field, owner):
        row = db.execute(
            f"SELECT * FROM requests WHERE id=? AND {field}=?", (rid, owner)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Request not found")
        return row

    def list_for(self, subject, service, device_id):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db)
            self.recipient_device(db, device_id, subject, service)
            rows = db.execute(
                "SELECT * FROM requests WHERE subject=? AND service=? "
                "ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created DESC LIMIT 100",
                (subject, service),
            ).fetchall()
            return [self.public(row) for row in rows]

    def get(self, rid, service):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db)
            return self.public(self.owned(db, rid, "service", service))

    def decide(self, rid, subject, decision, service, device_id):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.recipient_device(db, device_id, subject, service)
            # Expiry is checked inside the transaction, even if nobody has polled.
            row = self.owned(db, rid, "subject", subject)
            if row["service"] != service:
                raise HTTPException(404, "Request not found")
            if row["digest"] != decision.digest:
                raise HTTPException(409, "Action changed; reload before deciding")
            if row["status"] != "pending" or row["expires"] <= time.time():
                raise HTTPException(409, "Request is no longer pending")
            status = "approved" if decision.decision == "approve" else "rejected"
            db.execute(
                "UPDATE requests SET status=?,decided=? WHERE id=?", (status, time.time(), rid)
            )
            self.event(db, rid, subject, status)
            return self.public(self.owned(db, rid, "subject", subject))

    def claim(self, rid, service, digest, allowed_subjects=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.owned(db, rid, "service", service)
            if allowed_subjects is not None and row["subject"] not in allowed_subjects:
                raise HTTPException(403, "Recipient is not allowed")
            if row["digest"] != digest:
                raise HTTPException(409, "Execution payload differs from approved action")
            if row["status"] != "approved" or row["expires"] <= time.time():
                raise HTTPException(409, "Approval unavailable, expired or already consumed")
            execution_id = str(uuid.uuid4())
            db.execute(
                "UPDATE requests SET status='executing',execution_id=? WHERE id=?",
                (execution_id, rid),
            )
            self.event(db, rid, service, "claimed")
            return self.public(self.owned(db, rid, "service", service), include_payload=True)

    def result(self, rid, service, result):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.owned(db, rid, "service", service)
            if row["execution_id"] != result.execution_id:
                raise HTTPException(409, "Execution identity mismatch")
            if row["status"] == result.outcome and row["reference"] == result.reference:
                return self.public(row)
            if row["status"] != "executing":
                raise HTTPException(409, "Execution has already been finalized")
            db.execute(
                "UPDATE requests SET status=?,reference=? WHERE id=?",
                (result.outcome, result.reference, rid),
            )
            self.event(db, rid, service, result.outcome)
            return self.public(self.owned(db, rid, "service", service))

    def cancel(self, rid, service):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.owned(db, rid, "service", service)
            if row["status"] not in {"pending", "approved"}:
                raise HTTPException(409, "Request cannot be cancelled")
            db.execute("UPDATE requests SET status='cancelled' WHERE id=?", (rid,))
            self.event(db, rid, service, "cancelled")
            return self.public(self.owned(db, rid, "service", service))

    def events(self, rid, subject, service, device_id):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.recipient_device(db, device_id, subject, service)
            if self.owned(db, rid, "subject", subject)["service"] != service:
                raise HTTPException(404, "Request not found")
            return [
                dict(row)
                for row in db.execute(
                    "SELECT event,occurred FROM events WHERE request_id=? ORDER BY sequence", (rid,)
                )
            ]

    def active_device(self, db, device_id):
        row = db.execute(
            "SELECT * FROM paired_devices WHERE id=? AND revoked=0", (device_id,)
        ).fetchone()
        if not row:
            raise HTTPException(401, "Device is not paired")
        return row

    def recipient_device(self, db, device_id, subject, service):
        row = self.active_device(db, device_id)
        if row["subject"] != subject or row["service"] != service:
            raise HTTPException(401, "Device is not paired for this recipient")
        return row
