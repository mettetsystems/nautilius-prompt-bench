from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from prompt_piper.setup.catalog import (
    ALL_PRESETS,
    GEMMA3N_PRESETS,
    GEMMA3_PRESETS,
    NATIVE_BASE_URL,
    PODMAN_BASE_URL,
    QWEN3_PRESETS,
    TIER_LABELS,
    ModelFamily,
    ModelPreset,
    ModelTier,
    preset_fits_vram,
    resolve_preset_id,
)
from prompt_piper.setup.env_writer import upsert_env_section
from prompt_piper.setup.gpu_detect import detect_gpu, recommended_tier
from prompt_piper.setup.lexicon_setup import lexicon_setup_command_lines
from prompt_piper.setup.model_deps import (
    hf_cli_env_comments,
    hf_download_command,
)


from prompt_piper.setup.paths import repo_root


@dataclass(frozen=True)
class SetupResult:
    cpu_only: bool
    preset_id: str | None
    base_url: str | None
    chat_model: str | None
    api_key: str | None
    env_path: Path


InputFn = Callable[[str], str]
PrintFn = Callable[[str], None]


def run_setup_wizard(
    *,
    env_path: Path | None = None,
    input_fn: InputFn | None = None,
    print_fn: PrintFn | None = None,
    non_interactive: str | None = None,
) -> SetupResult:
    """Run the text-based model setup wizard and write .env."""
    root = repo_root()
    target_env = env_path or (root / ".env")
    if not target_env.is_file() and (root / ".env.example").is_file():
        target_env.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")

    read = input_fn or input
    write = print_fn or print

    write(_banner())
    if non_interactive:
        result = _resolve_non_interactive(non_interactive)
    else:
        result = _run_interactive(read, write)

    _apply_result(target_env, result)
    _print_next_steps(write, result)
    return result


def _banner() -> str:
    return (
        "\nNautilius Prompting Workbench setup — local model configuration\n"
        "================================================\n"
        "Clarification and draft generation can use a local OpenAI-compatible\n"
        "server (llama.cpp, vLLM, etc.) or run in CPU-only mode with rule-based\n"
        "fallbacks. Similarity search embeddings stay separate.\n"
    )


def _run_interactive(read: InputFn, write: PrintFn) -> SetupResult:
    write(
        "\nHow should Nautilius Prompting Workbench handle clarification and draft wording?\n"
        "  1) CPU-only mode (no local chat model; rule-based fallbacks)\n"
        "  2) Set up a local SLM (recommended with llama.cpp)\n"
    )
    mode = _choose(read, "Choice", ("1", "2"), default="1")
    if mode == "1":
        return SetupResult(
            cpu_only=True,
            preset_id=None,
            base_url=None,
            chat_model=None,
            api_key=None,
            env_path=Path(),
        )

    write(
        "\nChoose a model family:\n"
        "  1) Google Gemma 3 (1B – 12B; official google/* QAT GGUF)\n"
        "  2) Google Gemma 3n (E4B efficient; ~3–4B class)\n"
        "  3) Qwen3 (0.6B – 14B; official Qwen/* GGUF)\n"
        "  4) Other — connect your own OpenAI-compatible endpoint (vLLM, Ollama, etc.)\n"
    )
    family_choice = _choose(read, "Choice", ("1", "2", "3", "4"), default="1")

    deployment = _ask_deployment(read, write)
    base_url = PODMAN_BASE_URL if deployment == "podman" else NATIVE_BASE_URL
    gpu = detect_gpu()
    _write_gpu_summary(write, gpu)

    if family_choice == "1":
        preset = _choose_preset(read, write, GEMMA3_PRESETS, gpu=gpu, default_index=1)
        return _preset_result(preset, base_url)
    if family_choice == "2":
        preset = _choose_preset(read, write, GEMMA3N_PRESETS, gpu=gpu, default_index=0)
        return _preset_result(preset, base_url)
    if family_choice == "3":
        preset = _choose_preset(read, write, QWEN3_PRESETS, gpu=gpu, default_index=2)
        return _preset_result(preset, base_url)

    write(
        "\nCustom endpoint — for GPUs running larger models (7B–30B) via vLLM,\n"
        "llama.cpp, Ollama OpenAI shim, or similar.\n"
    )
    base_url = _prompt_default(read, "OpenAI-compatible base URL", base_url)
    chat_model = _prompt_default(read, "Model name / ID exposed by your server", "llama")
    api_key = read("API key (optional, press Enter to skip): ").strip() or None
    return SetupResult(
        cpu_only=False,
        preset_id="custom",
        base_url=base_url,
        chat_model=chat_model,
        api_key=api_key,
        env_path=Path(),
    )


def _ask_deployment(read: InputFn, write: PrintFn) -> str:
    write(
        "\nWhere will the Nautilius Prompting Workbench API run?\n"
        "  1) Native dev (API on host — use 127.0.0.1 for the model server)\n"
        "  2) Podman stack (API in container — use host.containers.internal)\n"
    )
    choice = _choose(read, "Choice", ("1", "2"), default="1")
    return "podman" if choice == "2" else "native"


def _write_gpu_summary(write: PrintFn, gpu) -> None:
    if gpu is None:
        write(
            "\nGPU: not detected — compact presets are safest; "
            "standard (~8GB+) and prosumer (~16GB+) models need sufficient VRAM.\n"
        )
        return
    vram_text = f"{gpu.vram_mb} MB" if gpu.vram_mb is not None else "VRAM unknown"
    tier = recommended_tier(gpu.vram_mb)
    write(
        f"\nGPU: {gpu.vendor} {gpu.name} ({vram_text}). "
        f"Recommended tier: {TIER_LABELS[tier]}.\n"
    )


def _choose_preset(
    read: InputFn,
    write: PrintFn,
    presets: tuple[ModelPreset, ...],
    *,
    gpu,
    default_index: int,
) -> ModelPreset:
    write("")
    rec_tier = recommended_tier(gpu.vram_mb if gpu is not None else None)
    current_tier: ModelTier | None = None
    option_index = 0
    options: list[ModelPreset] = []
    for preset in presets:
        if preset.tier != current_tier:
            current_tier = preset.tier
            write(f"\n  --- {TIER_LABELS[current_tier]} ---")
        option_index += 1
        options.append(preset)
        tags: list[str] = []
        if preset.tier == rec_tier and preset_fits_vram(preset, gpu.vram_mb if gpu else None):
            tags.append("recommended")
        if gpu is not None and gpu.vram_mb is not None and not preset_fits_vram(preset, gpu.vram_mb):
            tags.append(f"needs ~{preset.min_vram_mb // 1024}GB+ VRAM")
        if preset.community_gguf:
            tags.append("community GGUF")
        suffix = f" [{', '.join(tags)}]" if tags else ""
        write(f"  {option_index}) {preset.label} — {preset.notes}{suffix}")

    valid = tuple(str(index) for index in range(1, len(options) + 1))
    default_choice = str(default_index)
    for index, preset in enumerate(options, start=1):
        if preset.tier == rec_tier and preset_fits_vram(preset, gpu.vram_mb if gpu else None):
            default_choice = str(index)
            break
    choice = _choose(read, "Choice", valid, default=default_choice)
    return options[int(choice) - 1]


def _preset_result(preset: ModelPreset, base_url: str) -> SetupResult:
    return SetupResult(
        cpu_only=False,
        preset_id=preset.id,
        base_url=base_url,
        chat_model=preset.chat_model_name,
        api_key=None,
        env_path=Path(),
    )


def _resolve_non_interactive(spec: str) -> SetupResult:
    normalized = spec.strip().lower()
    if normalized in {"cpu", "cpu-only", "cpu_only", "none", "off"}:
        return SetupResult(
            cpu_only=True,
            preset_id=None,
            base_url=None,
            chat_model=None,
            api_key=None,
            env_path=Path(),
        )

    deployment = "native"
    preset_part = normalized
    if ":" in normalized:
        deployment, preset_part = normalized.split(":", 1)

    preset_part = resolve_preset_id(preset_part)
    base_url = PODMAN_BASE_URL if deployment == "podman" else NATIVE_BASE_URL
    if preset_part == "custom":
        return SetupResult(
            cpu_only=False,
            preset_id="custom",
            base_url=base_url,
            chat_model="llama",
            api_key=None,
            env_path=Path(),
        )

    preset = ALL_PRESETS.get(preset_part)
    if preset is None:
        choices = (
            "cpu-only, gemma3-1b, gemma3-4b, gemma3-12b, gemma3n-e4b, "
            "qwen3-0.6b, qwen3-1.7b, qwen3-4b, qwen3-8b, qwen3-14b, custom "
            "(aliases: qwen3-1.5b, qwen3-3b, gemma3-3b)"
        )
        msg = f"Unknown preset {preset_part!r}. Choices: {choices}"
        raise ValueError(msg)
    return _preset_result(preset, base_url)


def _apply_result(env_path: Path, result: SetupResult) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if result.cpu_only:
        upsert_env_section(
            env_path,
            {
                "PROMPT_PIPER_LLM_ENABLED": "false",
                "PROMPT_PIPER_LOCAL_MODEL_PRESET": "cpu-only",
            },
        )
        return

    assert result.base_url is not None
    assert result.chat_model is not None
    values: dict[str, str] = {
        "PROMPT_PIPER_LLM_ENABLED": "true",
        "PROMPT_PIPER_LOCAL_BASE_URL": result.base_url,
        "PROMPT_PIPER_LOCAL_CHAT_MODEL": result.chat_model,
        "PROMPT_PIPER_LOCAL_EMBED_MODEL": result.chat_model,
        "PROMPT_PIPER_LOCAL_MODEL_PRESET": result.preset_id or "custom",
    }

    preset = ALL_PRESETS.get(result.preset_id or "")
    if preset is not None:
        values["PROMPT_PIPER_LOCAL_MODEL_PATH"] = f"./data/models/{preset.suggested_gguf_filename}"
        values["PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO"] = preset.huggingface_gguf_repo
        values["PROMPT_PIPER_LOCAL_MODEL_GGUF_FILE"] = preset.huggingface_gguf_file
        preamble = (
            *hf_cli_env_comments(repo_root=repo_root()),
            f"# Official publisher: {preset.publisher}",
            f"#   {hf_download_command(preset.huggingface_gguf_repo, preset.huggingface_gguf_file)}",
        )
        if preset.community_gguf and preset.weights_repo:
            preamble = (
                *preamble,
                f"# Community GGUF quant of official weights: {preset.weights_repo}",
            )
        if preset.requires_hf_license:
            preamble = (
                *preamble,
                "# Accept the Gemma license on Hugging Face, then: hf auth login",
            )
        upsert_env_section(
            env_path,
            values,
            preamble=preamble,
        )
        return
    elif result.api_key:
        values["PROMPT_PIPER_LOCAL_API_KEY"] = result.api_key

    upsert_env_section(env_path, values)


def _print_next_steps(write: PrintFn, result: SetupResult) -> None:
    write("\nSetup complete. Updated .env with your model preferences.\n")
    for line in lexicon_setup_command_lines(root=repo_root()):
        write(f"  {line}\n")
    if result.cpu_only:
        write(
            "CPU-only mode: clarification uses rule-based templates and ranking.\n"
            "You can re-run setup anytime: make setup\n"
        )
        return

    preset = ALL_PRESETS.get(result.preset_id or "")
    write("Next steps (run from the Nautilius Prompting Workbench repo root):\n")
    if preset is not None:
        if preset.requires_hf_license:
            write(
                "  1. Accept the Gemma license on Hugging Face, then: hf auth login\n"
            )
            write("  2. Download the GGUF (also offered automatically by make setup):\n")
        else:
            write("  1. Download the GGUF (also offered automatically by make setup):\n")
        write("       make download-model\n")
        write(
            f"       # or: {hf_download_command(preset.huggingface_gguf_repo, preset.huggingface_gguf_file)}\n"
        )
        write(
            "  2. Install llama.cpp so `llama-server` is on PATH "
            "(or set LLAMA_SERVER=/path/to/llama-server).\n"
        )
        write("  3. Start the stack:\n")
        write("       make ensure-llm   # GPU + GGUF + llama-server → starts local SLM\n")
        write("       make dev-api      # terminal 1\n")
        write("       make dev-web      # terminal 2\n")
        write("  4. Or use Podman with a copied model.gguf:\n")
        write(f"       cp data/models/{preset.suggested_gguf_filename} data/models/model.gguf\n")
        write("       podman compose -f infra/podman-compose.yml --profile llama up -d\n")
    else:
        write("  1. Start your OpenAI-compatible server on the host.\n")
        write(f"  2. Confirm it serves model {result.chat_model!r} at {result.base_url}\n")
        write("  3. make dev-api && make dev-web\n")
    write("\n  Re-run wizard: make setup\n")


def _choose(
    read: InputFn,
    label: str,
    valid: tuple[str, ...],
    *,
    default: str,
) -> str:
    while True:
        raw = read(f"{label} [{ '/'.join(valid) }] (default {default}): ").strip()
        if not raw:
            return default
        if raw in valid:
            return raw


def _prompt_default(read: InputFn, label: str, default: str) -> str:
    raw = read(f"{label} (default {default}): ").strip()
    return raw or default
