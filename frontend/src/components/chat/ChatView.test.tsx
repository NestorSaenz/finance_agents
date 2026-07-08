import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "./ChatView";

// vi.mock factories are hoisted, so shared refs must come from vi.hoisted.
const { chatMock, logoutMock, replaceMock, ApiError } = vi.hoisted(() => {
  class ApiErrorMock extends Error {
    constructor(
      public readonly status: number,
      message: string,
    ) {
      super(message);
    }
  }
  return {
    chatMock: vi.fn(),
    logoutMock: vi.fn(),
    replaceMock: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: { chat: (...args: unknown[]) => chatMock(...args) },
  ApiError,
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ token: "tok", logout: logoutMock }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: replaceMock }) }));

beforeEach(() => {
  chatMock.mockReset();
  logoutMock.mockReset();
  replaceMock.mockReset();
});

async function sendMessage(text: string) {
  await userEvent.type(screen.getByRole("textbox"), `${text}{Enter}`);
}

describe("ChatView", () => {
  it("shows the user message and the assistant reply after sending", async () => {
    chatMock.mockResolvedValue({
      response: "Registré tu gasto de $50 en pizza.",
      session_id: "s1",
      agent_used: "register",
    });
    render(<ChatView />);

    await sendMessage("gasté 50 en pizza");

    expect(await screen.findByText("gasté 50 en pizza")).toBeInTheDocument();
    expect(await screen.findByText("Registré tu gasto de $50 en pizza.")).toBeInTheDocument();
    expect(chatMock).toHaveBeenCalledWith(
      { message: "gasté 50 en pizza", session_id: null },
      "tok",
    );
  });

  it("reuses the session id returned by the backend on the next turn", async () => {
    chatMock
      .mockResolvedValueOnce({ response: "ok 1", session_id: "s-42", agent_used: null })
      .mockResolvedValueOnce({ response: "ok 2", session_id: "s-42", agent_used: null });
    render(<ChatView />);

    await sendMessage("uno");
    await screen.findByText("ok 1");
    await sendMessage("dos");
    await screen.findByText("ok 2");

    expect(chatMock).toHaveBeenLastCalledWith({ message: "dos", session_id: "s-42" }, "tok");
  });

  it("shows a graceful error bubble when the request fails", async () => {
    chatMock.mockRejectedValue(new ApiError(500, "boom"));
    render(<ChatView />);

    await sendMessage("hola");

    expect(await screen.findByText(/tuve un problema/i)).toBeInTheDocument();
  });

  it("logs out and redirects on 401", async () => {
    chatMock.mockRejectedValue(new ApiError(401, "expired"));
    render(<ChatView />);

    await sendMessage("hola");

    await waitFor(() => expect(logoutMock).toHaveBeenCalled());
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("fills the input when a suggestion chip is clicked", async () => {
    render(<ChatView />);

    await userEvent.click(screen.getByText("Gasté 200.000 en el supermercado"));

    expect(screen.getByRole("textbox")).toHaveValue("Gasté 200.000 en el supermercado");
  });
});
