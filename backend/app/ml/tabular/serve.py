import json
import os
import re
import numpy as np
import pandas as pd
from joblib import load
from app.ml.artifacts import (
    ensure_artifact_file,
    infer_repo_relative_artifact_path,
    is_git_lfs_pointer,
    resolve_artifact_path,
)
from app.services.screening_program import derive_tabular_features
try:
    import shap
except Exception:
    shap = None

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "tabular")
ALT_ART_DIR = os.path.join(REPO_ROOT, "backend", "artifacts", "tabular")
REGISTRY = os.path.join(ART_DIR, "registry.json")

_cached = {
    "model": None,
    "meta": None,
    "explainer": None,
    "feature_cols": None,
    "model_feature_cols": None,
    "numeric_feature_cols": None,
    "classes": None,
    "target_idx": None,
}
EXPLAIN_METHOD = os.getenv("TABULAR_EXPLAIN_METHOD", "occlusion").strip().lower()

def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None

def _sanitize_json(value):
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    return value

def load_registry():
    reg_path = _first_existing([REGISTRY, os.path.join(ALT_ART_DIR, "registry.json")])
    if not reg_path:
        raise FileNotFoundError("Tabular registry.json not found")
    return _read_json(reg_path)["current"]

def _resolve_model_path(path: str) -> str:
    if not path:
        return ""
    return resolve_artifact_path(
        path,
        repo_root=REPO_ROOT,
        project_root=PROJECT_ROOT,
        artifact_dir=ART_DIR,
    )


def _parse_versioned_model_filename(path: str) -> tuple[str | None, str | None]:
    name = os.path.basename(path or "")
    match = re.match(r"^(?P<model_name>.+)_(?P<model_version>\d{8}_\d{6})\.joblib$", name)
    if not match:
        return None, None
    return match.group("model_name"), match.group("model_version")


def _local_model_candidates(model_name: str | None, preferred_path: str | None = None) -> list[str]:
    preferred_norm = os.path.normpath(preferred_path) if preferred_path else None
    buckets: list[list[tuple[tuple[str, float], str]]] = [[], []]
    prefix = f"{model_name}_" if model_name else None

    for base in [ART_DIR, ALT_ART_DIR]:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            if not entry.endswith(".joblib"):
                continue
            full_path = os.path.normpath(os.path.join(base, entry))
            if preferred_norm and full_path == preferred_norm:
                continue
            if not os.path.isfile(full_path) or is_git_lfs_pointer(full_path):
                continue

            _parsed_name, parsed_version = _parse_versioned_model_filename(entry)
            sort_key = (parsed_version or "", os.path.getmtime(full_path))
            if prefix and entry.startswith(prefix):
                buckets[0].append((sort_key, full_path))
            else:
                buckets[1].append((sort_key, full_path))

    ordered: list[str] = []
    seen = set()
    for bucket in buckets:
        for _sort_key, path in sorted(bucket, key=lambda item: item[0], reverse=True):
            if path in seen:
                continue
            seen.add(path)
            ordered.append(path)
    return ordered


def _load_model_with_fallback(meta: dict) -> tuple[object, str]:
    model_path = _resolve_model_path(meta.get("model_path", ""))
    repo_relative_path = infer_repo_relative_artifact_path(meta.get("model_path", ""))
    candidates: list[str] = []
    errors: list[str] = []

    if model_path and os.path.isfile(model_path) and not is_git_lfs_pointer(model_path):
        candidates.append(model_path)
    candidates.extend(_local_model_candidates(meta.get("model_name"), preferred_path=model_path))

    if model_path and model_path not in candidates:
        try:
            hydrated_path = ensure_artifact_file(
                model_path,
                repo_relative_path=repo_relative_path,
            )
            candidates.append(hydrated_path)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    seen = set()
    for candidate in candidates:
        candidate_norm = os.path.normpath(candidate)
        if candidate_norm in seen:
            continue
        seen.add(candidate_norm)
        try:
            return load(candidate_norm), candidate_norm
        except Exception as exc:
            errors.append(f"{os.path.basename(candidate_norm)} -> {type(exc).__name__}: {exc}")

    detail = "; ".join(errors) if errors else "no_model_candidates"
    raise RuntimeError(f"tabular_model_load_failed: {detail}")


def _apply_loaded_model_metadata(meta: dict, model_path: str) -> dict:
    resolved = dict(meta or {})
    resolved["model_path"] = model_path
    parsed_name, parsed_version = _parse_versioned_model_filename(model_path)
    if parsed_name:
        resolved["model_name"] = parsed_name
    if parsed_version:
        resolved["model_version"] = parsed_version
    return resolved

def get_model():
    if _cached["model"] is None:
        reg = load_registry()
        _cached["meta"] = dict(reg)
        _cached["model"], model_path = _load_model_with_fallback(_cached["meta"])
        _cached["meta"] = _apply_loaded_model_metadata(_cached["meta"], model_path)
        # infer feature columns from modelcard if available
        card_path = _first_existing([os.path.join(ART_DIR, "modelcard.json"), os.path.join(ALT_ART_DIR, "modelcard.json")])
        if card_path:
            card = _read_json(card_path)
            _cached["feature_cols"] = card.get("features")
            card_classes = card.get("classes")
            if isinstance(card_classes, list) and card_classes:
                _cached["classes"] = [str(c) for c in card_classes]
            _cached["target_idx"] = card.get("target_index_diabetic")
        # Prefer feature names embedded in the trained estimator when present.
        if hasattr(_cached["model"], "feature_names_in_"):
            try:
                names = list(_cached["model"].feature_names_in_)
                if names:
                    _cached["model_feature_cols"] = names
            except Exception:
                pass
        preprocess = None
        try:
            base_estimator = getattr(_cached["model"], "estimator", None)
            if base_estimator is None and getattr(_cached["model"], "calibrated_classifiers_", None):
                base_estimator = getattr(_cached["model"].calibrated_classifiers_[0], "estimator", None)
            named_steps = getattr(base_estimator, "named_steps", {}) or {}
            preprocess = named_steps.get("preprocess") or named_steps.get("pre")
        except Exception:
            preprocess = None
        if preprocess is not None:
            for name, _transformer, cols in getattr(preprocess, "transformers_", []):
                if name == "num":
                    _cached["numeric_feature_cols"] = list(cols)
                    break
        if _cached["classes"] is None and hasattr(_cached["model"], "classes_"):
            _cached["classes"] = [str(c) for c in _cached["model"].classes_]
    return _cached["model"], _cached["meta"]

def _coerce_payload_value(payload: dict, key):
    if key in payload:
        return payload.get(key)
    sk = str(key)
    if sk in payload:
        return payload.get(sk)
    try:
        ik = int(sk)
        if ik in payload:
            return payload.get(ik)
    except Exception:
        pass
    return np.nan


def _coerce_numeric_feature(value):
    if value in ("", None):
        return np.nan
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return np.nan
        if text in {"yes", "true", "y", "1"}:
            return 1.0
        if text in {"no", "false", "n", "0"}:
            return 0.0
        try:
            return float(text)
        except Exception:
            return np.nan
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except Exception:
        return np.nan


def build_input_df(payload: dict) -> pd.DataFrame:
    model, meta = get_model()
    payload = derive_tabular_features(payload)
    # Use estimator feature schema first when available. Some artifacts can
    # drift from model card fields and include numeric column keys (e.g., 118).
    feature_cols = _cached["model_feature_cols"] or _cached["feature_cols"] or list(payload.keys())

    row = {c: _coerce_payload_value(payload, c) for c in feature_cols}
    # Helpful derived feature when expected by model.
    if "pulse_pressure" in row and (pd.isna(row["pulse_pressure"]) or row["pulse_pressure"] in ("", None)):
        try:
            sbp = float(_coerce_payload_value(payload, "systolic_bp"))
            dbp = float(_coerce_payload_value(payload, "diastolic_bp"))
            row["pulse_pressure"] = sbp - dbp
        except Exception:
            pass
    for feature in _cached.get("numeric_feature_cols") or []:
        if feature in row:
            row[feature] = _coerce_numeric_feature(row[feature])
    return pd.DataFrame([row])

def _predict_proba_safe(model, X: pd.DataFrame):
    # Some legacy artifacts may have numeric feature names while incoming JSON
    # payload keys are strings. Try robust column-name coercions before failing.
    variants = [
        X,
        X.rename(columns=lambda c: str(c)),
        X.rename(columns=lambda c: int(c) if str(c).isdigit() else c),
    ]

    def _extract_missing_keys(err: Exception):
        # Handle many pandas/sklearn variants:
        # - KeyError: 118
        # - KeyError: '118'
        # - KeyError: '[118] not in index'
        # - KeyError: "None of [Index([118], dtype='int64')] are in the [columns]"
        if not isinstance(err, KeyError):
            return []
        raw_args = list(getattr(err, "args", []) or [])
        if not raw_args:
            return []

        keys = []
        for raw in raw_args:
            if isinstance(raw, (int, np.integer)):
                keys.append(int(raw))
                continue
            txt = str(raw)
            for m in re.findall(r"\d+", txt):
                try:
                    keys.append(int(m))
                except Exception:
                    continue
        # preserve order + uniqueness
        seen = set()
        out = []
        for k in keys:
            if k in seen:
                continue
            seen.add(k)
            out.append(k)
        return out

    def _predict_with_missing_key_fill(xf: pd.DataFrame):
        # Some legacy artifacts request integer-indexed columns not present in
        # API payload shape (for example KeyError: 118). Add missing columns
        # as NaN and retry so inference remains robust.
        x_try = xf.copy()
        for _ in range(256):
            try:
                return model.predict_proba(x_try)[0].astype(float), x_try
            except Exception as err:
                missing_keys = _extract_missing_keys(err)
                if not missing_keys:
                    raise
                added_any = False
                for k in missing_keys:
                    if k in x_try.columns:
                        continue
                    x_try[k] = np.nan
                    added_any = True
                if not added_any:
                    raise
        raise RuntimeError("tabular_predict_proba_failed_after_missing_key_fill")

    seen = set()
    last_err = None
    for xf in variants:
        sig = tuple(map(str, xf.columns.tolist()))
        if sig in seen:
            continue
        seen.add(sig)
        try:
            return _predict_with_missing_key_fill(xf)
        except Exception as e:
            last_err = e
            continue

    raise last_err if last_err else RuntimeError("tabular_predict_proba_failed")

def _class_info(proba: np.ndarray):
    class_names = _cached["classes"] or [str(i) for i in range(len(proba))]
    if len(class_names) != len(proba):
        class_names = [str(i) for i in range(len(proba))]
    class_to_idx = {c: i for i, c in enumerate(class_names)}
    target_idx = _cached["target_idx"]
    if target_idx is None or not (0 <= int(target_idx) < len(proba)):
        target_idx = class_to_idx.get("diabetic")
        if target_idx is None:
            target_idx = class_to_idx.get("t2d", len(proba) - 1)
    target_idx = int(target_idx)
    return class_names, target_idx

def _occlusion_top(model, X: pd.DataFrame, base_proba: float, target_idx: int, max_features: int):
    fallback_pairs = []
    for feat in X.columns.tolist():
        x_alt = X.copy()
        x_alt.at[0, feat] = np.nan
        try:
            p_alt = float(_predict_proba_safe(model, x_alt)[0][int(target_idx)])
            fallback_pairs.append((feat, base_proba - p_alt, X.iloc[0][feat]))
        except Exception:
            continue
    fallback_pairs.sort(key=lambda t: abs(t[1]), reverse=True)
    return [
        {"feature": f, "shap_value": float(v), "value": val}
        for f, v, val in fallback_pairs[:max_features]
    ]

def predict_tabular(payload: dict):
    model, meta = get_model()
    X = build_input_df(payload)
    proba, _ = _predict_proba_safe(model, X)
    class_names, target_idx = _class_info(proba)
    predicted_label = class_names[int(np.argmax(proba))]
    p_t2d = float(proba[target_idx])
    probs = {class_names[i]: float(proba[i]) for i in range(len(class_names))}
    probs["t2d"] = p_t2d
    return {
        "model_name": meta["model_name"],
        "model_version": meta["model_version"],
        "predicted_label": predicted_label,
        "probabilities": probs,
    }

def predict_with_explain(payload: dict, max_features: int = 10):
    model, meta = get_model()
    X = build_input_df(payload)
    proba, X = _predict_proba_safe(model, X)
    class_names, target_idx = _class_info(proba)
    predicted_label = class_names[int(np.argmax(proba))]
    p_t2d = float(proba[target_idx])

    explain_method = "shap"
    shap_top = []

    if EXPLAIN_METHOD == "shap" and shap is not None:
        # SHAP can be expensive on some artifacts; fall back to occlusion for responsiveness.
        try:
            if _cached["explainer"] is None:
                bg = X.copy()
                _cached["explainer"] = shap.Explainer(
                    lambda data: model.predict_proba(pd.DataFrame(data, columns=X.columns))[:, int(target_idx)],
                    bg
                )
            explainer = _cached["explainer"]
            sv = explainer(X)
            vals = sv.values[0]
            feats = X.columns.tolist()
            pairs = list(zip(feats, vals, X.iloc[0].tolist()))
            pairs.sort(key=lambda t: abs(t[1]), reverse=True)
            shap_top = [{"feature": f, "shap_value": float(v), "value": val} for f, v, val in pairs[:max_features]]
        except Exception:
            explain_method = "occlusion"
            shap_top = _occlusion_top(model, X, p_t2d, target_idx, max_features)
    else:
        explain_method = "occlusion"
        shap_top = _occlusion_top(model, X, p_t2d, target_idx, max_features)

    return {
        "model_name": meta["model_name"],
        "model_version": meta["model_version"],
        "predicted_label": predicted_label,
        "probabilities": {**{class_names[i]: float(proba[i]) for i in range(len(class_names))}, "t2d": p_t2d},
        "explainability": {"method": explain_method, "top_features": shap_top},
    }

def load_model_card():
    reg = load_registry()
    candidate = _resolve_model_path(reg.get("modelcard_path", ""))
    path = _first_existing([
        os.path.join(ART_DIR, "modelcard.json"),
        candidate,
        os.path.join(ALT_ART_DIR, "modelcard.json"),
    ])
    if not path:
        # Fallback to any versioned model card generated by training.
        for base in [ART_DIR, ALT_ART_DIR]:
            if not os.path.exists(base):
                continue
            cards = [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".modelcard.json")]
            if cards:
                path = sorted(cards)[-1]
                break
    if not path:
        raise FileNotFoundError("Tabular model card not found")
    return _sanitize_json(_read_json(path))

def load_performance():
    reg = load_registry()
    perf_path = _first_existing([
        _resolve_model_path(reg.get("performance_path", "")),
        os.path.join(ART_DIR, "performance.json"),
        os.path.join(ALT_ART_DIR, "performance.json"),
    ])
    if not perf_path:
        raise FileNotFoundError("Tabular performance.json not found")
    perf = _sanitize_json(_read_json(perf_path))

    comp_csv_path = _first_existing([
        _resolve_model_path(reg.get("comparison_csv", "")),
        os.path.join(ART_DIR, "comparison.csv"),
        os.path.join(ALT_ART_DIR, "comparison.csv"),
    ])
    comp = []
    if comp_csv_path:
        try:
            comp = _sanitize_json(pd.read_csv(comp_csv_path).to_dict(orient="records"))
        except Exception:
            comp = []
    return perf, comp
