import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Button,
  Content,
  DataList,
  DataListCell,
  DataListItem,
  DataListItemCells,
  DataListItemRow,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Grid,
  GridItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  SearchInput,
} from "@patternfly/react-core";
import {
  queryKeys,
  useDeleteSession,
  useRegistryPrompts,
  useUpdateUserSettings,
  useUserSettings,
} from "../api/hooks";
import { formatApiError } from "../api/http";
import type { RecentSessionEntry } from "../api/types";
import { filterRegistryPrompts } from "../lib/registrySearch";
import { loadRecentSessions } from "../lib/recentSessions";
import { formatDate, sessionPath, sessionStepForState } from "../lib/sessionRouting";
import { ErrorBanner, LinkButton, LoadingState, PageFrame, PageHeader, Panel, WarningBanner } from "../components/ui";
import { StatusBadge } from "../components/StatusBadge";

export function DashboardPage() {
  const recent = useQuery({
    queryKey: queryKeys.recentSessions,
    queryFn: loadRecentSessions,
    staleTime: 0,
  });
  const registry = useRegistryPrompts();
  const userSettings = useUserSettings();
  const saveSettings = useUpdateUserSettings();
  const deleteSession = useDeleteSession();
  const [registrySearch, setRegistrySearch] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<RecentSessionEntry | null>(null);

  async function confirmDelete() {
    if (!pendingDelete) {
      return;
    }
    setDeleteError(null);
    try {
      await deleteSession.mutateAsync(pendingDelete.id);
      setPendingDelete(null);
    } catch (error) {
      setDeleteError(formatApiError(error, "Could not delete session."));
      setPendingDelete(null);
    }
  }

  const configuredEndpoints = useMemo(
    () => userSettings.data?.api_endpoints.filter((endpoint) => endpoint.configured) ?? [],
    [userSettings.data],
  );

  const sessionsWithWarnings = useMemo(
    () => (recent.data ?? []).filter((item) => item.similarityWarning),
    [recent.data],
  );

  const filteredRegistryPrompts = useMemo(
    () => filterRegistryPrompts(registry.data ?? [], registrySearch),
    [registry.data, registrySearch],
  );

  const visibleRegistryPrompts = filteredRegistryPrompts.slice(0, 8);
  const registrySearchActive = registrySearch.trim().length > 0;

  return (
    <PageFrame>
      <PageHeader
        title="Dashboard"
        subtitle="Recent design sessions and finalized prompts on this machine."
        actions={<LinkButton to="/sessions/new">New session</LinkButton>}
      />

      {sessionsWithWarnings.length > 0 && (
        <WarningBanner
          message={`${sessionsWithWarnings.length} recent session(s) reported similarity warnings.`}
        />
      )}

      {configuredEndpoints.length > 0 && (
        <Panel title="Default external API">
          <FormGroup label="Used for send-to-model unless overridden on the Complete step" fieldId="default-endpoint">
            <FormSelect
              id="default-endpoint"
              value={userSettings.data?.default_api_endpoint_id ?? ""}
              isDisabled={!userSettings.data || saveSettings.isPending}
              onChange={(_event, value) => {
                const next = value || null;
                if (!userSettings.data) {
                  return;
                }
                void saveSettings.mutateAsync({
                  llm_enabled: userSettings.data.llm_enabled,
                  precision_warning_threshold: userSettings.data.precision_warning_threshold,
                  similarity_time_scope_index: userSettings.data.similarity_time_scope_index,
                  clarification_versions: userSettings.data.clarification_versions,
                  default_api_endpoint_id: next,
                  ai_tooling_api_override: {
                    label: userSettings.data.ai_tooling_api_override.label,
                    base_url: userSettings.data.ai_tooling_api_override.base_url,
                    chat_model: userSettings.data.ai_tooling_api_override.chat_model,
                  },
                  ask_the_locals_api_override: {
                    label: userSettings.data.ask_the_locals_api_override.label,
                    base_url: userSettings.data.ask_the_locals_api_override.base_url,
                    chat_model: userSettings.data.ask_the_locals_api_override.chat_model,
                  },
                  api_endpoints: userSettings.data.api_endpoints.map((endpoint) => ({
                    id: endpoint.id,
                    label: endpoint.label,
                    base_url: endpoint.base_url,
                    chat_model: endpoint.chat_model,
                  })),
                });
              }}
            >
              <FormSelectOption value="" label="Select an endpoint" />
              {configuredEndpoints.map((endpoint) => (
                <FormSelectOption
                  key={endpoint.id}
                  value={endpoint.id}
                  label={endpoint.label || endpoint.chat_model || endpoint.base_url}
                />
              ))}
            </FormSelect>
          </FormGroup>
        </Panel>
      )}

      <Grid hasGutter md={6}>
        <GridItem>
          <Panel title="Recent sessions">
            {recent.isLoading && <LoadingState label="Loading recent sessions…" />}
            {recent.isError && (
              <ErrorBanner message={formatApiError(recent.error, "Could not load recent sessions.")} />
            )}
            {deleteError && <ErrorBanner message={deleteError} />}
            {!recent.isLoading && !recent.isError && (recent.data ?? []).length === 0 && (
              <Content component="p">No sessions tracked yet. Start a new prompt design session.</Content>
            )}
            {!recent.isLoading && !recent.isError && (recent.data ?? []).length > 0 && (
              <DataList aria-label="Recent sessions">
                {(recent.data ?? []).map((session) => (
                  <DataListItem key={session.id}>
                    <DataListItemRow>
                      <DataListItemCells
                        dataListCells={[
                          <DataListCell key="title" width={4}>
                            <Link to={sessionPath(session.id, sessionStepForState(session.state))}>
                              {session.title}
                            </Link>
                            <Content component="small">
                              Updated {formatDate(session.updatedAt)}
                              {session.promptId && (
                                <>
                                  {" · "}
                                  <code>{session.promptId}</code>
                                </>
                              )}
                            </Content>
                            {session.similarityWarning && (
                              <Content component="small">{session.similarityWarning}</Content>
                            )}
                          </DataListCell>,
                          <DataListCell key="actions" alignRight>
                            <StatusBadge state={session.state} />
                            <Button
                              variant="secondary"
                              size="sm"
                              isDisabled={deleteSession.isPending && deleteSession.variables === session.id}
                              aria-label={`Delete session ${session.title}`}
                              onClick={() => setPendingDelete(session)}
                            >
                              Delete
                            </Button>
                          </DataListCell>,
                        ]}
                      />
                    </DataListItemRow>
                  </DataListItem>
                ))}
              </DataList>
            )}
          </Panel>
        </GridItem>

        <GridItem>
          <Panel title="Finalized prompts">
            {registry.isLoading && <LoadingState label="Loading registry…" />}
            {registry.isError && (
              <ErrorBanner message={formatApiError(registry.error, "Registry unavailable.")} />
            )}
            {registry.data && registry.data.length > 0 && (
              <SearchInput
                placeholder="Search by title, prompt ID, abstract, or tags…"
                value={registrySearch}
                onChange={(_event, value) => setRegistrySearch(value)}
                aria-label="Search finalized prompts"
              />
            )}
            {registry.data && registry.data.length === 0 && (
              <Content component="p">No finalized prompts in the local registry yet.</Content>
            )}
            {registry.data && registry.data.length > 0 && filteredRegistryPrompts.length === 0 && (
              <Content component="p">No finalized prompts match your search.</Content>
            )}
            {visibleRegistryPrompts.length > 0 && (
              <DataList aria-label="Finalized prompts">
                {visibleRegistryPrompts.map((prompt) => (
                  <DataListItem key={prompt.prompt_id}>
                    <DataListItemRow>
                      <DataListItemCells
                        dataListCells={[
                          <DataListCell key="title">
                            <Link to={`/registry/${prompt.prompt_id}`}>{prompt.title}</Link>
                            <Content component="small">
                              <code>{prompt.prompt_id}</code>
                              {prompt.abstract && <> · {prompt.abstract}</>}
                            </Content>
                          </DataListCell>,
                          <DataListCell key="version" alignRight>
                            v{prompt.version}
                          </DataListCell>,
                        ]}
                      />
                    </DataListItemRow>
                  </DataListItem>
                ))}
              </DataList>
            )}
            {registry.data && registry.data.length > 0 && filteredRegistryPrompts.length > 8 && (
              <Link to={`/registry${registrySearchActive ? `?q=${encodeURIComponent(registrySearch.trim())}` : ""}`}>
                View all {filteredRegistryPrompts.length} matching prompts
              </Link>
            )}
            {registry.data &&
              registry.data.length > 8 &&
              !registrySearchActive &&
              filteredRegistryPrompts.length <= 8 && (
                <Link to="/registry">View all {registry.data.length} prompts</Link>
              )}
          </Panel>
        </GridItem>
      </Grid>

      <Modal
        variant={ModalVariant.small}
        isOpen={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        aria-labelledby="delete-session-title"
      >
        <ModalHeader title="Delete session" labelId="delete-session-title" />
        <ModalBody>
          {pendingDelete
            ? `Delete “${pendingDelete.title}”? This removes the session from this machine. Finalized registry prompts are kept.`
            : null}
        </ModalBody>
        <ModalFooter>
          <Button variant="danger" onClick={() => void confirmDelete()} isDisabled={deleteSession.isPending}>
            {deleteSession.isPending ? "Deleting…" : "Delete"}
          </Button>
          <Button variant="link" onClick={() => setPendingDelete(null)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    </PageFrame>
  );
}
