import { useMutation } from "@tanstack/react-query";
import { apiFetch, formatApiError } from "../api/http";
import { Panel } from "./ui";

type HardwareReport = {
  gpus: { name: string; vendor: string; vram_mb: number | null; free_vram_mb: number | null }[];
  available_ram_mb: number | null;
  recommended: string;
  local_options: { id: string; label: string; model: string; status: string; reason: string }[];
  remote_option: { label: string; reason: string };
  note: string;
};
const memory = (mb: number | null) => mb === null ? "unknown" : `${(mb / 1024).toFixed(1)} GiB`;

export function HardwareRecommendations() {
  const scan = useMutation({ mutationFn: () => apiFetch<HardwareReport>("/health/hardware") });
  return <Panel title="Hardware and model recommendations">
    <button type="button" className="button secondary" disabled={scan.isPending} onClick={() => scan.mutate()}>
      {scan.isPending ? "Scanning hardware…" : "Scan GPU capabilities"}
    </button>
    {scan.error && <p role="alert">{formatApiError(scan.error)}</p>}
    {scan.data && <div aria-live="polite">
      {scan.data.gpus.length === 0 && <p>No supported GPU detected, or its driver is unavailable.</p>}
      {scan.data.gpus.map((gpu, index) => <p key={index}>{gpu.name}: {memory(gpu.vram_mb)} total, {memory(gpu.free_vram_mb)} free</p>)}
      <p>Available system RAM: {memory(scan.data.available_ram_mb)}. Recommended tier: {scan.data.recommended}.</p>
      <ul>{scan.data.local_options.map((option) => <li key={option.id}>
        <strong>{option.label}</strong> — {option.model} ({option.status}). {option.reason}
      </li>)}</ul>
      <p><strong>{scan.data.remote_option.label}</strong> — {scan.data.remote_option.reason}</p>
      <p>{scan.data.note}</p>
      <p>Select a local model with <code>make setup</code>. Configure a remote URL and model in the AI tooling override below. After changing hardware, run <code>./scripts/rebuild-hardware.sh</code>.</p>
    </div>}
  </Panel>;
}
