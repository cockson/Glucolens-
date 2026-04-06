import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.ml.artifacts import ensure_artifact_file, infer_repo_relative_artifact_path, is_git_lfs_pointer

ARTIFACT_ROOT = REPO_ROOT / "artifacts"


def main() -> None:
    for path in sorted(ARTIFACT_ROOT.rglob("*.joblib")):
        repo_relative = infer_repo_relative_artifact_path(str(path.relative_to(REPO_ROOT)))
        if not path.exists() or is_git_lfs_pointer(str(path)):
            ensure_artifact_file(str(path), repo_relative_path=repo_relative)


if __name__ == "__main__":
    main()
