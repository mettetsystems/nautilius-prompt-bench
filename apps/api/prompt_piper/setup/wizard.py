from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from prompt_piper.setup.catalog import (
    ALL_PRESETS,
    GEMMA3_PRESETS,
    GEMMA3N_PRESETS,
    NATIVE_BASE_URL,
    PODMAN_BASE_URL,
    QWEN3_PRESETS,
    TIER_LABELS,
    ModelPreset,
    ModelTier,
    preset_fits_vram,
    resolve_preset_id,
)
from prompt_piper.setup.endpoint_discovery import (
    ModelEndpoint,
    discover_endpoints,
    local_endpoint_conflict,
    normalize_base_url,
    probe_endpoint,
)
from prompt_piper.setup.env_writer import load_env, upsert_env_section
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
    allow_cpu: bool = False
    local_source: Path | None = None
    deployment_profile: str = "manual"


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
    settings = load_env(target_env)
    endpoints: list[ModelEndpoint] = []
    if non_interactive:
        result = _resolve_non_interactive(non_interactive)
        if not result.cpu_only and result.preset_id != "custom":
            endpoints = discover_endpoints(settings)
    else:
        write("Checking for existing model endpoints (model metadata only)...")
        endpoints = discover_endpoints(settings)
        result = _offer_existing_endpoint(endpoints, read, write)
        if result is None:
            result = _run_interactive(read, write)

    if not result.cpu_only and result.preset_id != "custom":
        # The user may have stopped the other server while choosing a model.
        if local_endpoint_conflict(endpoints) and (
            conflict := local_endpoint_conflict(discover_endpoints(settings))
        ):
            raise ValueError(conflict)
        if not non_interactive:
            result = _choose_model_source(result, read, write)
    _apply_result(target_env, result)
    target_env.chmod(0o600)
    _print_next_steps(write, result)
    return result


def _banner() -> str:
    return (
        "\nNautilius Prompting Workbench setup — local model configuration\n"
        "================================================\n"
        "Clarification and draft generation can use a local OpenAI-compatible\n"
        "server (Project Maya, vLLM, llama.cpp, etc.) or use rule-based\n"
        "fallbacks. Similarity search embeddings stay separate.\n"
    )


def _read_api_key(read: InputFn, *, required: bool = False) -> str | None:
    from getpass import getpass

    hint = "required by this server" if required else "optional"
    prompt = f"API key ({hint}; stored in .env): "
    return (getpass if read is input else read)(prompt).strip() or None


def _endpoint_model(endpoint: ModelEndpoint, read: InputFn, write: PrintFn) -> str:
    if len(endpoint.models) == 1:
        write(f"Using model: {endpoint.models[0]}")
        return endpoint.models[0]
    if endpoint.models:
        for index, model in enumerate(endpoint.models, 1):
            write(f"  {index}) {model}")
        choice = _choose(
            read, "Model to use", tuple(str(i) for i in range(1, len(endpoint.models) + 1)),
            default="1",
        )
        return endpoint.models[int(choice) - 1]
    write(
        f"Model list unavailable: {endpoint.status}. "
        "Enter a model already served by this endpoint."
    )
    model = read("Model ID: ").strip()
    if not model:
        raise ValueError("A model ID is required.")
    return model


def _offer_existing_endpoint(
    endpoints: list[ModelEndpoint], read: InputFn, write: PrintFn
) -> SetupResult | None:
    if not endpoints:
        write("No endpoints found on the checked addresses. Enter a custom URL below if needed.")
        return None
    write("Existing model endpoints or services requiring verification:")
    for index, endpoint in enumerate(endpoints, 1):
        detail = ", ".join(endpoint.models) or endpoint.status
        write(f"  {index}) {endpoint.base_url} — {detail}")
    write("Reusing a server avoids loading another model into RAM/VRAM.")
    while True:
        answer = read("Use an existing model endpoint? [Y/n]: ").strip().lower()
        if answer in {"", "y", "yes"}:
            break
        if answer in {"n", "no"}:
            write("Local model startup stays blocked while another local server is detected.")
            return None
    index = "1"
    if len(endpoints) > 1:
        index = _choose(
            read, "Endpoint", tuple(str(i) for i in range(1, len(endpoints) + 1)), default="1"
        )
    endpoint = endpoints[int(index) - 1]
    if endpoint.status.startswith("credentials required"):
        key = _read_api_key(read, required=True)
        verified = probe_endpoint(endpoint.base_url, key)
        if verified is None or verified.status.startswith("credentials required"):
            raise ValueError("Could not access the endpoint model list. Check its URL and API key.")
        endpoint = verified
    elif not endpoint.api_key:
        # Some servers expose a public model list but protect chat completions.
        endpoint = replace(endpoint, api_key=_read_api_key(read))
    model = _endpoint_model(endpoint, read, write)
    base_url = endpoint.base_url
    address = urlsplit(base_url)
    if address.hostname in {"localhost", "127.0.0.1", "::1"} and (
        _ask_deployment(read, write) == "podman"
    ):
        host = "host.containers.internal"
        if address.port:
            host += f":{address.port}"
        base_url = urlunsplit((address.scheme, host, address.path, "", ""))
    write("Reusing the selected endpoint. Local model downloads and auto-start are disabled.")
    return SetupResult(False, "custom", base_url, model, endpoint.api_key, Path())


def _custom_endpoint(read: InputFn, write: PrintFn) -> SetupResult:
    write("Connect to Project Maya, vLLM, llama.cpp, or another OpenAI-compatible server.")
    base_url = normalize_base_url(read("Existing/remote OpenAI-compatible base URL: "))
    key = _read_api_key(read)
    endpoint = probe_endpoint(base_url, key)
    model = _endpoint_model(
        endpoint or ModelEndpoint(base_url, status="unreachable or model listing unsupported"),
        read, write,
    )
    return SetupResult(False, "custom", base_url, model, key, Path())


def _choose_model_source(result: SetupResult, read: InputFn, write: PrintFn) -> SetupResult:
    from dataclasses import replace
    from getpass import getpass

    from prompt_piper.setup.model_sources import load_preferences, local_gguf, save_preferences

    prefs = load_preferences()
    write("Model source: 1) Hugging Face download  2) Import from local repository/folder")
    choice = _choose(read, "Source", ("1", "2"), default="2" if prefs.get("local_repo") else "1")
    if choice == "1":
        token = (getpass if read is input else read)("Hugging Face token (optional, hidden; Enter keeps saved token): ").strip()
        if token:
            save_preferences(hf_token=token)
        return result
    location = read(f"Local repository directory or GGUF file [{prefs.get('local_repo', '')}]: ").strip() or prefs.get("local_repo", "")
    preset = ALL_PRESETS[result.preset_id]
    source = local_gguf(location, preset.suggested_gguf_filename, read, write)
    # Check the actual local file; a custom file may be larger than the recommended preset.
    from prompt_piper.setup.hardware import scan_hardware
    report = scan_hardware()
    weights_mb = source.stat().st_size // 1048576
    ram = report["available_ram_mb"]
    free = (report["selected_gpu"] or {}).get("free_vram_mb")
    required_ram = required_vram = weights_mb + 2048
    if result.deployment_profile == "specification":
        from prompt_piper.setup.deployment_budget import plan_model_file

        plan = plan_model_file(
            source, result.preset_id, (report["selected_gpu"] or {}).get("vram_mb")
        )
        required_ram, required_vram = plan["required_ram_mb"], plan["required_vram_mb"]
    if ram is None or ram < required_ram:
        raise ValueError("Not enough verified available RAM for this GGUF file")
    if not result.allow_cpu and (free is None or free < required_vram):
        raise ValueError("Not enough verified free VRAM for this GGUF file; choose the CPU/low option or remote")
    save_preferences(local_repo=location)
    return replace(result, local_source=source, chat_model=source.stem)


def _run_interactive(read: InputFn, write: PrintFn) -> SetupResult:
    from dataclasses import replace

    from prompt_piper.setup.hardware import print_hardware, scan_hardware

    report = scan_hardware()
    print_hardware(report, write)
    write("  0) Rule-based mode (no model)\n  5) Advanced manual model catalog")
    default = {"low": "1", "mid": "2", "high": "3", "remote": "4"}[report["recommended"]]
    while True:
        choice = _choose(read, "Model choice", ("0", "1", "2", "3", "4", "5"), default=default)
        if choice == "0":
            return SetupResult(True, None, None, None, None, Path())
        if choice == "5":
            return _run_advanced(read, write)
        if choice == "4":
            try:
                return _custom_endpoint(read, write)
            except ValueError as exc:
                write(str(exc))
                continue
        option = report["local_options"][int(choice)-1]
        if option["status"] == "unavailable":
            write(option["reason"])
            continue
        deployment = _ask_deployment(read, write)
        result = _preset_result(ALL_PRESETS[option["preset"]], PODMAN_BASE_URL if deployment == "podman" else NATIVE_BASE_URL)
        return replace(
            result, allow_cpu=option["status"] == "cpu", deployment_profile="specification"
        )


def _run_advanced(read: InputFn, write: PrintFn) -> SetupResult:
    write("Manual deployment: catalog size tiers do not validate the 32K specification budget.")
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

    if family_choice == "4":
        return _custom_endpoint(read, write)

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
    preset = _choose_preset(read, write, QWEN3_PRESETS, gpu=gpu, default_index=2)
    return _preset_result(preset, base_url)


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
                "PROMPT_PIPER_AUTO_START_LLM": "false",
                "PROMPT_PIPER_ALLOW_CPU_LLM": "false",
            },
        )
        return

    assert result.base_url is not None
    assert result.chat_model is not None
    values: dict[str, str] = {
        "PROMPT_PIPER_LLM_ENABLED": "true",
        "PROMPT_PIPER_AUTO_START_LLM": "false" if result.preset_id == "custom" else "true",
        "PROMPT_PIPER_ALLOW_CPU_LLM": str(result.allow_cpu).lower(),
        "PROMPT_PIPER_LOCAL_BASE_URL": result.base_url,
        "PROMPT_PIPER_LOCAL_CHAT_MODEL": result.chat_model,
        "PROMPT_PIPER_LOCAL_EMBED_MODEL": result.chat_model,
        "PROMPT_PIPER_LOCAL_MODEL_PRESET": result.preset_id or "custom",
        "PROMPT_PIPER_DEPLOYMENT_PROFILE": result.deployment_profile,
    }
    if result.deployment_profile == "specification":
        # Clear stale short-context/partial-offload choices when choosing this workload.
        values["PROMPT_PIPER_LLAMA_N_CTX"] = "32768"
        values["PROMPT_PIPER_LLAMA_GPU_LAYERS"] = "0" if result.allow_cpu else "999"

    preset = ALL_PRESETS.get(result.preset_id or "")
    if preset is not None:
        values["PROMPT_PIPER_LOCAL_MODEL_PATH"] = f"./data/models/{preset.suggested_gguf_filename}"
        values["PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO"] = preset.huggingface_gguf_repo
        values["PROMPT_PIPER_LOCAL_MODEL_GGUF_FILE"] = preset.huggingface_gguf_file
        if result.local_source is not None:
            values["PROMPT_PIPER_LOCAL_MODEL_SOURCE"] = "local"
            values["PROMPT_PIPER_LOCAL_MODEL_SOURCE_PATH"] = str(result.local_source)
            values["PROMPT_PIPER_LOCAL_MODEL_PATH"] = str(repo_root() / "data" / "models" / result.local_source.name)
        else:
            values["PROMPT_PIPER_LOCAL_MODEL_SOURCE"] = "huggingface"
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
    else:
        # An explicitly unauthenticated selection must not inherit an old shell key.
        values["PROMPT_PIPER_LOCAL_API_KEY"] = result.api_key or ""

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
        write(f"  1. Using model {result.chat_model!r} at {result.base_url}\n")
        write("  2. Keep that server running; Nautilius will not download or start another model.\n")
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
