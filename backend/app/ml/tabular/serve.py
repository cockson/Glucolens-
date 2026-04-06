import json
import os
import re
import threading
import time
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
_model_lock = threading.Lock()
_warmup_lock = threading.Lock()
_warmup_thread: threading.Thread | None = None
_warmup_state = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _max_model_size_bytes() -> int | None:
    raw = os.getenv("TABULAR_MAX_MODEL_SIZE_MB", "").strip()
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return int(value * 1024 * 1024)
        except ValueError:
            pass

    if os.getenv("ENV", "").strip().lower() == "prod":
        return 64 * 1024 * 1024

    return None

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


def _set_warmup_state(status: str, *, error: str | None = None):
    with _warmup_lock:
        _warmup_state["status"] = status
        _warmup_state["error"] = error
        now = time.time()
        if status == "loading":
            _warmup_state["started_at"] = now
            _warmup_state["finished_at"] = None
        elif status in {"ready", "failed"}:
            if _warmup_state["started_at"] is None:
                _warmup_state["started_at"] = now
            _warmup_state["finished_at"] = now


def get_model_status() -> dict:
    with _warmup_lock:
        status = dict(_warmup_state)

    meta = _cached.get("meta") or {}
    reg = {}
    if not meta:
        try:
            reg = load_registry()
        except Exception:
            reg = {}

    model_meta = meta or reg
    status["loaded"] = _cached.get("model") is not None
    status["model_name"] = model_meta.get("model_name")
    status["model_version"] = model_meta.get("model_version")
    return status

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
    max_model_size_bytes = _max_model_size_bytes()

    if model_path and os.path.isfile(model_path) and not is_git_lfs_pointer(model_path):
        candidates.append(model_path)
    candidates.extend(_local_model_candidates(meta.get("model_name"), preferred_path=model_path))

    seen = set()
    for candidate in candidates:
        candidate_norm = os.path.normpath(candidate)
        if candidate_norm in seen:
            continue
        seen.add(candidate_norm)
        if max_model_size_bytes is not None:
            try:
                candidate_size = os.path.getsize(candidate_norm)
            except OSError as exc:
                errors.append(f"{os.path.basename(candidate_norm)} -> OSError: {exc}")
                continue
            if candidate_size > max_model_size_bytes:
                errors.append(
                    f"{os.path.basename(candidate_norm)} -> skipped_oversized_model: "
                    f"{candidate_size} bytes exceeds {max_model_size_bytes} byte limit"
                )
                continue
        try:
            return load(candidate_norm), candidate_norm
        except Exception as exc:
            errors.append(f"{os.path.basename(candidate_norm)} -> {type(exc).__name__}: {exc}")

    if model_path and model_path not in seen:
        try:
            hydrated_path = ensure_artifact_file(
                model_path,
                repo_relative_path=repo_relative_path,
            )
            hydrated_norm = os.path.normpath(hydrated_path)
            if max_model_size_bytes is not None:
                hydrated_size = os.path.getsize(hydrated_norm)
                if hydrated_size > max_model_size_bytes:
                    errors.append(
                        f"{os.path.basename(hydrated_norm)} -> skipped_oversized_model: "
                        f"{hydrated_size} bytes exceeds {max_model_size_bytes} byte limit"
                    )
                else:
                    return load(hydrated_norm), hydrated_norm
            else:
                return load(hydrated_norm), hydrated_norm
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

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


def _load_model_card_for_meta(meta: dict | None = None) -> dict | None:
    meta = meta or {}
    candidate = _resolve_model_path(meta.get("modelcard_path", ""))
    path = _first_existing([
        candidate,
        os.path.join(ART_DIR, "modelcard.json"),
        os.path.join(ALT_ART_DIR, "modelcard.json"),
    ])
    if not path:
        for base in [ART_DIR, ALT_ART_DIR]:
            if not os.path.exists(base):
                continue
            cards = [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".modelcard.json")]
            if cards:
                path = sorted(cards)[-1]
                break
    if not path:
        return None
    return _read_json(path)


def _load_model_into_cache():
    reg = load_registry()
    meta = dict(reg)
    model, model_path = _load_model_with_fallback(meta)
    meta = _apply_loaded_model_metadata(meta, model_path)

    card = _load_model_card_for_meta(meta)
    feature_cols = None
    classes = None
    target_idx = None
    if card:
        feature_cols = card.get("features")
        card_classes = card.get("classes")
        if isinstance(card_classes, list) and card_classes:
            classes = [str(c) for c in card_classes]
        target_idx = card.get("target_index_diabetic")

    model_feature_cols = None
    if hasattr(model, "feature_names_in_"):
        try:
            names = list(model.feature_names_in_)
            if names:
                model_feature_cols = names
        except Exception:
            pass

    numeric_feature_cols = None
    preprocess = None
    try:
        base_estimator = getattr(model, "estimator", None)
        if base_estimator is None and getattr(model, "calibrated_classifiers_", None):
            base_estimator = getattr(model.calibrated_classifiers_[0], "estimator", None)
        named_steps = getattr(base_estimator, "named_steps", {}) or {}
        preprocess = named_steps.get("preprocess") or named_steps.get("pre")
    except Exception:
        preprocess = None
    if preprocess is not None:
        for name, _transformer, cols in getattr(preprocess, "transformers_", []):
            if name == "num":
                numeric_feature_cols = list(cols)
                break
    if classes is None and hasattr(model, "classes_"):
        classes = [str(c) for c in model.classes_]

    _cached["model"] = model
    _cached["meta"] = meta
    _cached["explainer"] = None
    _cached["feature_cols"] = feature_cols
    _cached["model_feature_cols"] = model_feature_cols
    _cached["numeric_feature_cols"] = numeric_feature_cols
    _cached["classes"] = classes
    _cached["target_idx"] = target_idx

def get_model():
    if _cached["model"] is None:
        with _model_lock:
            if _cached["model"] is None:
                _load_model_into_cache()
    return _cached["model"], _cached["meta"]


def _warmup_model():
    try:
        _set_warmup_state("loading")
        get_model()
        _set_warmup_state("ready")
    except Exception as exc:
        _set_warmup_state("failed", error=f"{type(exc).__name__}: {exc}")


def start_model_warmup(force: bool = False) -> bool:
    global _warmup_thread

    if _cached["model"] is not None and not force:
        _set_warmup_state("ready")
        return False

    with _warmup_lock:
        current_status = _warmup_state["status"]
        thread_alive = _warmup_thread is not None and _warmup_thread.is_alive()
        if thread_alive and not force:
            return False
        if current_status == "ready" and not force:
            return False
        _warmup_state["status"] = "queued"
        _warmup_state["error"] = None
        _warmup_state["started_at"] = time.time()
        _warmup_state["finished_at"] = None
        _warmup_thread = threading.Thread(target=_warmup_model, name="tabular-model-warmup", daemon=True)
        _warmup_thread.start()
        return True


def ensure_model_ready():
    if _cached["model"] is not None:
        return

    status = get_model_status()
    if status["status"] == "failed":
        raise RuntimeError(f"tabular_model_unavailable: {status.get('error') or 'warmup_failed'}")
    if status["status"] in {"queued", "loading"}:
        raise RuntimeError("tabular_model_warming_up: the tabular model is still loading, retry shortly")

    start_model_warmup()
    raise RuntimeError("tabular_model_warming_up: tabular model warmup started, retry shortly")

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
    ensure_model_ready()
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
    ensure_model_ready()
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
    card = _load_model_card_for_meta(reg)
    if not card:
        raise FileNotFoundError("Tabular model card not found")
    return _sanitize_json(card)

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
