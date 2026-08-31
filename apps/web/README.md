# Web app (`apps/web/`)

React 18 + TypeScript + Vite single-page app for the **Nautilius Prompting Workbench** long-horizon coding-agent workflow UI (16-question contract, clarify → export).


## Structure

| Path | README | Purpose |
|------|--------|---------|
| `src/` | [src/README.md](src/README.md) | Application source |
| `vite.config.ts` | — | Dev server, API proxy, SPA routing for `/sessions/:id/*` (including `precision`) |
| `vite.proxy.ts` | — | Which `/sessions` paths are SPA vs API (non-GET always proxies) |
| `package.json` | — | `@prompt-piper/web` scripts and dependencies |

## Run

```bash
# From repo root — proxies /sessions, /registry, /health to :8010
make dev-web
```

Open http://127.0.0.1:5174. Production build is baked into `infra/Containerfile.web` (nginx).

## Test

```bash
npm test --prefix apps/web
# or: make test-web
```
