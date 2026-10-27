import axios, { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import * as authLib from "@/lib/auth";

function unauthorized(config: unknown) {
  return new AxiosError(
    "Unauthorized",
    "ERR_BAD_REQUEST",
    config as never,
    {},
    {
      status: 401,
      statusText: "Unauthorized",
      data: {},
      headers: {},
      config: config as never,
    } as never,
  );
}

describe("api 401 refresh/retry interceptor", () => {
  const originalAdapter = api.defaults.adapter;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authLib, "getAccessToken").mockReturnValue("expired-token");
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
  });

  it("retries the original request once after a successful refresh", async () => {
    const setSpy = vi.spyOn(authLib, "setAccessToken");
    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "new-token", expires_in: 3600, token_type: "bearer" },
    });

    let calls = 0;
    api.defaults.adapter = vi.fn(async (config) => {
      calls += 1;
      if (calls === 1) throw unauthorized(config);
      return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
    });

    const res = await api.get("/api/v1/resources");

    expect(res.data).toEqual({ ok: true });
    expect(calls).toBe(2);
    expect(setSpy).toHaveBeenCalledWith("new-token", 3600);
  });

  it("dedupes concurrent 401s into a single refresh call", async () => {
    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "new-token", expires_in: 3600, token_type: "bearer" },
    });

    api.defaults.adapter = vi.fn(async (config) => {
      const retried = (config as { _retry?: boolean })._retry;
      if (!retried) throw unauthorized(config);
      return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
    });

    await Promise.all([api.get("/api/v1/resources"), api.get("/api/v1/costs/summary")]);

    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  it("logs out and rejects when the refresh itself fails", async () => {
    vi.spyOn(axios, "post").mockRejectedValue(new Error("refresh expired"));
    const clearSpy = vi.spyOn(authLib, "clearAccessToken");
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");

    api.defaults.adapter = vi.fn(async (config) => {
      throw unauthorized(config);
    });

    await expect(api.get("/api/v1/resources")).rejects.toBeInstanceOf(AxiosError);

    expect(clearSpy).toHaveBeenCalled();
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: "cloudpilot:logout" }),
    );
  });

  it("does not attempt a refresh for a 401 from the auth endpoints themselves", async () => {
    const postSpy = vi.spyOn(axios, "post");
    api.defaults.adapter = vi.fn(async (config) => {
      throw unauthorized(config);
    });

    await expect(api.post("/api/v1/auth/login", {})).rejects.toBeInstanceOf(AxiosError);
    expect(postSpy).not.toHaveBeenCalled();
  });
});
