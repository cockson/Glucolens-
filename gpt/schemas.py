from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal

Lang = Literal["en", "fr"]

FinalLabel = Literal["screen_positive_refer", "screen_negative", "retake_image", "insufficient_data"]
FusionReason = Literal[
    "fusion",
    "fallback_tabular_only",
    "near_threshold_conservative",
    "retina_quality_failed",
    "skin_quality_failed",
    "genomics_quality_failed",
    "missing_tabular",
]

class ThresholdMeta(BaseModel):
    policy_id: Optional[str] = None
    scope: Literal["facility", "country", "default"] = "default"

class QualityGate(BaseModel):
    passed: bool = True
    reason: str = "ok"
    metrics: Dict[str, Any] = Field(default_factory=dict)

class ExplainabilityGradCAM(BaseModel):
    method: Literal["gradcam"] = "gradcam"
    overlay_png_base64: Optional[str] = None  # do NOT send to GPT; store/display in UI only

class TabularOut(BaseModel):
    model_name: str
    model_version: str
    predicted_label: str
    probabilities: Dict[str, float] = Field(default_factory=dict)

class RetinaOut(BaseModel):
    model_name: str
    model_version: str
    predicted_label: Literal["t2d", "not_diabetic", "retake_image"]
    probabilities: Dict[str, float] = Field(default_factory=dict)
    explainability: Optional[ExplainabilityGradCAM] = None
    quality_gate: QualityGate = Field(default_factory=QualityGate)

class SkinOut(BaseModel):
    model_name: str
    model_version: str
    predicted_label: Literal["positive", "negative", "retake_image"]
    probabilities: Dict[str, float] = Field(default_factory=dict)
    explainability: Optional[ExplainabilityGradCAM] = None
    quality_gate: QualityGate = Field(default_factory=QualityGate)

class GenomicsExplainability(BaseModel):
    top_coefficients: List[Dict[str, Any]] = Field(default_factory=list)

class GenomicsOut(BaseModel):
    model: str = "genomics"
    probability: float = 0.0
    predicted_label: Literal["positive", "negative"]
    explainability: Optional[GenomicsExplainability] = None

class FusionOut(BaseModel):
    final_label: FinalLabel
    final_proba: float = Field(0.0, ge=0.0, le=1.0)
    reason: FusionReason

class FusionPayload(BaseModel):
    fusion: FusionOut
    threshold_used: float = 0.5
    threshold_meta: ThresholdMeta = Field(default_factory=ThresholdMeta)
    tabular: Optional[TabularOut] = None
    retina: Optional[RetinaOut] = None
    skin: Optional[SkinOut] = None
    genomics: Optional[GenomicsOut] = None
    prediction_id: str  # uuid string


GPTReportType = Literal[
    "clinical_insight",
    "patient_explanation",
    "explainability",
    "followup",
    "documentation",
]

class GPTRequest(BaseModel):
    report_type: GPTReportType
    language: Lang = "en"

    # Direct fusion output
    fusion_payload: FusionPayload

    # Optional: follow-up history (safe summaries only)
    prior_summaries: Optional[List[Dict[str, Any]]] = None

    # Optional: document preferences
    doc_type: Optional[Literal["soap", "referral_letter", "screening_report"]] = "soap"
    referral_target: Optional[str] = None

    # Linking (audit)
    patient_id: Optional[str] = None
    encounter_id: Optional[str] = None


class GPTResponse(BaseModel):
    report_type: GPTReportType
    prompt_version: str
    model: str
    content: str
    meta: Dict[str, Any] = {}