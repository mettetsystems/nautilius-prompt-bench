# Nautilius Prompting Workbench Quadlets (Fedora / rootless Podman)

Run Nautilius Prompting Workbench as **persistent user systemd services** that start at boot.

Quadlets live in `~/.config/containers/systemd/` and are managed with `systemctl --user`.

## Prerequisites

```bash
sudo dnf install podman podman-compose
loginctl enable-linger "$USER"   # start containers at boot without logging in
```

Clone or copy the repo to `~/nautilius-prompt-bench` (Quadlet paths assume `%h/nautilius-prompt-bench`).

## Quick install

### One-shot Make targets (recommended)

From the repo root, these build images, run tests, install Quadlets, enable systemd user units (with linger), wait for `/health`, and open the default browser:

```bash
make persistent-install-cpu   # CPU-only (no llama profile)
make persistent-install-ai    # Local SLM via compose llama profile (default: qwen3-1.7b)
```

Overrides:

```bash
./scripts/persistent-install.sh ai --preset qwen3-4b
SKIP_TESTS=1 SKIP_BROWSER=1 make persistent-install-cpu
SKIP_BUILD=1 make persistent-install-cpu   # after make export / podman load
```

### Manual Quadlet copy

```bash
chmod +x scripts/install-quadlets.sh scripts/init-db-quadlet.sh
./scripts/install-quadlets.sh --method compose
# AI stack with llama profile:
./scripts/install-quadlets.sh --method compose --profiles llama --start
```

Then follow the printed steps (build, `daemon-reload`, enable service, init DB) when not using `--start`.

---

## Method A: Compose Quadlet (recommended)

Uses the existing [`../podman-compose.yml`](../podman-compose.yml) stack.

### Install

```bash
mkdir -p ~/.config/containers/systemd
cp infra/quadlets/prompt-piper.compose ~/.config/containers/systemd/
```

Or: `./scripts/install-quadlets.sh --method compose`

### One-time setup

```bash
cd ~/nautilius-prompt-bench
cp .env.example .env   # first time only

mkdir -p ~/Documents/Nautilius/{exports,registry,audit}
mkdir -p data/{postgres,model-cache}

podman compose -f infra/podman-compose.yml build
```

### Enable at boot

```bash
systemctl --user daemon-reload
systemctl --user enable --now prompt-piper.service
./scripts/init-db.sh
```

### Verify

```bash
systemctl --user status prompt-piper.service
curl http://127.0.0.1:8000/health
```

Open http://127.0.0.1:5173 in a browser.

### After code changes

```bash
cd ~/nautilius-prompt-bench
podman compose -f infra/podman-compose.yml build
systemctl --user restart prompt-piper.service
```

---

## Method B: Individual container Quadlets

Separate units for postgres, API, and web — useful if you want explicit control or pinned local image tags.

### Install

```bash
./scripts/install-quadlets.sh --method containers
```

This copies:

| File | systemd unit |
|------|----------------|
| `prompt-piper.network` | `prompt-piper-network.service` |
| `prompt-piper-postgres.container` | `prompt-piper-postgres.service` |
| `prompt-piper-api.container` | `prompt-piper-api.service` |
| `prompt-piper-web.container` | `prompt-piper-web.service` |

### Build tagged images

```bash
cd ~/nautilius-prompt-bench
podman build -f infra/Containerfile.api -t localhost/prompt-piper-api:latest .
podman build -f infra/Containerfile.web \
  --build-arg VITE_API_BASE_URL=http://127.0.0.1:8000 \
  -t localhost/prompt-piper-web:latest .
```

### Enable at boot

```bash
systemctl --user daemon-reload
systemctl --user enable --now prompt-piper-network.service
systemctl --user enable --now prompt-piper-postgres.service
systemctl --user enable --now prompt-piper-api.service
systemctl --user enable --now prompt-piper-web.service
./scripts/init-db-quadlet.sh
```

---

## What persists across reboots

| Data | Host path |
|------|-----------|
| Exports, registry, audit | `~/Documents/Nautilius/` |
| PostgreSQL | `~/nautilius-prompt-bench/data/postgres/` |
| Embedding model cache | `~/nautilius-prompt-bench/data/model-cache/` |
| Configuration | `~/nautilius-prompt-bench/.env` |

Containers are recreated on start; data stays on the host via bind mounts.

---

## Common commands

```bash
# Status
systemctl --user status prompt-piper.service          # compose method
systemctl --user status 'prompt-piper-*.service'      # container method

# Logs
journalctl --user -u prompt-piper.service -f
journalctl --user -u prompt-piper-api.service -f

# Stop / start
systemctl --user stop prompt-piper.service
systemctl --user start prompt-piper.service

# Disable boot start
systemctl --user disable prompt-piper.service
```

---

## Custom repo location

If the repo is not at `~/nautilius-prompt-bench`, edit paths in the Quadlet files before installing:

- `%h/nautilius-prompt-bench` → your clone path (Quadlet `%h` = home directory)
- Or set `WorkingDirectory` / `File` in `prompt-piper.compose` accordingly

---

## Optional: llama.cpp server

The compose file includes an optional `llama` profile. With compose Quadlet you can extend the stack manually:

```bash
podman compose -f infra/podman-compose.yml --profile llama up -d
```

A dedicated llama Quadlet is not included yet; add one following the same pattern as `prompt-piper-postgres.container`.

---

## Troubleshooting

### Services don't start at boot

```bash
loginctl show-user "$USER" -p Linger   # should be Linger=yes
loginctl enable-linger "$USER"
```

### SELinux (Fedora)

Bind mounts use the `:Z` suffix in Quadlet `Volume=` lines. If writes fail:

```bash
ls -Z ~/Documents/Nautilius
systemctl --user restart prompt-piper-api.service
```

### API can't reach Postgres (container method)

Ensure all containers use `Network=prompt-piper.network` and postgres is healthy:

```bash
podman exec prompt-piper-postgres pg_isready -U prompt_piper
```

### Rebuild web after changing API URL

`VITE_API_BASE_URL` is baked in at web **build** time. Rebuild the web image and restart.

---

## Uninstall

```bash
systemctl --user disable --now prompt-piper.service   # or individual units
rm -f ~/.config/containers/systemd/prompt-piper*
systemctl --user daemon-reload
```

Data under `~/Documents/Nautilius` and `~/nautilius-prompt-bench/data/` is not removed automatically.
