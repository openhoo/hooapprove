"""Embed this client in the trusted executor, never give its credentials to the model."""

import httpx

from .models import ActionRequest, action_digest


class ApprovalClient:
    def __init__(self, url, token, service, *, http=None):
        self.http = http or httpx.Client(base_url=url, timeout=15)
        self.headers = {"Authorization": "Bearer " + token}
        self.service = service

    def request(self, action: ActionRequest):
        response = self.http.post("/v1/requests", json=action.model_dump(), headers=self.headers)
        response.raise_for_status()
        return response.json()

    def status(self, request_id):
        response = self.http.get("/v1/requests/" + request_id, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def execute(self, request_id, current_action: ActionRequest, operation):
        """Re-read source state before calling; operation must use immutable payload and execution_id.

        No retries after claiming. The external API must enforce its own idempotency/version fence.
        A crash/timeout between claim and execution is intentionally unavailable for automatic retry.
        """
        digest = action_digest(self.service, current_action)
        response = self.http.post(
            f"/v1/requests/{request_id}/claim", json={"digest": digest}, headers=self.headers
        )
        response.raise_for_status()
        receipt = response.json()
        try:
            reference = operation(receipt["payload"], receipt["execution_id"])
        except Exception:
            # Even an apparent timeout can mean the external service already placed the order.
            try:
                self.report(request_id, receipt["execution_id"], "uncertain")
            except httpx.HTTPError:
                pass  # Remains 'executing': also fenced against another execution.
            raise
        self.report(request_id, receipt["execution_id"], "completed", str(reference))
        return reference

    def report(self, request_id, execution_id, outcome, reference=""):
        response = self.http.post(
            f"/v1/requests/{request_id}/result",
            headers=self.headers,
            json={"execution_id": execution_id, "outcome": outcome, "reference": reference},
        )
        response.raise_for_status()
        return response.json()
