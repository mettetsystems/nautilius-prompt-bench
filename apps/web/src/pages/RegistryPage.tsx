import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Content, SearchInput } from "@patternfly/react-core";
import { Table, Tbody, Td, Th, Thead, Tr } from "@patternfly/react-table";
import { useRegistryPrompts } from "../api/hooks";
import { formatApiError } from "../api/http";
import { filterRegistryPrompts } from "../lib/registrySearch";
import { formatDate } from "../lib/sessionRouting";
import { ErrorBanner, LoadingState, PageFrame, PageHeader, Panel } from "../components/ui";

export function RegistryPage() {
  const registry = useRegistryPrompts();
  const [searchParams] = useSearchParams();
  const [registrySearch, setRegistrySearch] = useState(() => searchParams.get("q") ?? "");

  const filteredPrompts = useMemo(
    () => filterRegistryPrompts(registry.data ?? [], registrySearch),
    [registry.data, registrySearch],
  );
  const searchActive = registrySearch.trim().length > 0;
  const totalCount = registry.data?.length ?? 0;

  return (
    <PageFrame>
      <PageHeader
        title="Registry"
        subtitle="Browse finalized prompts stored under data/registry on this machine."
      />
      <Panel>
        {registry.isLoading && <LoadingState label="Loading registry…" />}
        {registry.isError && (
          <ErrorBanner message={formatApiError(registry.error, "Could not load registry.")} />
        )}
        {registry.data && totalCount === 0 && <Content component="p">No finalized prompts yet.</Content>}
        {totalCount > 0 && (
          <SearchInput
            placeholder="Search by title, prompt ID, abstract, or tags…"
            value={registrySearch}
            onChange={(_event, value) => setRegistrySearch(value)}
            aria-label="Search finalized prompts"
          />
        )}
        {searchActive && totalCount > 0 && (
          <Content component="small">
            Showing {filteredPrompts.length} of {totalCount} prompts
          </Content>
        )}
        {totalCount > 0 && filteredPrompts.length === 0 && (
          <Content component="p">No finalized prompts match your search.</Content>
        )}
        {filteredPrompts.length > 0 && (
          <Table aria-label="Finalized prompts">
            <Thead>
              <Tr>
                <Th>Title</Th>
                <Th>Prompt ID</Th>
                <Th>Version</Th>
                <Th>Updated</Th>
              </Tr>
            </Thead>
            <Tbody>
              {filteredPrompts.map((prompt) => (
                <Tr key={prompt.prompt_id}>
                  <Td>
                    <Link to={`/registry/${prompt.prompt_id}`}>{prompt.title}</Link>
                  </Td>
                  <Td>
                    <code>{prompt.prompt_id}</code>
                  </Td>
                  <Td>{prompt.version}</Td>
                  <Td>{formatDate(prompt.updated_at)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Panel>
    </PageFrame>
  );
}
