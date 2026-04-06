from typing import Any

from pydantic import BaseModel, Field


class GPTAssistantRequest(BaseModel):
    language: str = "en"
    fusion_payload: dict[str, Any]
    prior_summaries: list[dict[str, Any]] | None = None
    doc_type: str = "soap"
    referral_target: str | None = None
    patient_id: str | None = None
    encounter_id: str | None = None


class GPTResponse(BaseModel):
    assistant_key: str
    assistant_name: str
    prompt_version: str
    model: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)
