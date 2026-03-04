import os
import json
from typing import Dict, Tuple

from openai import OpenAI

from app.gpt.prompts import (
    PROMPT_VERSION,
    clinician_system,
    patient_system,
    explainability_system,
    followup_system,
    documentation_system,
)
from app.gpt.facts import build_facts_panel
from app.gpt.schemas import GPTRequest

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2-mini")
MAX_TOKENS = int(os.getenv("GPT_MAX_OUTPUT_TOKENS", "650"))
TIMEOUT = int(os.getenv("GPT_TIMEOUT_SECONDS", "30"))

def _system_prompt(req: GPTRequest) -> str:
    lang = req.language
    if req.report_type == "clinical_insight":
        return clinician_system(lang)
    if req.report_type == "patient_explanation":
        return patient_system(lang)
    if req.report_type == "explainability":
        return explainability_system(lang)
    if req.report_type == "followup":
        return followup_system(lang)
    if req.report_type == "documentation":
        return documentation_system(lang)
    raise ValueError(f"Unknown report_type: {req.report_type}")

def call_gpt(req: GPTRequest) -> Tuple[str, Dict, Dict]:
    # Build safe facts panel
    facts = build_facts_panel(req.fusion_payload)

    # Add optional follow-up context (safe summaries only)
    if req.prior_summaries:
        facts["prior_summaries"] = req.prior_summaries

    # Documentation preferences
    if req.report_type == "documentation":
        facts["doc_type"] = req.doc_type
        facts["referral_target"] = req.referral_target

    system = _system_prompt(req)
    user = json.dumps(facts, ensure_ascii=False, indent=2)

    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_output_tokens=MAX_TOKENS,
        timeout=TIMEOUT,
    )

    text = ""
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    text += c.text

    meta = {
        "openai_response_id": getattr(resp, "id", None),
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "language": req.language,
    }

    # Return also the input facts for auditing
    return text.strip(), meta, facts