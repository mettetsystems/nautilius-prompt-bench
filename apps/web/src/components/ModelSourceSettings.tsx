import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Content, Form } from "@patternfly/react-core";
import { apiFetch, formatApiError } from "../api/http";
import { ErrorBanner, Panel, SuccessBanner, TextField } from "./ui";

type SourceSettings = { hf_token_configured: boolean; local_repo: string };

export function ModelSourceSettings() {
  const source = useQuery({
    queryKey: ["model-source"],
    queryFn: () => apiFetch<SourceSettings>("/settings/model-source"),
  });
  const [token, setToken] = useState("");
  const [repo, setRepo] = useState("");
  const [clearToken, setClearToken] = useState(false);
  useEffect(() => {
    if (source.data) {
      setRepo(source.data.local_repo);
    }
  }, [source.data]);
  const save = useMutation({
    mutationFn: () =>
      apiFetch<SourceSettings>("/settings/model-source", {
        method: "PUT",
        body: JSON.stringify({ hf_token: token || null, local_repo: repo, clear_token: clearToken }),
      }),
    onSuccess: () => {
      setToken("");
      setClearToken(false);
      void source.refetch();
    },
  });
  return (
    <Panel title="Model sources">
      <Form>
        <TextField
          id="hf-token"
          label="Hugging Face token (optional)"
          type="password"
          autoComplete="off"
          value={token}
          onChange={setToken}
          placeholder={source.data?.hf_token_configured ? "Token saved — leave blank to keep" : "hf_…"}
        />
        <Checkbox
          id="clear-hf-token"
          label="Remove saved token"
          isChecked={clearToken}
          onChange={(_event, checked) => setClearToken(checked)}
        />
        <TextField
          id="local-model-repo"
          label="Local model repository or GGUF file"
          value={repo}
          onChange={setRepo}
          placeholder="/path/to/local/models"
        />
        <Content component="p">
          These preferences are used by setup and model import. Local folders must be visible to the API; Git LFS weights must already be downloaded. Saving does not download or load a model.
        </Content>
        <Button
          variant="secondary"
          isDisabled={save.isPending || source.isPending || source.isError}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : "Save model sources"}
        </Button>
        {(save.error || source.error) && <ErrorBanner message={formatApiError(save.error || source.error)} />}
        {save.isSuccess && (
          <SuccessBanner message="Model source preferences saved. Run setup to choose your model and import source." />
        )}
      </Form>
    </Panel>
  );
}
