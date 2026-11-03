import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import type { EventRecord } from "@/lib/api";
import {
  isPossibleOperatorCheck,
  operatorCheckLabel,
} from "@/lib/operatorCheck";
import { EventDetail } from "./Timeline";

function item(agent: unknown, source = "http"): EventRecord {
  return {
    id: "probe",
    timestamp: "2026-11-03T00:00:00Z",
    host_id: "host",
    source,
    src_ip: "192.0.2.1",
    dst_port: 80,
    category: "http_request",
    severity: "medium",
    event_type: "http.request",
    attributes: { user_agent: agent, path: "/.env" },
    safe_original: { path: "/.env" },
  };
}

it("labels a claimed operator probe without hiding its severity or evidence", () => {
  render(
    <EventDetail
      item={item("AttackScope recovery check forged")}
      onClose={() => {}}
    />,
  );
  expect(screen.getByText(operatorCheckLabel)).toHaveAttribute(
    "title",
    expect.stringContaining("Его можно подделать"),
  );
  expect(screen.getByText(/http · medium/)).toBeVisible();
  expect(screen.getAllByText(/\.env/).length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: /История IP/ })).toBeVisible();
});

it.each([
  null,
  undefined,
  123,
  {},
  "Mozilla/5.0",
  "AttackScope unknown check",
  "AttackScope rotation checkEVIL",
])("does not mark unrelated or malformed user agents: %s", (agent) => {
  expect(isPossibleOperatorCheck(item(agent))).toBe(false);
});

it("does not label SSH events by a claimed HTTP User-Agent", () => {
  expect(
    isPossibleOperatorCheck(item("AttackScope rotation check", "ssh")),
  ).toBe(false);
});
