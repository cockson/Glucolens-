import os
import re
import tempfile
import urllib.parse
import urllib.request


_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
_DEFAULT_ARTIFACT_MEDIA_BASE_URL = os.getenv(
    "ARTIFACT_MEDIA_BASE_URL",
    "https://media.githubusercontent.com/media/cockson/Glucolens-/main/backend",
)


def _split_parts(path: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", path or "") if part and part != "."]


def infer_repo_relative_artifact_path(path: str) -> str | None:
    parts = _split_parts(path)
    if not parts:
        return None
    if "backend" in parts:
        parts = parts[parts.index("backend") + 1 :]
    elif "artifacts" in parts:
        parts = parts[parts.index("artifacts") :]
    elif _WINDOWS_ABS_RE.match(str(path).strip()) or str(path).startswith(("\\\\", "//")):
        return None
    return "/".join(parts) if parts else None


def is_git_lfs_pointer(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(len(_LFS_POINTER_PREFIX)) == _LFS_POINTER_PREFIX
    except OSError:
        return False


def ensure_artifact_file(path: str, repo_relative_path: str | None = None) -> str:
    target = os.path.normpath(path)
    if os.path.isfile(target) and not is_git_lfs_pointer(target):
        return target

    rel_path = (repo_relative_path or infer_repo_relative_artifact_path(path) or "").strip("/")
    if not rel_path:
        return target

    os.makedirs(os.path.dirname(target), exist_ok=True)
    quoted_rel = "/".join(urllib.parse.quote(part) for part in rel_path.split("/") if part)
    url = f"{_DEFAULT_ARTIFACT_MEDIA_BASE_URL}/{quoted_rel}"
    request = urllib.request.Request(url, headers={"User-Agent": "GlucoLens/1.0"})

    fd, tmp_path = tempfile.mkstemp(prefix="artifact_", suffix=".tmp", dir=os.path.dirname(target))
    os.close(fd)
    try:
        with urllib.request.urlopen(request, timeout=180) as response, open(tmp_path, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        if is_git_lfs_pointer(tmp_path):
            raise RuntimeError(f"artifact_download_returned_lfs_pointer: {rel_path}")
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return target


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
