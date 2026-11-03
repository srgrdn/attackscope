"""Chromium rendering check with synthetic API responses; no ingestion or real logs."""

import os
import re
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect, sync_playwright

base = os.environ.get("ATTACKSCOPE_BROWSER_URL", "http://localhost:8180")
timestamp = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
event = {
    "id": "operator-probe",
    "timestamp": timestamp,
    "host_id": "synthetic",
    "source": "http",
    "src_ip": "192.0.2.1",
    "dst_port": 80,
    "category": "http_request",
    "severity": "medium",
    "event_type": "http.request",
    "attributes": {
        "path": "/.aws/credentials",
        "status": 307,
        "user_agent": "AttackScope recovery check <img src=x onerror=window.__probe=1>",
    },
    "safe_original": {"path": "/.aws/credentials"},
}
finding = {
    "id": "finding-probe",
    "rule_id": "sensitive_path",
    "rule_version": 2,
    "rule_name": "Sensitive path probing",
    "host_id": "synthetic",
    "src_ip": "192.0.2.1",
    "source": "http",
    "timestamp": timestamp,
    "window_start": timestamp,
    "window_end": timestamp,
    "event_count": 1,
    "evidence_ids": [event["id"]],
    "reason": {
        "description": "Synthetic evidence",
        "metric": "count",
        "observed": 1,
        "threshold": 1,
        "window_kind": "fixed_utc",
        "evidence_truncated": False,
        "matched_paths": ["/.aws/credentials"],
        "matched_paths_truncated": False,
    },
}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/api/v1/events?*",
        lambda route: route.fulfill(json={"items": [event], "next_cursor": None}),
    )
    page.route(
        "**/api/v1/findings?*",
        lambda route: route.fulfill(json={"items": [finding], "truncated": False}),
    )
    page.route(
        "**/api/v1/timeline?*",
        lambda route: route.fulfill(
            json={"mode": "events", "total": 1, "items": [event], "buckets": []}
        ),
    )
    page.goto(base + "#events", wait_until="networkidle")
    label = "Возможная проверка оператора"
    expect(page.get_by_text(label, exact=True)).to_be_visible()
    expect(page.get_by_text(label, exact=True)).to_have_attribute(
        "title", re.compile("можно подделать")
    )
    expect(page.get_by_role("cell", name="medium", exact=True)).to_be_visible()
    page.get_by_role("button", name="Открыть", exact=True).click()
    expect(page.locator(".detail-card:has(h2)").get_by_text(label, exact=True)).to_be_visible()
    expect(page.locator(".detail-card img")).to_have_count(0)
    assert page.evaluate("window.__probe === undefined")
    page.get_by_role("link", name="Event Timeline", exact=True).click()
    expect(page.locator("canvas")).to_have_count(1)
    bounds = page.locator(".event-chart").bounding_box()
    start = (
        datetime.fromisoformat(page.get_by_label("С (UTC)", exact=True).input_value())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    end = (
        datetime.fromisoformat(page.get_by_label("До (UTC)", exact=True).input_value())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    point = datetime.fromisoformat(timestamp).timestamp()
    page.mouse.click(
        bounds["x"] + 85 + (bounds["width"] - 115) * (point - start) / (end - start),
        bounds["y"] + 30 + (bounds["height"] - 110) / 2,
    )
    expect(page.get_by_role("heading", name="Обнаруженные чувствительные пути")).to_be_visible()
    expect(page.locator(".detail-card code")).to_have_text("/.aws/credentials")
    expect(page.get_by_text("sensitive_path · версия 2")).to_be_visible()
    assert not errors, errors
    browser.close()
    print(
        "Chromium: unverified operator hint, unchanged severity, "
        "safe log text and matched paths passed"
    )
