# Web source (`src/`)

Frontend application root. Routed by `App.tsx`; workflow steps use `SessionWorkflowPage` + step-specific pages.

| Directory | README | Purpose |
|-----------|--------|---------|
| `pages/` | [pages/README.md](pages/README.md) | Route-level screens (clarify, edit, similarity, …) |
| `components/` | [components/README.md](components/README.md) | Reusable UI — stepper, banners, agent-contract card |
| `api/` | [api/README.md](api/README.md) | HTTP client, React Query hooks, shared types |
| `lib/` | [lib/README.md](lib/README.md) | Routing helpers, recent sessions, clarification UX |
| `test/` | [test/README.md](test/README.md) | Vitest setup |

| File | Role |
|------|------|
| `main.tsx` | React root mount |
| `App.tsx` | React Router routes (workflow steps + `/sessions/:id/precision`) |
| `index.css` | Global styles and workflow stepper |
