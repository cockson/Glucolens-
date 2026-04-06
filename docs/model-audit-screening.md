# GlucoLens Screening Model Audit

As of the current artifact set, retain `fusion_logreg_v3` as the primary screening model and `tabular_rf_cal_sigmoid_smote_1` as the fallback/core model.

## Retain

- `fusion_logreg_v3`
  - Best operational fit for screening because it can use retina, skin, and genomics when present, but still works when only tabular data is available.
- `tabular_rf_cal_sigmoid_smote_1`
  - Best aligned with first-contact screening and longitudinal 3/6/12-month scheduling.
- `retina_resnet18_tempcal`
  - Retain as an adjunct only.
- `skin_resnet18_tempcal`
  - Retain as an adjunct with caution.

## Do Not Retain As Primary Screening Model

- `genomics_logreg`
  - Keep for research or optional enrichment only. The current artifact is too imbalanced and mixes non-genomic clinical variables with SNP features.

## Screening Recommendation

- High-risk / positive fusion result: 3-month track
- Intermediate / near-threshold or prediabetic pattern: 6-month track
- Low-risk negative result: 12-month track

## Key Governance Gaps

- The tabular and fusion headline metrics look unrealistically high and still need external real-world validation.
- Retina validation is small and label-skewed.
- Skin is missing a dedicated `performance.json` artifact.
- Genomics should not drive screening cadence in its current form.
