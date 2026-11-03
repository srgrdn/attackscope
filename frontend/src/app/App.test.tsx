import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

// Canvas rendering and ResizeObserver are verified by the Chromium smoke tests.
vi.mock("@/features/TimelineChart", () => ({
  TimelineChart: () => <div aria-label="Timeline chart" />,
}));

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(() => vi.unstubAllGlobals());

describe("Application shell", () => {
  it("shows a pending check and timeline controls", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    const client = mount();
    expect(screen.getAllByRole("status")[0]).toHaveTextContent(
      "Проверка подключения",
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Event Timeline",
    );
    expect(screen.getByRole("button", { name: "Приблизить +" })).toBeVisible();
    expect(screen.getByRole("link", { name: /IP Explorer/ })).toBeVisible();
    client.clear();
  });

  it("shows readiness from the backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((path: string) =>
          Promise.resolve(
            new Response(
              JSON.stringify(
                path.includes("hosts")
                  ? { items: [] }
                  : path.includes("timeline")
                    ? { mode: "events", total: 0, items: [], buckets: [] }
                    : { status: "ready" },
              ),
            ),
          ),
        ),
    );
    const client = mount();
    expect(await screen.findByText("Backend подключён")).toBeVisible();
    client.clear();
  });

  it("recovers after an error when the user retries", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValue(new Error("<img src=x onerror=alert(1)>"));
    vi.stubGlobal("fetch", fetcher);
    const client = mount();
    await waitFor(
      () =>
        expect(screen.getAllByRole("status")[0]).toHaveTextContent(
          "Backend недоступен",
        ),
      { timeout: 4000 },
    );
    expect(document.querySelector("img")).toBeNull();
    fetcher.mockResolvedValue(
      new Response(JSON.stringify({ status: "ready" })),
    );
    await userEvent.click(screen.getByRole("button", { name: "Проверить" }));
    expect(await screen.findByText("Backend подключён")).toBeVisible();
    client.clear();
  });
});
