import httpx
import pytest
from test_service import TOKEN, approve

from examples.rewe_adapter import GuardedCheckout
from hooapprove.client import ApprovalClient


class FakeRewe:
    def __init__(self):
        self.orders = {}
        self.total = 1200

    def checkout_snapshot(self, subject):
        return {
            "cart_id": "cart-1",
            "cart_version": 1,
            "items": [{"name": "Brot", "quantity": 2}],
            "total_minor": self.total,
            "currency": "EUR",
            "address": "Beispielstraße 12",
            "delivery_slot": "18–20 Uhr",
            "payment_method_id": "card-1",
            "payment_label": "Visa • 4242",
        }

    def place_exact_order(self, payload, execution_id):
        if payload["total_minor"] != self.total:
            raise ValueError("Upstream snapshot changed")
        self.orders.setdefault(execution_id, dict(payload))
        return "order-" + execution_id


def adapter(client):
    rewe = FakeRewe()
    return rewe, GuardedCheckout(
        rewe, ApprovalClient("http://testserver", TOKEN, "rewe", http=client)
    )


def test_guarded_checkout_saved_order_exactly_once(client):
    rewe, checkout = adapter(client)
    pending = checkout.prepare("demo-human")
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert not rewe.orders
    value = client.app.state.store.get(pending["request_id"], "rewe")
    approve(client, value)
    reference = checkout.place("demo-human", pending["request_id"])
    assert reference.startswith("order-")
    assert len(rewe.orders) == 1
    assert next(iter(rewe.orders.values()))["total_minor"] == 1200
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert len(rewe.orders) == 1


def test_changed_rewe_price_blocks_order(client):
    rewe, checkout = adapter(client)
    pending = checkout.prepare("demo-human")
    approve(client, client.app.state.store.get(pending["request_id"], "rewe"))
    rewe.total = 1400
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert not rewe.orders


def test_timeout_after_upstream_mutation_never_repeats(client):
    rewe, checkout = adapter(client)
    original = rewe.place_exact_order

    def times_out(payload, execution_id):
        original(payload, execution_id)
        raise TimeoutError("Response lost after upstream saved the order")

    rewe.place_exact_order = times_out
    pending = checkout.prepare("demo-human")
    approve(client, client.app.state.store.get(pending["request_id"], "rewe"))
    with pytest.raises(TimeoutError):
        checkout.place("demo-human", pending["request_id"])
    assert len(rewe.orders) == 1
    assert client.app.state.store.get(pending["request_id"], "rewe")["status"] == "uncertain"
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert len(rewe.orders) == 1
