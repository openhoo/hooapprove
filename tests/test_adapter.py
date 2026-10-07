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
    prepared_again = checkout.prepare("demo-human")
    assert prepared_again["request_id"] == pending["request_id"]
    assert prepared_again["status"] == "completed"
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
    prepared_again = checkout.prepare("demo-human")
    assert prepared_again["request_id"] == pending["request_id"]
    assert prepared_again["status"] == "uncertain"
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert len(rewe.orders) == 1


def test_changed_checkout_gets_fresh_approval_without_cart_revision(client):
    rewe, checkout = adapter(client)
    first = checkout.prepare("demo-human")
    assert checkout.prepare("demo-human")["request_id"] == first["request_id"]
    rewe.total = 1400
    second = checkout.prepare("demo-human")
    assert second["request_id"] != first["request_id"]
    assert not rewe.orders


def test_deliberate_new_attempt_can_prepare_unchanged_rejected_action(client):
    rewe, checkout = adapter(client)
    first = checkout.prepare("demo-human", attempt_id="workflow-1")
    value = client.app.state.store.get(first["request_id"], "rewe")
    response = client.post(
        f"/api/requests/{value['id']}/decision",
        json={"decision": "reject", "digest": value["digest"]},
    )
    assert response.status_code == 200
    retry = checkout.prepare("demo-human", attempt_id="workflow-1")
    assert retry["request_id"] == first["request_id"]
    assert retry["status"] == "rejected"
    second = checkout.prepare("demo-human", attempt_id="workflow-2")
    assert second["request_id"] != first["request_id"]
    assert second["status"] == "approval_required"
    assert not rewe.orders


def test_claim_response_lost_never_calls_upstream(client, monkeypatch):
    rewe, checkout = adapter(client)
    pending = checkout.prepare("demo-human")
    approve(client, client.app.state.store.get(pending["request_id"], "rewe"))
    original = client.post

    def lose_claim_response(url, **kwargs):
        response = original(url, **kwargs)
        if url.endswith("/claim"):
            raise httpx.ReadTimeout("Claim response lost")
        return response

    monkeypatch.setattr(client, "post", lose_claim_response)
    with pytest.raises(httpx.ReadTimeout):
        checkout.place("demo-human", pending["request_id"])
    assert not rewe.orders
    assert client.app.state.store.get(pending["request_id"], "rewe")["status"] == "executing"
    monkeypatch.setattr(client, "post", original)
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert not rewe.orders


def test_failed_uncertain_report_preserves_original_upstream_error(client, monkeypatch):
    rewe, checkout = adapter(client)
    pending = checkout.prepare("demo-human")
    approve(client, client.app.state.store.get(pending["request_id"], "rewe"))
    original = rewe.place_exact_order

    def timeout(payload, execution_id):
        original(payload, execution_id)
        raise TimeoutError("Upstream response lost")

    def invalid_report(*args):
        raise ValueError("Malformed result response")

    rewe.place_exact_order = timeout
    monkeypatch.setattr(checkout.approvals, "report", invalid_report)
    with pytest.raises(TimeoutError, match="Upstream response lost"):
        checkout.place("demo-human", pending["request_id"])
    assert len(rewe.orders) == 1
    assert client.app.state.store.get(pending["request_id"], "rewe")["status"] == "executing"


def test_completed_operation_report_failure_is_explicit_and_not_retried(client, monkeypatch):
    from hooapprove.client import ExecutionResultReportingError

    rewe, checkout = adapter(client)
    pending = checkout.prepare("demo-human")
    approve(client, client.app.state.store.get(pending["request_id"], "rewe"))

    def timeout_report(*args):
        raise httpx.ReadTimeout("Result response lost")

    monkeypatch.setattr(checkout.approvals, "report", timeout_report)
    with pytest.raises(ExecutionResultReportingError, match="Do not repeat") as error:
        checkout.place("demo-human", pending["request_id"])
    assert error.value.request_id == pending["request_id"]
    assert error.value.reference == "order-" + error.value.execution_id
    assert isinstance(error.value.__cause__, httpx.ReadTimeout)
    assert len(rewe.orders) == 1
    assert client.app.state.store.get(pending["request_id"], "rewe")["status"] == "executing"
    with pytest.raises(httpx.HTTPStatusError):
        checkout.place("demo-human", pending["request_id"])
    assert len(rewe.orders) == 1
