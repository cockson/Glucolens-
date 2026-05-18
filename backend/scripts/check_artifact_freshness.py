import json
import os
import re
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = BACKEND_ROOT / "artifacts"
VERSION_RE = re.compile(r"_(\d{8}_\d{6})\.joblib$")

MODALITIES = {
    "tabular": {"card": "modelcard.json", "performance": "performance.json", "requires_static_card": True},
    "retina": {"card": "modelcard.json", "performance": "performance.json", "requires_static_card": True},
    "skin": {"card": "modelcard.json", "performance": None, "requires_static_card": True},
    "genomics": {"card": "model_card.json", "performance": "performance.json", "requires_static_card": True},
    "fusion": {"card": "modelcard.json", "performance": "performance.json", "requires_static_card": True},
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def repo_path(path: str) -> Path:
    parts = [p for p in re.split(r"[\\/]+", str(path or "")) if p and p != "."]
    if not parts:
        return BACKEND_ROOT
    if "backend" in parts:
        parts = parts[parts.index("backend") + 1 :]
    if parts and parts[0] == "artifacts":
        return BACKEND_ROOT.joinpath(*parts)
    return BACKEND_ROOT.joinpath(*parts)


def version_from_model_path(path: str) -> str | None:
    match = VERSION_RE.search(str(path or ""))
    return match.group(1) if match else None


def get_nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def check_modality(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    base = ARTIFACT_ROOT / name
    failures: list[str] = []
    warnings: list[str] = []

    registry_path = base / "registry.json"
    if not registry_path.is_file():
        return {"modality": name, "status": "fail", "failures": ["missing registry.json"], "warnings": []}

    registry = load_json(registry_path).get("current") or {}
    model_path_text = registry.get("model_path")
    if not model_path_text:
        failures.append("registry.current.model_path is missing")
        model_file = None
    else:
        model_file = repo_path(model_path_text)
        if not model_file.is_file():
            failures.append(f"registry model_path does not exist: {model_path_text}")

    inferred_version = version_from_model_path(model_path_text or "")
    registry_version = registry.get("model_version")
    if registry_version and inferred_version and registry_version != inferred_version:
        failures.append(
            f"registry model_version {registry_version} does not match model_path version {inferred_version}"
        )

    card_version = None
    card_name = cfg.get("card")
    if card_name:
        card_path = base / card_name
        if not card_path.is_file():
            failures.append(f"missing model card: {card_name}")
        else:
            card = load_json(card_path)
            card_name_value = card.get("model_name")
            card_version = card.get("model_version")
            if registry.get("model_name") and card_name_value and registry["model_name"] != card_name_value:
                failures.append(
                    f"registry model_name {registry['model_name']} does not match card model_name {card_name_value}"
                )
            expected_version = registry_version or inferred_version
            if expected_version and card_version and card_version != expected_version:
                failures.append(
                    f"card model_version {card_version} does not match current version {expected_version}"
                )
            if not card.get("intended_use") and name not in {"tabular", "genomics"}:
                warnings.append("model card has no intended_use field")
            if name == "skin" and not card.get("metrics_val"):
                failures.append("skin has no performance.json and modelcard.metrics_val is missing")
    elif cfg.get("requires_static_card"):
        failures.append("static model card is required but no card filename is configured")

    performance_name = cfg.get("performance")
    if performance_name:
        perf_path = base / performance_name
        if not perf_path.is_file():
            failures.append(f"missing performance file: {performance_name}")
        else:
            perf = load_json(perf_path)
            perf_version = (
                get_nested(perf, "current", "model_version")
                or get_nested(perf, "current", "model_version")
                or perf.get("model_version")
            )
            expected_version = registry_version or inferred_version or card_version
            if perf_version and expected_version and perf_version != expected_version:
                failures.append(
                    f"performance model_version {perf_version} does not match current version {expected_version}"
                )
            if name == "fusion":
                if not perf.get("metrics_summary"):
                    failures.append("fusion performance.metrics_summary is missing")
                if not perf.get("horizon_training_note"):
                    failures.append("fusion performance.horizon_training_note is missing")
            elif name == "tabular":
                if not get_nested(perf, "best", "oof"):
                    failures.append("tabular performance.best.oof is missing")
            elif name == "genomics":
                if "auc" not in perf and not get_nested(perf, "metrics_oof", "auc"):
                    failures.append("genomics performance AUC is missing")
            elif name == "retina":
                if not perf.get("val"):
                    failures.append("retina performance.val is missing")

    return {
        "modality": name,
        "status": "fail" if failures else "pass",
        "model_path": model_path_text,
        "registry_version": registry_version,
        "inferred_version": inferred_version,
        "card_version": card_version,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    results = [check_modality(name, cfg) for name, cfg in MODALITIES.items()]
    report = {
        "status": "fail" if any(r["failures"] for r in results) else "pass",
        "results": results,
    }
    print(json.dumps(report, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
