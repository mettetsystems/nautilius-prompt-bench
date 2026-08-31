# Applications (`apps/`)

Runnable application packages for Nautilius Prompting Workbench. Everything user-facing or API-facing lives here.

| Package | Role |
|---------|------|
| [`api/`](api/README.md) | FastAPI backend — session workflow, registry, similarity, optimization, precision, export, send-to-model |
| [`web/`](web/README.md) | React + Vite SPA — clarification through export and complete (including send-to-model) |

## Run locally

```bash
# Terminal 1 — API on :8010 (from repo root)
make dev-api

# Terminal 2 — web UI on :5174 with API proxy
make dev-web
```

Stop the native processes (and Podman/Quadlets if they are running) with `make shutdown`.

See the [root README](../README.md) for Podman, setup wizard, and environment variables.
