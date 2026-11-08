import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ClarificationQuestionPanel } from "./ClarificationQuestionPanel";
import type { ClarificationVersionText, SessionDetailResponse } from "../api/types";

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

describe("flipped interaction questions", () => {
  const rationale = "Access rules determine which order records the portal may expose.";
  const blindSpot = "It is unconfirmed whether shared accounts may see another customer's orders.";
  const versions: ClarificationVersionText[] = ["beginner", "standard", "advanced"].map((level) => ({
    level: level as ClarificationVersionText["level"],
    label: level[0].toUpperCase() + level.slice(1),
    prompt: "Who should be allowed to view each order?",
    rationale,
    blind_spots: [blindSpot],
  }));

  it("shows why and unconfirmed blind spots in every wording without adopting them", () => {
    render(<ClarificationQuestionPanel sessionId="one" session={{ ...session, clarification_versions: versions }} />);
    for (const label of ["Beginner", "Standard", "Advanced"]) {
      const detail = screen.getByText(label).closest("details")!;
      expect(within(detail).getByText("Why this matters:")).toBeInTheDocument();
      expect(within(detail).getByText(rationale, { exact: false })).toBeInTheDocument();
      expect(within(detail).getByText("Potential blind spots (unconfirmed)")).toBeInTheDocument();
      expect(within(detail).getByText(blindSpot)).toBeInTheDocument();
      if (label === "Standard") expect(detail).toHaveAttribute("open");
    }
    expect(screen.getByLabelText("Custom answer (optional)")).toHaveValue("");
    expect(mocks.answer).not.toHaveBeenCalled();
  });

  it("shows legacy beginner explanations in standard and advanced wording too", () => {
    const legacyVersions = versions.map(({ blind_spots: _unused, ...version }) => ({
      ...version,
      rationale: version.level === "beginner" ? rationale : null,
    }));
    render(<ClarificationQuestionPanel sessionId="one" session={{ ...session, clarification_versions: legacyVersions }} />);
    const standard = screen.getByText("Standard").closest("details")!;
    expect(within(standard).getByText(rationale, { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("Potential blind spots (unconfirmed)")).not.toBeInTheDocument();
  });
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
