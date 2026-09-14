import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch, formatApiError } from "../api/http";
import { Panel } from "./ui";

type SourceSettings = { hf_token_configured: boolean; local_repo: string };
export function ModelSourceSettings() {
  const source = useQuery({ queryKey: ["model-source"], queryFn: () => apiFetch<SourceSettings>("/settings/model-source") });
  const [token, setToken] = useState("");
  const [repo, setRepo] = useState("");
  const [clearToken, setClearToken] = useState(false);
  useEffect(() => { if (source.data) setRepo(source.data.local_repo); }, [source.data]);
  const save = useMutation({
    mutationFn: () => apiFetch<SourceSettings>("/settings/model-source", { method: "PUT", body: JSON.stringify({ hf_token: token || null, local_repo: repo, clear_token: clearToken }) }),
    onSuccess: () => { setToken(""); setClearToken(false); void source.refetch(); },
  });
  return <Panel title="Model sources">
    <label className="field"><span>Hugging Face token (optional)</span>
      <input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder={source.data?.hf_token_configured ? "Token saved — leave blank to keep" : "hf_…"} />
    </label>
    <label><input type="checkbox" checked={clearToken} onChange={(event) => setClearToken(event.target.checked)} /> Remove saved token</label>
    <label className="field"><span>Local model repository or GGUF file</span>
      <input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="/path/to/local/models" />
    </label>
    <p>These preferences are used by setup and model import. Local folders must be visible to the API; Git LFS weights must already be downloaded. Saving does not download or load a model.</p>
    <button type="button" className="button secondary" disabled={save.isPending || source.isPending || source.isError} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save model sources"}</button>
    {(save.error || source.error) && <p role="alert">{formatApiError(save.error || source.error)}</p>}
    {save.isSuccess && <p role="status">Model source preferences saved. Run setup to choose your model and import source.</p>}
  </Panel>;
}
