import { NavLink, Outlet, useLocation } from "react-router-dom";
import { APP_NAME } from "@prompt-piper/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Flex,
  FlexItem,
  Label,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadMain,
  Nav,
  NavItem,
  NavList,
  Page,
  Spinner,
} from "@patternfly/react-core";
import CogIcon from "@patternfly/react-icons/dist/esm/icons/cog-icon";
import logoUrl from "@assets/logo/logo.png";
import { fetchHealth, fetchLlmHealth } from "../api/sessions";
import { apiFetch, formatApiError } from "../api/http";
import { LinkButton } from "./ui";

export function AppLayout() {
  const queryClient = useQueryClient();
  const { pathname } = useLocation();
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
    <Page
      horizontalSubnav={
        <Nav aria-label="Main" variant="horizontal-subnav">
          <NavList>
            <NavItem isActive={pathname === "/"}>
              <NavLink to="/" end>
                Dashboard
              </NavLink>
            </NavItem>
            <NavItem isActive={pathname.startsWith("/sessions/new")}>
              <NavLink to="/sessions/new">New session</NavLink>
            </NavItem>
            <NavItem isActive={pathname === "/registry" || pathname.startsWith("/registry/")}>
              <NavLink to="/registry">Registry</NavLink>
            </NavItem>
          </NavList>
        </Nav>
      }
      masthead={
        <Masthead display={{ default: "stack", lg: "inline" }}>
          <MastheadMain>
            <MastheadBrand>
              <Flex
                direction={{ default: "column" }}
                spaceItems={{ default: "spaceItemsNone" }}
                alignItems={{ default: "alignItemsFlexStart" }}
              >
                <p className="eyebrow">Long Horizon Code Prompt Workbench</p>
                <NavLink to="/" end className="brand-home">
                  <img src={logoUrl} alt="" className="brand-logo" width={128} height={128} />
                  <span className="sr-only">{APP_NAME}</span>
                </NavLink>
              </Flex>
            </MastheadBrand>
          </MastheadMain>
          <MastheadContent>
            <Flex
              alignItems={{ default: "alignItemsCenter" }}
              flexWrap={{ default: "wrap" }}
              spaceItems={{ default: "spaceItemsSm" }}
            >
              <FlexItem>
                <Flex spaceItems={{ default: "spaceItemsSm" }} aria-live="polite">
                  {health.isLoading && (
                    <FlexItem>
                      <Spinner size="sm" aria-label="API …" />
                    </FlexItem>
                  )}
                  {health.isError && <Label color="red">API offline</Label>}
                  {health.data && <Label color="green" status="success">API {health.data.status}</Label>}
                  {llmHealth.data?.status === "ok" && (
                    <Label color="green" status="success" title={llmHealth.data.message}>
                      Model ok
                    </Label>
                  )}
                  {llmHealth.data?.status === "disabled" && (
                    <Label color="orange" status="warning" title={llmHealth.data.message}>
                      CPU mode
                    </Label>
                  )}
                  {llmHealth.data?.status === "unreachable" && (
                    <Label color="red" status="danger" title={llmHealth.data.message}>
                      Model offline
                    </Label>
                  )}
                </Flex>
              </FlexItem>
              {llmHealth.data?.llm_enabled && (
                <Button
                  variant="secondary"
                  isDisabled={offload.isPending}
                  onClick={() => offload.mutate()}
                  title="Stop the managed local model server to free GPU memory"
                >
                  {offload.isPending ? "Offloading…" : "Offload model"}
                </Button>
              )}
              {offload.isError && <span role="alert">{formatApiError(offload.error)}</span>}
              {offload.isSuccess && <span role="status">{offload.data.message}</span>}
              <LinkButton
                to="/settings"
                className="settings-link"
                variant="plain"
                aria-label="Settings"
                title="Settings"
                icon={<CogIcon />}
              />
            </Flex>
          </MastheadContent>
        </Masthead>
      }
    >
      <Outlet />
    </Page>
  );
}
