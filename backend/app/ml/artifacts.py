import os
import re


_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _split_parts(path: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", path or "") if part and part != "."]


def resolve_artifact_path(
    path: str,
    *,
    repo_root: str,
    project_root: str,
    artifact_dir: str | None = None,
) -> str:
    if not path:
        return path

    text = str(path).strip()
    candidates: list[str] = []

    if os.path.isabs(text):
        candidates.append(text)

    parts = _split_parts(text)
    if artifact_dir and parts:
        candidates.append(os.path.join(artifact_dir, parts[-1]))

    if "backend" in parts:
        idx = parts.index("backend")
        tail = parts[idx + 1 :]
        candidates.append(os.path.join(project_root, "backend", *tail))
        if tail:
            candidates.append(os.path.join(repo_root, *tail))

    if "artifacts" in parts:
        idx = parts.index("artifacts")
        candidates.append(os.path.join(repo_root, *parts[idx:]))

    if text == "backend" or text.startswith(("backend/", "backend\\")):
        tail_parts = _split_parts(text[len("backend") :].lstrip("\\/"))
        candidates.append(os.path.join(project_root, "backend", *tail_parts))
    elif not _WINDOWS_ABS_RE.match(text) and not text.startswith(("\\\\", "//")):
        rel_parts = _split_parts(text)
        if rel_parts:
            candidates.append(os.path.join(repo_root, *rel_parts))

    seen = set()
    deduped: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        normalized = os.path.normpath(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    for candidate in deduped:
        if os.path.exists(candidate):
            return candidate

    return deduped[0] if deduped else os.path.normpath(text)
