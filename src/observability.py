"""Stage artifact persistence — the backbone of the observable pipeline.

Every offline stage reads the previous stage's artifact and writes its own under
``data/<stage>/<doc_id>.<ext>`` through these helpers, so each step is
inspectable and re-loadable. JSON is pretty-printed (``indent=2``,
``ensure_ascii=False``); ``txt`` is written raw. Writes are deterministic and
idempotent — the same input always produces the same file, with no timestamps or
random values in the body.

Pydantic models (and lists of them) are serialized automatically::

    from src.observability import persist_artifact, load_artifact
    persist_artifact("chunks", "AAPL_10K_2024", chunks)      # list[Chunk] -> JSON
    raw = load_artifact("chunks", "AAPL_10K_2024")           # -> list[dict]
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from src.config import settings

_EXTS = ("json", "txt")


def _check_ext(ext: str) -> None:
    if ext not in _EXTS:
        raise ValueError(f"unsupported ext {ext!r}; use one of {_EXTS}")


def _safe(token: str, name: str) -> str:
    """Reject empty or path-traversing stage/doc_id tokens."""
    if not token or "/" in token or "\\" in token or ".." in token:
        raise ValueError(f"unsafe {name}: {token!r}")
    return token


def _to_jsonable(obj: object) -> object:
    """Turn pydantic models (and lists of them) into JSON-safe primitives."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [x.model_dump(mode="json") if isinstance(x, BaseModel) else x for x in obj]
    return obj


def _root(base: str | Path | None) -> Path:
    return Path(base) if base is not None else settings.data_path


def artifact_path(stage: str, doc_id: str, ext: str = "json", *, base: str | Path | None = None) -> Path:
    """Path where ``doc_id``'s artifact for ``stage`` lives (no I/O)."""
    _check_ext(ext)
    return _root(base) / _safe(stage, "stage") / f"{_safe(doc_id, 'doc_id')}.{ext}"


def persist_artifact(
    stage: str, doc_id: str, obj: object, ext: str = "json", *, base: str | Path | None = None
) -> Path:
    """Write ``obj`` to ``data/<stage>/<doc_id>.<ext>`` and return the path."""
    path = artifact_path(stage, doc_id, ext, base=base)
    path.parent.mkdir(parents=True, exist_ok=True)
    if ext == "json":
        text = json.dumps(_to_jsonable(obj), indent=2, ensure_ascii=False) + "\n"
    else:  # txt — written exactly as given, so round-trips are byte-faithful
        if not isinstance(obj, str):
            raise TypeError("txt artifacts require a str obj")
        text = obj
    # newline="" -> write '\n' verbatim (no OS CRLF translation), so artifacts are byte-faithful.
    path.write_text(text, encoding="utf-8", newline="")
    return path


def load_artifact(stage: str, doc_id: str, ext: str = "json", *, base: str | Path | None = None):
    """Load an artifact. JSON -> dict/list; txt -> str. Raises FileNotFoundError if missing."""
    path = artifact_path(stage, doc_id, ext, base=base)
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if ext == "json" else text


def list_artifacts(stage: str, ext: str = "json", *, base: str | Path | None = None) -> list[str]:
    """Sorted doc_ids with an artifact for ``stage`` (``.gitkeep`` etc. are ignored)."""
    _check_ext(ext)
    folder = _root(base) / _safe(stage, "stage")
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob(f"*.{ext}"))


def stage_count(stage: str, ext: str = "json", *, base: str | Path | None = None) -> int:
    """How many artifacts ``stage`` has persisted."""
    return len(list_artifacts(stage, ext, base=base))
