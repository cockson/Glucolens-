import json
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.gpt.facts import build_facts_panel
from app.gpt.prompts import ASSISTANTS, PROMPT_VERSION


MODEL = settings.OPENAI_MODEL
MAX_TOKENS = settings.GPT_MAX_OUTPUT_TOKENS
TIMEOUT = settings.GPT_TIMEOUT_SECONDS
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")
    _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def call_gpt_assistant(assistant_key: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assistant = ASSISTANTS.get(assistant_key)
    if assistant is None:
        raise ValueError(f"Unknown assistant: {assistant_key}")

    facts = build_facts_panel(payload["fusion_payload"])
    if payload.get("prior_summaries"):
        facts["prior_summaries"] = payload["prior_summaries"]
    if assistant_key == "clinical_documentation":
        facts["doc_type"] = payload.get("doc_type")
        facts["referral_target"] = payload.get("referral_target")

    client = _get_client()
    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": assistant["system"]},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=2)},
        ],
        max_output_tokens=MAX_TOKENS,
        timeout=TIMEOUT,
    )

    text = ""
    for item in resp.output:
        if item.type != "message":
            continue
        for content in item.content:
            if content.type == "output_text":
                text += content.text

    meta = {
        "assistant_key": assistant_key,
        "assistant_name": assistant["name"],
        "openai_response_id": getattr(resp, "id", None),
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "facts_summary": {
            "prediction_id": facts.get("prediction_id"),
            "final_label": (facts.get("summary") or {}).get("final_label"),
        },
    }
    return text.strip(), meta
