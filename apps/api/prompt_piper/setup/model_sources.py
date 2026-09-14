"""Shared model-source preferences; tokens are never returned to the UI."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from prompt_piper.setup.llama_launcher import repo_root


def preferences_path() -> Path:
    return repo_root() / "data" / "model-source.json"


def load_preferences() -> dict[str, str]:
    path = preferences_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_preferences(
    *, hf_token: str | None = None, local_repo: str | None = None, clear_token: bool = False
) -> dict:
    values = load_preferences()
    if clear_token:
        values.pop("hf_token", None)
    elif hf_token:
        if any(c.isspace() for c in hf_token):
            raise ValueError("Token must not contain whitespace")
        values["hf_token"] = hf_token
    if local_repo is not None:
        if local_repo.strip():
            path = Path(local_repo).expanduser().resolve()
            if not path.exists() or not (path.is_dir() or path.suffix.lower() == ".gguf"):
                raise ValueError("Local repository must be an existing directory or GGUF file")
            values["local_repo"] = str(path)
        else:
            values.pop("local_repo", None)
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".model-source-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(values, stream)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return public_preferences(values)


def public_preferences(values: dict | None = None) -> dict:
    values = load_preferences() if values is None else values
    return {
        "hf_token_configured": bool(values.get("hf_token")),
        "local_repo": values.get("local_repo", ""),
    }


def local_gguf(path: str, recommended_filename: str, read=input, write=print) -> Path:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        files = sorted(source.rglob("*.gguf"))
        preferred = [file for file in files if file.name == recommended_filename]
        if len(preferred) == 1:
            source = preferred[0]
        elif len(files) == 1:
            source = files[0]
        elif files:
            for index, file in enumerate(files, 1):
                write(f"  {index}) {file.relative_to(source)}")
            choice = read("GGUF file number: ").strip()
            if not choice.isdigit() or not 1 <= int(choice) <= len(files):
                raise ValueError("Choose a listed GGUF file")
            source = files[int(choice) - 1]
        else:
            raise ValueError("No GGUF files found in this local repository")
    if not source.is_file() or source.suffix.lower() != ".gguf":
        raise ValueError("Choose an existing GGUF file or directory of GGUF files")
    with source.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise ValueError("Not a GGUF model (a Git LFS pointer must be materialized first)")
    return source.resolve()
