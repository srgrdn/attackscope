"""Read-only browser acceptance against the real single-VM dataset."""

import json
import os
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect, sync_playwright

base = os.environ.get("ATTACKSCOPE_BROWSER_URL", "http://127.0.0.1:18180")
probe = "AttackScope UI text check <img src=x onerror=window.__attackScopeProbe=1>"
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base, wait_until="networkidle")
    expect(page.get_by_role("heading", level=1)).to_have_text("Event Timeline")
    expect(page.locator("canvas")).to_have_count(1)
    assert "demo-vm-demo" not in page.locator("select[name=host_id]").inner_text()
    assert "production-vm" in page.locator("select[name=host_id]").inner_text()
    with page.expect_response(lambda response: "/api/v1/timeline?" in response.url) as zoom:
        page.get_by_role("button", name="Приблизить +").click()
    assert zoom.value.ok
    now = datetime.now(timezone.utc)
    response = page.request.get(
        base + "/api/v1/events",
        params={
            "from": (now - timedelta(days=1)).isoformat(),
            "to": now.isoformat(),
            "source": "http",
            "limit": 100,
        },
    )
    assert response.ok
    observed = next(
        event
        for event in response.json()["items"]
        if event["attributes"].get("user_agent") == probe
    )
    page.get_by_role("link", name="Event Explorer", exact=True).click()
    page.get_by_placeholder("IPv4 / IPv6").fill(observed["src_ip"])
    page.locator("select[name=source]").select_option("http")
    with page.expect_response(
        lambda response: "/api/v1/events?" in response.url and "source=http" in response.url
    ) as filtered:
        page.get_by_role("button", name="Применить фильтры", exact=True).click()
    assert filtered.value.ok
    row = page.get_by_role("row").filter(has_text=observed["timestamp"])
    row.get_by_role("button", name="Открыть", exact=True).first.click()
    expect(page.locator(".detail-card > pre").filter(has_text=probe).first).to_be_visible()
    expect(page.locator(".detail-card img")).to_have_count(0)
    assert page.evaluate("window.__attackScopeProbe === undefined")
    page.get_by_role("link", name="История IP:", exact=False).click()
    expect(page.get_by_role("heading", name="Целевые VM")).to_be_visible()
    expect(page.get_by_text("Геолокация / ASN: недоступны.", exact=False)).to_be_visible()
    page.get_by_role("link", name="Overview", exact=True).click()
    expect(page.get_by_role("heading", name="Активные IP")).to_be_visible()
    page.get_by_role("link", name="Event Explorer", exact=True).click()
    with page.expect_download() as downloading:
        page.get_by_role("button", name="Экспорт JSON").click()
    with open(downloading.value.path()) as file:
        events = json.load(file)
    assert events
    assert not any((event.get("source_reference") or "").startswith("demo:") for event in events)
    assert "ATTACKSCOPE_QUERY_PLACEHOLDER" not in json.dumps(events)
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("link", name="Event Timeline", exact=True).click()
    expect(page.locator("canvas")).to_have_count(1)
    assert not errors, errors
    page.screenshot(
        path=os.environ.get("ATTACKSCOPE_SCREENSHOT", "/tmp/production.png"), full_page=True
    )
    browser.close()
    print(
        "Production Chromium: real host, timeline, safe log text, IP, "
        "overview, export and mobile passed"
    )
