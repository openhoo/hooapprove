import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Detail(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)


class ActionRequest(StrictModel):
    subject: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_.:-]+$")
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=2000)
    details: list[Detail] = Field(min_length=1, max_length=200)
    payload: dict[str, JsonValue]
    idempotency_key: str = Field(min_length=8, max_length=160)
    expires_in: int = Field(default=600, ge=30, le=1800)

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, payload):
        if len(canonical(payload).encode()) > 64_000:
            raise ValueError("Payload too large")
        return payload


class Decision(StrictModel):
    decision: Literal["approve", "reject"]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Claim(StrictModel):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Result(StrictModel):
    execution_id: str = Field(min_length=1, max_length=100)
    outcome: Literal["completed", "failed", "uncertain"]
    reference: str = Field(default="", max_length=200)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def action_digest(service, request):
    # The visible human contract and executable payload are one immutable envelope.
    value = request.model_dump(exclude={"idempotency_key", "expires_in"})
    return hashlib.sha256(canonical({"service": service, **value}).encode()).hexdigest()
