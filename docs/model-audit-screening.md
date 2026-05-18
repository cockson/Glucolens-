# GlucoLens Screening Model Audit

As of the current artifact set, retain `fusion_logreg_v3` as the primary screening wrapper and `tabular_rf_cal_sigmoid_smote_0` as the fallback/core model.

## Retain

- `fusion_logreg_v3`
  - Current version: `20260518_141508`.
  - Current training data was regenerated from out-of-fold tabular probabilities with diagnostic leakage fields suppressed. Retina, skin, and genomics are unavailable in this regenerated local training file.
  - Current holdout AUROC: `0.956`; Brier: `0.077`; accuracy: `0.887`; F1: `0.833`.
  - Best operational wrapper for screening because it can use retina, skin, and genomics when present, but the current local artifact is effectively tabular-only until real linked modality outcomes are exported.
- `tabular_rf_cal_sigmoid_smote_0`
  - Current version: `20260518_130427`.
  - Current OOF AUROC: `0.888`; Brier: `0.356`; accuracy: `0.730`; F1: `0.729`.
  - Retrained without HbA1c, fasting glucose, or antidiabetic treatment fields.
  - Best aligned with first-contact screening and operational 3/6/12-month scheduling.
- `retina_resnet18_tempcal`
  - Retain as an adjunct only.
- `skin_resnet18_tempcal`
  - Retain as an adjunct with caution.

## Do Not Retain As Primary Screening Model

- `genomics_logreg`
  - Keep for research or optional enrichment only. The current training path now excludes anthropometric and clinical overlap columns; it remains imbalanced and should not drive cadence by itself.

## Screening Recommendation

- High-risk / positive fusion result: 3-month track
- Intermediate / near-threshold or prediabetic pattern: 6-month track
- Low-risk negative result: 12-month track

## Key Governance Gaps

- Fusion no longer uses in-sample served tabular predictions for meta-model training; `fusion_train.csv` is generated from out-of-fold non-leaky tabular probabilities.
- The current fusion artifact is still tabular-only because real linked retina, skin, and genomics outcomes were not available in the local export path.
- Tabular strict audit passed with label-shuffle AUROC `0.511`, but HDL/LDL perfect-bin warnings remain and need review against real clinical data.
- Retina validation is small and label-skewed.
- Skin is missing a dedicated `performance.json` artifact.
- Genomics should not drive screening cadence in its current form.
- The current target is a present-time screening class. 3/6/12-month outputs are follow-up bands, not true horizon-specific event-risk targets, until dated longitudinal outcomes are available.
- Diagnostic tabular fields such as HbA1c and fasting glucose are clinical context/reporting fields and should remain excluded from retrained screening model features to avoid target leakage.
