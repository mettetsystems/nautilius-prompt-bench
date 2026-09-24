# Native Mac installation

This installation targets an Apple Silicon MacBook Air (M3, 2024), macOS Tahoe,
16 GB unified memory, and 237 GB available SSD storage. It runs the API, browser
UI, SQLite, and llama.cpp directly on macOS. Metal lets llama.cpp use the Apple
GPU and shared CPU/GPU memory. Storage capacity is separate from unified memory.

## Install

1. Install [Homebrew](https://brew.sh) using its official instructions. Use a
   native Terminal window, with Rosetta disabled.
2. Copy or clone this version of the repository to the Mac. Use a fresh checkout;
   do not copy `.env`, `node_modules`, Python `.venv`, or private runtime data from
   a Linux installation.
3. In Terminal, change into the repository folder and run:

   ```bash
   bash scripts/install-macos.sh
   bash scripts/start-macos.sh
   ```

4. Open <http://127.0.0.1:5174>.

The installer installs native Homebrew Python 3.12, Node 22, and llama.cpp;
installs the app and embedding dependencies; builds the UI; creates a Mac `.env`;
and downloads WordNet and the official Qwen3 1.7B Q8_0 GGUF. Internet access is
needed during setup. The embedding model may download on its first use. The full
optional semantic lexicon index is not built automatically.

An existing non-Mac `.env` is preserved and the installer stops before changing
it. Back it up yourself or use a fresh checkout. Re-running the installer keeps
the Mac `.env` and skips an already downloaded model. Do not run `make setup`
afterward unless you intend to replace the Mac profile.

## Memory and model settings

The default is a light 1.7B model with a 4,096-token context (input plus output).
Embeddings run on CPU; all processes still share the same 16 GB RAM. Automatic
Metal tuning uses half of installed RAM as a planning allowance, leaving room
for macOS, the browser, and the application. This is an estimate, not measured
free GPU memory or a hard allocation limit. Other applications and context size
still affect memory pressure. Do not disable macOS memory protections.

For longer agent contracts, increase `PROMPT_PIPER_LLAMA_N_CTX` to `8192` in
`.env`, stop the app and model, then restart. Watch Activity Monitor → Memory;
reduce context or close other applications if memory pressure rises. Larger
models are optional experiments, not required for this light inference profile.

Press Ctrl+C in the launch terminal to stop the API and web UI. The local model
stays available for reuse; release its memory with:

```bash
make llama-down
```

The launcher serves the built UI locally using Vite preview. This is a local
workstation installation, not a signed `.app`/DMG, public server, or login service.
Session data remains in `data/`; exports use the application's configured paths.
External inference is disabled by default.

## Verify Metal

```bash
/opt/homebrew/bin/llama-server --list-devices
make ensure-llm
curl http://127.0.0.1:8010/health
```

The first command should list a Metal device; startup should report `APPLE GPU
(Apple M3)` and a positive `-ngl` value. Inspect `data/llama-server.log` for actual
Metal layer offloading. If Metal is missing, check that Homebrew, Python, and the
terminal are native arm64, then reinstall `llama.cpp` with Homebrew. Startup checks
an actual inference request and fails if the model cannot respond.

Backend detection and launcher behavior have automated tests runnable on Linux.
Actual Tahoe/M3 installation, performance, and memory pressure still require a
smoke test on the target Mac; no Mac hardware was available during implementation.

References: [llama.cpp Metal build support](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md),
[Homebrew llama.cpp](https://formulae.brew.sh/formula/llama.cpp),
[official Qwen3 1.7B GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF).
