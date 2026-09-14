import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ClarificationQuestionPanel } from "./ClarificationQuestionPanel";
import type { SessionDetailResponse } from "../api/types";

const mocks = vi.hoisted(() => ({ suggest: vi.fn(), answer: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({ useQuery: () => ({ data: { llm_enabled: true, status: "ok" } }) }));
vi.mock("../api/hooks", () => ({
  useAnswerClarification: () => ({ mutateAsync: mocks.answer }),
  useCompleteClarification: () => ({}),
  useSuggestClarification: () => ({ mutateAsync: mocks.suggest }),
  useAskTheLocals: () => ({}),
  useUserSettings: () => ({ data: {} }),
}));
const session = {
  clarification_field: "application_requirements.runtime",
  clarification_question: "What runtime?",
  clarification_question_number: 1,
  clarification_total_questions: 30,
  clarification_quick_replies: ["Unsure", "Not applicable", "Recommend an option", "unspecified"],
} as SessionDetailResponse;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.suggest.mockResolvedValue({ field_name: session.clarification_field, original_answer: "Python", proposed_answer: "Python 3.12", suggested_answers: [], recommendations: ["Consider Python 3.12"], model_available: true });
  mocks.answer.mockResolvedValue({});
});

describe("clarification suggestions", () => {
  it("keeps the original answer and requires explicit editable adoption and submission", async () => {
    render(<ClarificationQuestionPanel sessionId="one" session={session} />);
    fireEvent.change(screen.getByLabelText("Custom answer (optional)"), { target: { value: "Python" } });
    fireEvent.click(screen.getByText("Get model suggestions"));
    await screen.findByLabelText("Model proposal");
    expect(mocks.suggest).toHaveBeenCalledWith({ current_answer: "Python", model: "lightweight", field_name: session.clarification_field });
    expect(screen.getByLabelText("Custom answer (optional)")).toHaveValue("Python");
    expect(mocks.answer).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Model proposal"), { target: { value: "Python 3.13" } });
    fireEvent.click(screen.getByText("Use edited proposal"));
    expect(screen.getByLabelText("Custom answer (optional)")).toHaveValue("Python 3.13");
    expect(mocks.answer).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Submit answer"));
    await waitFor(() => expect(mocks.answer).toHaveBeenCalledWith("Python 3.13"));
  });

  it("rejects a proposal without removing the manual answer", async () => {
    render(<ClarificationQuestionPanel sessionId="one" session={session} />);
    fireEvent.change(screen.getByLabelText("Custom answer (optional)"), { target: { value: "Python" } });
    fireEvent.click(screen.getByText("Get model suggestions"));
    await screen.findByLabelText("Model proposal");
    fireEvent.click(screen.getByText("Reject suggestion"));
    expect(screen.queryByLabelText("Model proposal")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Custom answer (optional)")).toHaveValue("Python");
  });

  it("does not show a late response on a different question", async () => {
    let resolve!: (value: unknown) => void;
    mocks.suggest.mockReturnValue(new Promise((done) => { resolve = done; }));
    const { rerender } = render(<ClarificationQuestionPanel sessionId="one" session={session} />);
    fireEvent.click(screen.getByText("Get model suggestions"));
    rerender(<ClarificationQuestionPanel sessionId="one" session={{ ...session, clarification_question_number: 2, clarification_field: "application_requirements.hosting" }} />);
    resolve({ proposed_answer: "Stale answer", suggested_answers: [] });
    await waitFor(() => expect(screen.queryByLabelText("Model proposal")).not.toBeInTheDocument());
  });
});
