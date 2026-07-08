import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";

const loginMock = vi.fn();
const refreshMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    login: (...args: unknown[]) => loginMock(...args),
    refresh: (...args: unknown[]) => refreshMock(...args),
    signup: vi.fn(),
    chat: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

const SESSION = { access_token: "tok", refresh_token: "ref", user_id: "u1", email: "e@x.com" };

function Probe() {
  const { user, token, loading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="state">
        {loading ? "loading" : token ? `in:${user?.email}` : "out"}
      </span>
      <button onClick={() => void login({ email: "e@x.com", password: "pw" })}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  loginMock.mockReset();
  refreshMock.mockReset().mockResolvedValue(SESSION);
});

describe("AuthProvider", () => {
  it("starts logged out when there is nothing stored", async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("out"));
  });

  it("hydrates the session from localStorage on mount", async () => {
    localStorage.setItem("fg_token", "tok");
    localStorage.setItem("fg_refresh", "ref");
    localStorage.setItem("fg_user", JSON.stringify({ userId: "u1", email: "e@x.com" }));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("in:e@x.com"));
    // It refreshes the access token on hydration to revive an idle session.
    await waitFor(() => expect(refreshMock).toHaveBeenCalledWith("ref"));
  });

  it("persists token + user on login and clears them on logout", async () => {
    loginMock.mockResolvedValue(SESSION);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("out"));

    await userEvent.click(screen.getByText("login"));

    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("in:e@x.com"));
    expect(localStorage.getItem("fg_token")).toBe("tok");

    await userEvent.click(screen.getByText("logout"));

    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("out"));
    expect(localStorage.getItem("fg_token")).toBeNull();
  });
});
