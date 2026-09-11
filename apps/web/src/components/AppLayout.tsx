import { Link, NavLink, Outlet } from "react-router-dom";
import { APP_NAME } from "@prompt-piper/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import logoUrl from "@assets/logo/logo.png";
import { fetchHealth, fetchLlmHealth } from "../api/sessions";

import { apiFetch, formatApiError } from "../api/http";

export function AppLayout() {
  const queryClient = useQueryClient();
  const offload = useMutation({
    mutationFn: () => apiFetch<{ message: string }>("/health/llm/offload", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["health"] }),
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: 1,
    refetchInterval: 60_000,
  });
  const llmHealth = useQuery({
    queryKey: ["health", "llm"],
    queryFn: fetchLlmHealth,
    retry: 1,
    refetchInterval: 15_000,
  });

  return (
    <div className="layout">
      <header className="layout-header">
        <div className="layout-header-start">
          <div className="layout-brand">
            <p className="eyebrow">Long Horizon Code Prompt Workbench</p>
            <Link to="/" className="brand-link">
              <img src={logoUrl} alt="" className="brand-logo" width={128} height={128} />
              <span className="sr-only">{APP_NAME}</span>
            </Link>
          </div>
        </div>
        <nav className="layout-nav" aria-label="Main">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            Dashboard
          </NavLink>
          <NavLink
            to="/sessions/new"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            New session
          </NavLink>
          <NavLink
            to="/registry"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Registry
          </NavLink>
        </nav>
        <div className="layout-header-end">
          <div className="api-pill" aria-live="polite">
            {health.isLoading && "API …"}
            {health.isError && <span className="pill-error">API offline</span>}
            {health.data && <span className="pill-ok">API {health.data.status}</span>}
            {llmHealth.data?.status === "ok" && (
              <span className="pill-ok" title={llmHealth.data.message}>
                Model ok
              </span>
            )}
            {llmHealth.data?.status === "disabled" && (
              <span className="pill-warn" title={llmHealth.data.message}>
                CPU mode
              </span>
            )}
            {llmHealth.data?.status === "unreachable" && (
              <span className="pill-error" title={llmHealth.data.message}>
                Model offline
              </span>
            )}
          </div>
          {llmHealth.data?.llm_enabled && (
            <button type="button" disabled={offload.isPending} onClick={() => offload.mutate()}
              title="Stop the managed local model server to free GPU memory">
              {offload.isPending ? "Offloading…" : "Offload model"}
            </button>
          )}
          {offload.isError && <span role="alert">{formatApiError(offload.error)}</span>}
          {offload.isSuccess && <span role="status">{offload.data.message}</span>}
          <Link to="/settings" className="settings-gear" aria-label="Settings" title="Settings">
            ⚙
          </Link>
        </div>
      </header>
      <main className="layout-main">
        <Outlet />
      </main>
    </div>
  );
}
