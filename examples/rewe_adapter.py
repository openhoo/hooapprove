"""Adapter contract for REWE. This is an example, not a connection to the existing REWE MCP.

The authenticated MCP session resolves subject; never accept an arbitrary subject from a tool arg.
Keep checkout credentials behind this adapter. No agent-accessible unguarded checkout endpoint.
"""

import hashlib

from hooapprove.client import ApprovalClient
from hooapprove.models import ActionRequest, action_digest


class GuardedCheckout:
    def __init__(self, rewe, approvals: ApprovalClient):
        self.rewe, self.approvals = rewe, approvals

    def snapshot(self, subject):
        # The source adapter must obtain authoritative prices, version and delivery details.
        order = self.rewe.checkout_snapshot(subject)
        payload = {
            key: order[key]
            for key in (
                "cart_id",
                "cart_version",
                "items",
                "total_minor",
                "currency",
                "address",
                "delivery_slot",
                "payment_method_id",
            )
        }
        action = ActionRequest(
            subject=subject,
            action="order.place",
            title="Deinen Einkauf bestellen",
            summary="Prüfe Warenkorb, Gesamtbetrag und Lieferung vor der Bestellung.",
            details=[
                {
                    "label": "Gesamtbetrag",
                    "value": f"{order['total_minor'] / 100:.2f} {order['currency']} inklusive Gebühren",
                },
                {
                    "label": "Warenkorb",
                    "value": "; ".join(f"{x['quantity']} × {x['name']}" for x in order["items"]),
                },
                {"label": "Lieferadresse", "value": order["address"]},
                {"label": "Lieferung", "value": order["delivery_slot"]},
                {"label": "Zahlung", "value": order["payment_label"]},
            ],
            payload=payload,
            idempotency_key="checkout-snapshot",
            expires_in=300,
        )
        # Prices, address or payment labels can change without a new cart revision.
        # The whole approval envelope therefore identifies this preparation attempt.
        action.idempotency_key = "order-" + action_digest(self.approvals.service, action)
        return action

    def prepare(self, authenticated_subject, *, attempt_id=None):
        """Prepare once per trusted workflow attempt, with stable IDs across retries.

        After rejection, cancellation or expiry, a deliberate new preparation can use
        a fresh attempt_id. An uncertain/executing/completed order must be reconciled
        upstream before starting another attempt; never generate retry IDs automatically.
        """
        action = self.snapshot(authenticated_subject)
        if attempt_id is not None:
            if not isinstance(attempt_id, str) or not 1 <= len(attempt_id) <= 200:
                raise ValueError(
                    "Preparation attempt ID must be a nonempty string of at most 200 characters"
                )
            action.idempotency_key = (
                "order-"
                + hashlib.sha256(f"{action.idempotency_key}\n{attempt_id}".encode()).hexdigest()
            )
        value = self.approvals.request(action)
        return {
            "status": "approval_required" if value["status"] == "pending" else value["status"],
            "request_id": value["id"],
            "approval_url": value["approval_url"],
        }

    def place(self, authenticated_subject, request_id):
        # Re-read immediately before claim. Changed price/address/cart invalidates this request.
        current = self.snapshot(authenticated_subject)
        return self.approvals.execute(request_id, current, self.rewe.place_exact_order)

    # place_exact_order(payload, execution_id) must enforce the snapshot/version atomically,
    # and use execution_id as the upstream idempotency key. Do not read a mutable cart again.
