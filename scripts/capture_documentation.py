"""Capture actual UI against the dedicated documentation stack only."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:18182"
OUTPUT = Path("/output")
seed = json.loads((OUTPUT / "seed.json").read_text())
assert seed["synthetic"] is True
fixed = datetime.fromisoformat(seed["base_time"]) + timedelta(seconds=60)
entries = []


def capture(page, filename, description, locator=None, full_page=False, simulated=False):
    page.evaluate("document.fonts.ready")
    if locator is None:
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(OUTPUT / filename), full_page=full_page, animations="disabled")
    else:
        locator.screenshot(path=str(OUTPUT / filename), animations="disabled")
    entries.append(
        {
            "file": filename,
            "description": description,
            "simulated_api_error": simulated,
            "sha256": hashlib.sha256((OUTPUT / filename).read_bytes()).hexdigest(),
        }
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1440, "height": 1100},
        locale="ru-RU",
        timezone_id="UTC",
        device_scale_factor=1,
    )
    context.add_init_script(f"Date.now = () => {int(fixed.timestamp() * 1000)};")

    # Block accidental requests outside the documentation UI, including image URLs in logs.
    def local_only(route):
        parsed = urlsplit(route.request.url)
        if parsed.hostname == "127.0.0.1" and parsed.port == 18182:
            route.continue_()
        else:
            route.abort()

    context.route("**/*", local_only)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    expect(page.get_by_text("Backend подключён", exact=True)).to_be_visible()
    expect(page.get_by_text("Группы · точное количество", exact=False)).to_be_visible()
    hosts = page.locator("select[name=host_id]").inner_text()
    assert "demo-wiki" in hosts and "production-vm" not in hosts
    capture(page, "01-timeline-overview.png", "Timeline: aggregated synthetic observations")

    page.get_by_placeholder("IPv4 / IPv6").fill("198.51.100.42")
    page.get_by_role("button", name="Применить", exact=True).click()
    expect(page.get_by_text("Отдельные события", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Карта событий · 6 наблюдений")).to_be_visible()
    cloud = datetime.fromisoformat(seed["cloud_time"])
    page.get_by_label("С (UTC)", exact=True).fill(
        (cloud - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M")
    )
    page.get_by_label("До (UTC)", exact=True).fill(
        (cloud + timedelta(seconds=180)).strftime("%Y-%m-%dT%H:%M")
    )
    with page.expect_response(lambda response: "/api/v1/timeline?" in response.url):
        page.get_by_role("button", name="Применить", exact=True).click()
    expect(page.locator(".timeline-panel")).to_have_attribute("aria-busy", "false")
    capture(page, "02-timeline-filtered.png", "Timeline: six credential probes for a reserved IP")

    page.get_by_role("link", name="Event Explorer", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Event Explorer")).to_be_visible()
    page.get_by_placeholder("IPv4 / IPv6").fill("198.51.100.42")
    page.locator("select[name=source]").select_option("http")
    page.get_by_role("button", name="Применить фильтры", exact=True).click()
    expect(page.locator("tbody tr")).to_have_count(6)
    capture(page, "03-event-explorer.png", "Event Explorer: time/IP/source filters and export")

    page.get_by_role("button", name="Открыть", exact=True).first.click()
    card = page.locator(".detail-card:has(h2)")
    expect(card.get_by_role("heading", name="Атрибуты")).to_be_visible()
    capture(page, "04-event-detail.png", "Safe event projection; query values were removed", card)

    page.get_by_role("link", name="История IP:", exact=False).click()
    expect(page.get_by_role("heading", name="Целевые VM")).to_be_visible()
    capture(
        page,
        "06-ip-explorer.png",
        "IP Explorer: synthetic IP history and distributions",
        full_page=True,
    )
    page.get_by_role("button", name="Sensitive path probing", exact=False).first.click()
    finding = page.locator(".detail-card:has(h3)")
    expect(finding.get_by_role("heading", name="Обнаруженные чувствительные пути")).to_be_visible()
    expect(finding.locator("code")).to_have_count(6)
    capture(page, "05-finding-detail.png", "Sensitive path v2: six matches and evidence", finding)

    page.get_by_role("link", name="Overview", exact=True).click()
    expect(page.get_by_role("heading", name="Активные IP", exact=True)).to_be_visible()
    capture(
        page,
        "07-overview.png",
        "Overview: all events versus rule-classified observations",
    )

    page.get_by_role("link", name="История до 365d", exact=True).click()
    expect(page.get_by_role("heading", name="Исторические IP")).to_be_visible()
    capture(page, "08-history.png", "Historical analysis: full UTC-hour coverage", full_page=True)

    page.goto(BASE + "#events?" + urlencode({"ip": "192.0.2.44"}), wait_until="networkidle")
    expect(page.get_by_text("Возможная проверка оператора", exact=True)).to_be_visible()
    page.get_by_role("button", name="Открыть", exact=True).click()
    card = page.locator(".detail-card:has(h2)")
    expect(card.get_by_text("Возможная проверка оператора", exact=True)).to_be_visible()
    capture(
        page,
        "09-operator-check.png",
        "Unverified User-Agent hint; observation remains included",
        card,
    )

    page.get_by_role("link", name="Event Timeline", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Event Timeline")).to_be_visible()
    page.get_by_placeholder("IPv4 / IPv6").fill("192.0.2.254")
    page.get_by_role("button", name="Применить", exact=True).click()
    expect(page.get_by_text("В этом диапазоне событий нет.", exact=False)).to_be_visible()
    capture(
        page,
        "10-empty-state.png",
        "Empty filtered range; not proof of no network traffic",
        full_page=True,
    )

    error_page = context.new_page()
    error_page.route(
        "**/api/v1/timeline?*",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"error":{"code":"busy","message":"Documentation state"}}',
        ),
    )
    error_page.goto(BASE, wait_until="networkidle")
    expect(error_page.get_by_role("alert")).to_be_visible()
    capture(
        error_page,
        "11-api-error.png",
        "Actual UI error state with browser-simulated HTTP503",
        simulated=True,
    )
    error_page.close()

    mobile = context.new_page()
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.goto(BASE, wait_until="networkidle")
    expect(mobile.locator("canvas")).to_have_count(1)
    capture(mobile, "12-mobile-timeline.png", "Timeline on a narrow viewport", full_page=True)
    assert not errors, errors
    metadata = {
        **seed,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "application_origin": BASE,
        "viewport": {"width": 1440, "height": 1100},
        "screenshots": entries,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    browser.close()
    print(f"Captured {len(entries)} checked UI screenshots; demo data only")
