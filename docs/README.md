# Documentation (`docs/`)

Design and operator guides for **Nautilius Prompting Workbench**, the local-first long-horizon coding-agent prompting workbench. The [root README](../README.md) is the quick-start; these go deeper.

| Document | Audience | Contents |
|----------|----------|----------|
| [architecture.md](architecture.md) | Developers | 16-question agent contract, state machine, clarity-first optimizer, quality gate |
| [user-workflow.md](user-workflow.md) | Users / integrators | Step-by-step session API and UI flow |
| [developer-guide.md](developer-guide.md) | Contributors | Coding RequirementCard, testing, adding routes |
| [local-setup.md](local-setup.md) | Fedora operators | Native vs Podman setup detail |
| [privacy-model.md](privacy-model.md) | Security review | What stays local, external inference gate |
| [registry-format.md](registry-format.md) | Integrators | `metadata.yaml`, coding specs, artifact layout |

Folder-level READMEs under `apps/`, `data/`, etc. describe **where code and runtime files live**; these docs describe **how the product behaves**.

**Upgrade note:** the 16-question agent-contract `RequirementCard` is not compatible with older six-dimension session JSON — clear `./data/sessions/` after upgrading.
