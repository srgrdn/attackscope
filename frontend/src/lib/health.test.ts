import { afterEach, expect, it, vi } from "vitest";
import { fetchReadiness } from "./health";

afterEach(() => vi.unstubAllGlobals());

it("rejects HTTP errors instead of displaying arbitrary backend messages", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("secret", { status: 503 })),
  );
  await expect(fetchReadiness()).rejects.toThrow("Backend unavailable");
});

it("validates the readiness payload", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response('{"status":"unexpected"}')),
  );
  await expect(fetchReadiness()).rejects.toThrow("Invalid readiness response");
});

it("passes the cancellation signal", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{"status":"ready"}'));
  vi.stubGlobal("fetch", fetcher);
  const controller = new AbortController();
  await fetchReadiness(controller.signal);
  expect(fetcher).toHaveBeenCalledWith(
    "/api/v1/health/ready",
    expect.objectContaining({ signal: controller.signal }),
  );
});
