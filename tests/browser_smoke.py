"""Real Chromium smoke against the localhost-only running demo instance."""

import json
import os
from datetime import datetime, UTC

from playwright.sync_api import expect, sync_playwright

base = os.environ.get("ATTACKSCOPE_BROWSER_URL", "http://localhost:8180")
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base, wait_until="networkidle")
    expect(page.get_by_role("heading", level=1)).to_have_text("Event Timeline")
    expect(page.locator("canvas")).to_have_count(1)
    expect(page.get_by_text("Группы · точное количество")).to_be_visible()
    with page.expect_response(lambda response: "/api/v1/timeline?" in response.url) as changed:
        page.get_by_role("button", name="Приблизить +").click()
    assert changed.value.ok
    dense = changed.value.json()
    if dense["mode"] == "buckets":
        # Prefer a quieter lane: the densest HTTP bucket can overlap a finding diamond.
        candidates = [item for item in dense["buckets"] if item["source"] == "firewall"]
        bucket = max(candidates or dense["buckets"], key=lambda item: item["count"])
        bounds = page.locator(".event-chart").bounding_box()
        start = (
            datetime.fromisoformat(page.get_by_label("С (UTC)", exact=True).input_value())
            .replace(tzinfo=UTC)
            .timestamp()
        )
        end = (
            datetime.fromisoformat(page.get_by_label("До (UTC)", exact=True).input_value())
            .replace(tzinfo=UTC)
            .timestamp()
        )
        middle = (
            datetime.fromisoformat(bucket["from"].replace("Z", "+00:00")).timestamp()
            + datetime.fromisoformat(bucket["to"].replace("Z", "+00:00")).timestamp()
        ) / 2
        lane = ["ssh", "http", "firewall"].index(bucket["source"])
        x = bounds["x"] + 85 + (bounds["width"] - 115) * (middle - start) / (end - start) + 14
        y = bounds["y"] + 30 + (bounds["height"] - 110) * (lane + 0.5) / 3
        page.mouse.click(x, y)
        expect(page.get_by_role("button", name="Исследовать интервал")).to_be_visible()
        with page.expect_response(lambda response: "/api/v1/timeline?" in response.url) as drilled:
            page.get_by_role("button", name="Исследовать интервал").click()
        assert drilled.value.ok
    page.get_by_role("link", name="Event Explorer", exact=True).click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Event Explorer")
    expect(page.get_by_role("button", name="Далее")).to_be_enabled()
    page.get_by_role("button", name="Далее").click()
    expect(page.get_by_text("Страница 2 · до 100 событий")).to_be_visible()
    page.get_by_role("button", name="Назад").click()
    page.get_by_role("button", name="Открыть", exact=True).first.click()
    expect(page.get_by_role("heading", name="Безопасная проекция исходных данных")).to_be_visible()
    page.get_by_role("link", name="История IP:", exact=False).click()
    expect(page.get_by_role("heading", name="Целевые VM")).to_be_visible()
    expect(page.get_by_text("Геолокация / ASN: недоступны.", exact=False)).to_be_visible()
    page.get_by_role("link", name="Все события этого IP за выбранный период →").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Event Explorer")
    assert page.get_by_placeholder("IPv4 / IPv6").input_value()
    page.get_by_role("link", name="История до 365d", exact=True).click()
    expect(page.get_by_role("heading", name="Исторические IP")).to_be_visible()
    page.get_by_role("link", name="Overview", exact=True).click()
    expect(page.get_by_role("heading", name="Активные IP")).to_be_visible()
    page.get_by_role("link", name="Event Explorer", exact=True).click()
    with page.expect_download() as downloading:
        page.get_by_role("button", name="Экспорт JSON").click()
    download = downloading.value
    with open(download.path()) as file:
        assert len(json.load(file)) >= 2086
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("link", name="Event Timeline", exact=True).click()
    expect(page.locator("canvas")).to_have_count(1)
    assert not errors, errors
    page.screenshot(
        path=os.environ.get("ATTACKSCOPE_SCREENSHOT", "/tmp/attackscope-browser.png"),
        full_page=True,
    )
    print(
        "Chromium: timeline zoom, pagination, detail → IP, overview, filtered JSON download and mobile passed"
    )
    browser.close()
