# `@prompt-piper/shared`

Minimal shared TypeScript types for **Nautilius Prompting Workbench**, published as a local workspace package.

| File | Role |
|------|------|
| `src/index.ts` | `APP_NAME` (`Nautilius Prompting Workbench`), `APP_TAGLINE`, health response types |
| `package.json` | Package name and build config |
| `tsconfig.json` | TypeScript project settings |

Imported by `apps/web` for branding, health checks, and API typing alignment. Session-specific DTOs (including the nested coding `RequirementCard`) live in `apps/web/src/api/types.ts`; extend this package when types are shared across multiple frontends.
