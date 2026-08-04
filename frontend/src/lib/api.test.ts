import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";

interface CapturedInit {
  method: string;
  headers: Record<string, string>;
  body?: string;
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function captured(fetchMock: ReturnType<typeof vi.fn>): { url: string; init: CapturedInit } {
  const call = fetchMock.mock.calls[0];
  if (!call) throw new Error("fetch was not called");
  return { url: call[0] as string, init: call[1] as CapturedInit };
}

afterEach(() => vi.unstubAllGlobals());

describe("api.login", () => {
  it("POSTs credentials to the login endpoint and returns the session", async () => {
    const session = { access_token: "t", refresh_token: "r", user_id: "u", email: "e@x.com" };
    const fetchMock = stubFetch(200, session);

    const res = await api.login({ email: "e@x.com", password: "pw" });

    expect(res).toEqual(session);
    const { url, init } = captured(fetchMock);
    expect(url).toBe("/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body ?? "{}")).toEqual({ email: "e@x.com", password: "pw" });
  });
});

describe("api.chat", () => {
  it("sends the message with the bearer token", async () => {
    const fetchMock = stubFetch(200, { response: "hola", session_id: "s1", agent_used: "query" });

    const res = await api.chat({ message: "hola", session_id: null }, "tok-123");

    expect(res.session_id).toBe("s1");
    const { url, init } = captured(fetchMock);
    expect(url).toBe("/api/v1/chat");
    expect(init.headers.Authorization).toBe("Bearer tok-123");
  });

  it("omits the Authorization header when there is no token", async () => {
    const fetchMock = stubFetch(200, { response: "x", session_id: "s", agent_used: null });

    await api.chat({ message: "hola" }, null);

    expect(captured(fetchMock).init.headers.Authorization).toBeUndefined();
  });
});

describe("error handling", () => {
  it("throws ApiError with status and backend message on non-2xx", async () => {
    stubFetch(401, { message: "Credenciales inválidas." });

    await expect(api.login({ email: "a", password: "b" })).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Credenciales inválidas.",
    });
  });

  it("wraps a network failure as ApiError(0)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const error = await api.login({ email: "a", password: "b" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
  });
});
