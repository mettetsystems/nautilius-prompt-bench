import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { apiFetch } from "../api/http";
import { PrecisionPage } from "./PrecisionPage";

vi.mock("../api/http", () => ({ apiFetch: vi.fn(), formatApiError: String }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("switches to CPU suggestions and ignores a late model response", async () => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  let finishModel!: (value: unknown) => void;
  const modelResponse = new Promise((resolve) => { finishModel = resolve; });
  const requests: boolean[] = [];
  vi.mocked(apiFetch).mockImplementation(async (path, options) => {
    if (path === "/sessions/test") return { session: { state: "optimization" } };
    if (path === "/sessions/test/precision") return {
      score: 0.7, threshold: 0.75, refinement_available: true,
      llm_available: true, vector_index_available: false,
      optimized_body: "Write a good summary.",
      findings: [{ id: "f1", term: "good", category: "lazy_adjective",
        line: "Write a good summary.", line_number: 1, start: 8, end: 12 }],
    };
    if (path === "/sessions/test/precision/suggest") {
      const payload = JSON.parse(String(options?.body));
      requests.push(payload.use_llm);
      if (payload.use_llm) return modelResponse;
      return { finding_id: "f1", suggested_replacements: ["CPU replacement"],
        source: "wordnet", model_available: false };
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter><PrecisionPage sessionId="test" /></MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(requests).toEqual([true]));
  fireEvent.click(screen.getByLabelText("Use AI tooling model"));
  await screen.findByRole("button", { name: "CPU replacement" });
  expect(requests).toEqual([true, false]);
  await act(async () => {
    finishModel({ finding_id: "f1", suggested_replacements: ["Late model replacement"],
      source: "llm", model_available: true });
    await modelResponse;
  });
  expect(screen.getByRole("button", { name: "CPU replacement" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Late model replacement" })).not.toBeInTheDocument();
});
