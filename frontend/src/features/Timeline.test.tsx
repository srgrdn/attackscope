import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { EventDetail } from "./Timeline";
it("renders hostile log fields as text", () => {
  const attack = '<img src=x onerror="alert(1)">';
  render(
    <EventDetail
      onClose={() => {}}
      item={{
        id: "demo",
        timestamp: "2026-11-03T00:00:00Z",
        host_id: "demo",
        source: "http",
        src_ip: "2001:db8::1",
        dst_port: 443,
        category: "http_request",
        severity: "info",
        event_type: "http_request",
        attributes: { path: attack },
        safe_original: { path: attack },
      }}
    />,
  );
  expect(document.querySelector("img")).toBeNull();
  expect(screen.getAllByText(/onerror/).length).toBeGreaterThan(0);
  expect(screen.getByRole("link")).toHaveAttribute(
    "href",
    "#ip/2001%3Adb8%3A%3A1",
  );
});
