"""Verify Timeline keeps its canvas and document during delayed range requests."""

import asyncio
import os

from playwright.async_api import async_playwright, expect


async def main() -> None:
    base = os.environ.get("ATTACKSCOPE_BROWSER_URL", "http://localhost:8180")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base, wait_until="networkidle")
        await expect(page.locator("canvas")).to_have_count(1)
        await page.evaluate("""() => {
            window.timelineCanvas = document.querySelector('.event-chart canvas');
            window.timelineChart = document.querySelector('.event-chart');
            window.timelineRemoved = false;
            new MutationObserver(records => {
                for (const record of records) for (const node of record.removedNodes) {
                    if (node === window.timelineCanvas || node.contains?.(window.timelineCanvas))
                        window.timelineRemoved = true;
                }
            }).observe(document.body, {childList: true, subtree: true});
        }""")
        empty = False

        async def delayed(route) -> None:
            response = await route.fetch()
            await asyncio.sleep(0.8)
            if empty:
                await route.fulfill(
                    response=response,
                    json={"mode": "events", "total": 0, "items": [], "buckets": []},
                )
            else:
                await route.fulfill(response=response)

        await page.route("**/api/v1/timeline?*", delayed)

        async def unchanged() -> None:
            assert await page.evaluate("""() =>
                window.timelineCanvas === document.querySelector('.event-chart canvas') &&
                window.timelineChart === document.querySelector('.event-chart') &&
                window.timelineCanvas.isConnected && !window.timelineRemoved
            """), "Timeline canvas or document was replaced"

        async def completed() -> None:
            await expect(page.locator(".timeline-panel")).to_have_attribute("aria-busy", "true")
            await expect(page.get_by_text("Обновление событий… ·", exact=True)).to_be_visible()
            await unchanged()
            await expect(page.locator(".timeline-panel")).to_have_attribute("aria-busy", "false")
            await unchanged()

        # Visit uncached ranges so every action exercises the delayed API response.
        for name in ("Приблизить +", "← Раньше", "Отдалить −", "Позже →", "7d"):
            await page.get_by_role("button", name=name, exact=True).click()
            await completed()

        chart = page.locator(".event-chart")
        bounds = await chart.bounding_box()
        await page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + 100)
        await page.mouse.wheel(0, -200)
        await completed()

        empty = True
        await page.get_by_role("button", name="1h", exact=True).click()
        await completed()
        await expect(page.get_by_text("В этом диапазоне событий нет.", exact=False)).to_be_visible()
        empty = False
        await page.get_by_role("button", name="24h", exact=True).click()
        await completed()
        assert not errors, errors
        await browser.close()
        print(
            "Timeline: zoom, wheel, time shift, empty range preserve canvas during delayed requests"
        )


asyncio.run(main())
