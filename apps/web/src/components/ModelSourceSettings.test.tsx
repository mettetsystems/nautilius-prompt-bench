import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModelSourceSettings } from "./ModelSourceSettings";
import { apiFetch } from "../api/http";
vi.mock("../api/http", () => ({ apiFetch: vi.fn(), formatApiError: String }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
describe("model sources", () => {
  it("masks token input and clears it after saving without receiving the secret", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ hf_token_configured: true, local_repo: "/models" });
    render(<QueryClientProvider client={new QueryClient()}><ModelSourceSettings /></QueryClientProvider>);
    const token = screen.getByLabelText("Hugging Face token (optional)");
    expect(token).toHaveAttribute("type", "password");
    await waitFor(() => expect(screen.getByLabelText("Local model repository or GGUF file")).toHaveValue("/models"));
    fireEvent.change(token, { target: { value: "hf_secret" } });
    fireEvent.click(screen.getByText("Save model sources"));
    await screen.findByRole("status");
    expect(token).toHaveValue("");
    expect(apiFetch).toHaveBeenCalledWith("/settings/model-source", expect.objectContaining({ method: "PUT", body: JSON.stringify({ hf_token: "hf_secret", local_repo: "/models", clear_token: false }) }));
  });
});
