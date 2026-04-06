from fastapi import APIRouter, Depends, HTTPException

from app.api.deps_billing import require_active_subscription
from app.gpt.prompts import ASSISTANTS, PROMPT_VERSION
from app.gpt.schemas import GPTAssistantRequest, GPTResponse
from app.gpt.service import MODEL, call_gpt_assistant


router = APIRouter(prefix="/gpt", tags=["gpt"])


def _run(assistant_key: str, payload: GPTAssistantRequest) -> GPTResponse:
    try:
        content, meta = call_gpt_assistant(assistant_key, payload.model_dump())
        return GPTResponse(
            assistant_key=assistant_key,
            assistant_name=ASSISTANTS[assistant_key]["name"],
            prompt_version=PROMPT_VERSION,
            model=MODEL,
            content=content,
            meta=meta,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assistants")
def list_assistants(user=Depends(require_active_subscription)):
    return {
        "assistants": [
            {"key": key, "name": value["name"]}
            for key, value in ASSISTANTS.items()
        ]
    }


@router.post("/clinical-decision-support", response_model=GPTResponse)
def clinical_decision_support(
    payload: GPTAssistantRequest,
    user=Depends(require_active_subscription),
):
    return _run("clinical_decision_support", payload)


@router.post("/patient-education", response_model=GPTResponse)
def patient_education(
    payload: GPTAssistantRequest,
    user=Depends(require_active_subscription),
):
    return _run("patient_education_lifestyle", payload)


@router.post("/explainability-trust", response_model=GPTResponse)
def explainability_trust(
    payload: GPTAssistantRequest,
    user=Depends(require_active_subscription),
):
    return _run("explainability_trust", payload)


@router.post("/clinical-documentation", response_model=GPTResponse)
def clinical_documentation(
    payload: GPTAssistantRequest,
    user=Depends(require_active_subscription),
):
    return _run("clinical_documentation", payload)
