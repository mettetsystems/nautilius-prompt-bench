from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from prompt_piper.setup.embedding_device import EmbeddingDeviceDecision, resolve_embedding_device
from prompt_piper.setup.env_writer import upsert_lexicon_env_section
from prompt_piper.setup.paths import repo_root


@dataclass(frozen=True)
class LexiconSetupResult:
    wordnet_ready: bool
    embed_ready: bool
    vector_index_ready: bool
    vector_index_path: Path | None
    index_build_skipped: bool
    embedding_device: str
    embedding_device_reason: str


def nltk_data_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "nltk_data"


def lexicon_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "lexicon"


def vector_index_path(root: Path | None = None) -> Path:
    return lexicon_dir(root) / "precision_vectors.json"


def venv_python(root: Path | None = None) -> Path:
    return (root or repo_root()) / "apps" / "api" / ".venv" / "bin" / "python"


def venv_pip(root: Path | None = None) -> Path:
    return (root or repo_root()) / "apps" / "api" / ".venv" / "bin" / "pip"


def _nltk_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Env for NLTK child processes.

    NLTK 3.10+ blocks imports under CWD; a repo-local venv sits under that tree,
    so legitimate site-packages (e.g. regex) are false-positive blocked.
    """
    env = {**os.environ, **(extra or {})}
    env.setdefault("NLTK_DISABLE_IMPORT_SECURITY", "1")
    return env


def is_wordnet_installed(root: Path | None = None) -> bool:
    data_dir = nltk_data_dir(root)
    return (data_dir / "corpora" / "wordnet").is_dir()


def is_lexicon_embed_installed() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def is_vector_index_built(root: Path | None = None) -> bool:
    path = vector_index_path(root)
    return path.is_file() and path.stat().st_size > 0


def setup_wordnet(root: Path | None = None) -> bool:
    """Download WordNet + OMW into repo-local data/nltk_data."""
    root = root or repo_root()
    data_dir = nltk_data_dir(root)
    data_dir.mkdir(parents=True, exist_ok=True)

    if is_wordnet_installed(root):
        return True

    python = venv_python(root)
    if not python.is_file():
        msg = "Backend venv not found. Run 'make install-api' first."
        raise RuntimeError(msg)

    env = _nltk_subprocess_env({"NLTK_DATA": str(data_dir)})
    subprocess.run(
        [
            str(python),
            "-m",
            "nltk.downloader",
            "-d",
            str(data_dir),
            "wordnet",
            "omw-1.4",
        ],
        check=True,
        env=env,
    )
    return is_wordnet_installed(root)


def setup_lexicon_embed(root: Path | None = None) -> bool:
    """Install sentence-transformers into the API venv."""
    root = root or repo_root()
    if is_lexicon_embed_installed():
        return True

    pip = venv_pip(root)
    api_dir = root / "apps" / "api"
    if not pip.is_file():
        msg = "Backend venv not found. Run 'make install-api' first."
        raise RuntimeError(msg)

    subprocess.run(
        [str(pip), "install", "-e", f"{api_dir}[lexicon]"],
        check=True,
    )
    return is_lexicon_embed_installed()


def configure_embedding_runtime(root: Path | None = None) -> EmbeddingDeviceDecision:
    """Detect GPU compatibility and write PROMPT_PIPER_EMBEDDING_DEVICE to .env."""
    root = root or repo_root()
    env_path = root / ".env"
    if not env_path.is_file() and (root / ".env.example").is_file():
        env_path.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")

    decision = resolve_embedding_device()
    upsert_lexicon_env_section(
        env_path,
        {"PROMPT_PIPER_EMBEDDING_DEVICE": decision.device},
        preamble=(f"# {decision.reason}",),
    )
    return decision


def build_vector_index(
    root: Path | None = None,
    *,
    force: bool = False,
) -> Path | None:
    """Embed WordNet + glossary entries (CPU by default). Returns output path."""
    root = root or repo_root()
    output = vector_index_path(root)
    if not force and is_vector_index_built(root):
        return output

    setup_lexicon_embed(root)
    setup_wordnet(root)

    python = venv_python(root)
    if not python.is_file():
        msg = "Backend venv not found. Run 'make install-api' first."
        raise RuntimeError(msg)

    env = _nltk_subprocess_env({"CUDA_VISIBLE_DEVICES": ""})
    subprocess.run(
        [str(python), "-m", "prompt_piper.lexicon.build_index", "--output", str(output)],
        check=True,
        env=env,
    )
    return output if is_vector_index_built(root) else None


def run_lexicon_setup(
    *,
    root: Path | None = None,
    skip_index: bool = False,
    force_index: bool = False,
) -> LexiconSetupResult:
    """WordNet + embedding deps; optional vector index build when missing."""
    root = root or repo_root()
    lexicon_dir(root).mkdir(parents=True, exist_ok=True)
    nltk_data_dir(root).mkdir(parents=True, exist_ok=True)

    wordnet_ready = setup_wordnet(root)
    embed_ready = setup_lexicon_embed(root)
    device_decision = configure_embedding_runtime(root)

    index_skipped = False
    index_path: Path | None = None
    if skip_index:
        index_skipped = True
        index_path = vector_index_path(root) if is_vector_index_built(root) else None
    elif is_vector_index_built(root) and not force_index:
        index_skipped = True
        index_path = vector_index_path(root)
    else:
        index_path = build_vector_index(root, force=force_index)

    return LexiconSetupResult(
        wordnet_ready=wordnet_ready,
        embed_ready=embed_ready,
        vector_index_ready=is_vector_index_built(root),
        vector_index_path=index_path,
        index_build_skipped=index_skipped,
        embedding_device=device_decision.device,
        embedding_device_reason=device_decision.reason,
    )


def lexicon_setup_command_lines(*, root: Path | None = None) -> tuple[str, ...]:
    """Shell commands for manual lexicon setup (wizard next-steps)."""
    root = root or repo_root()
    python = venv_python(root)
    return (
        "Precision lexicon (semantic refinement):",
        f"  {python} -m prompt_piper.setup.lexicon_setup",
        "  # or: make setup-lexicon-all",
        "  # Index build is CPU-only (~20–60 min); skipped when already present.",
        "  # PROMPT_PIPER_EMBEDDING_DEVICE is set from GPU compatibility during setup.",
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up WordNet, embedding deps, and precision vector index.",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Download WordNet and install embeddings only; do not build vector index.",
    )
    parser.add_argument(
        "--force-index",
        action="store_true",
        help="Rebuild precision_vectors.json even when it already exists.",
    )
    parser.add_argument(
        "--wordnet-only",
        action="store_true",
        help="Download WordNet data only.",
    )
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Install sentence-transformers only.",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Build vector index only (requires WordNet + sentence-transformers).",
    )
    args = parser.parse_args(argv)

    try:
        if args.wordnet_only:
            ok = setup_wordnet()
            print(f"WordNet ready: {ok}")
            return 0 if ok else 1

        if args.embed_only:
            ok = setup_lexicon_embed()
            decision = configure_embedding_runtime()
            print(f"sentence-transformers ready: {ok}")
            print(f"Embedding device: {decision.device} ({decision.reason})")
            return 0 if ok else 1

        if args.index_only:
            path = build_vector_index(force=args.force_index)
            if path is None:
                print("Vector index build failed.", file=sys.stderr)
                return 1
            print(f"Wrote vector index to {path}")
            return 0

        result = run_lexicon_setup(skip_index=args.skip_index, force_index=args.force_index)
    except subprocess.CalledProcessError as exc:
        print(f"Lexicon setup failed (exit {exc.returncode}).", file=sys.stderr)
        return exc.returncode or 1
    except RuntimeError as exc:
        print(f"Lexicon setup error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Lexicon setup complete — WordNet: {result.wordnet_ready}, "
        f"embeddings: {result.embed_ready}, "
        f"vector index: {result.vector_index_ready}"
        + (" (skipped)" if result.index_build_skipped else "")
    )
    print(
        f"Embedding runtime: {result.embedding_device} "
        f"({result.embedding_device_reason})"
    )
    if result.vector_index_path is not None:
        print(f"  index: {result.vector_index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
