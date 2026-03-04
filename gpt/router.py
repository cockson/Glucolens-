from fastapi import APIRouter, HTTPException
from app.gpt.schemas import GPTInput, GPTResponse
from app.gpt.service import call_gpt, MODEL
from app.gpt.prompts import PROMPT_VERSION

router = APIRouter(prefix="/gpt", tags=["gpt"])

def _run(report_type: str, payload: GPTInput) -> GPTResponse:
    try:
        content, meta = call_gpt(report_type, payload.model_dump())
        return GPTResponse(
            report_type=report_type,
            prompt_version=PROMPT_VERSION,
            model=MODEL,
            content=content,
            meta=meta,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/clinical-insight", response_model=GPTResponse)
def clinical_insight(payload: GPTInput):
    return _run("clinical_insight", payload)

@router.post("/patient-explanation", response_model=GPTResponse)
def patient_explanation(payload: GPTInput):
    return _run("patient_explanation", payload)

@router.post("/explainability", response_model=GPTResponse)
def explainability(payload: GPTInput):
    return _run("explainability", payload)

@router.post("/followup", response_model=GPTResponse)
def followup(payload: GPTInput):
    return _run("followup", payload)

@router.post("/documentation", response_model=GPTResponse)
def documentation(payload: GPTInput):
    return _run("documentation", payload)