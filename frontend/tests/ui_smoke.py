"""Read-only Playwright checks against intercepted hypothetical API responses.

Start Vite first, then run:
    python frontend/tests/ui_smoke.py --base-url http://127.0.0.1:5173
Optional screenshots: --screenshots /path/to/output
CHROMIUM_PATH selects a browser; otherwise use system Chromium or Playwright's installed Chromium.
Only the supplied frontend origin can reach the network. Every /api/ request is intercepted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Page, Route, expect, sync_playwright
from ui_fixtures import (
    BTC_SWEEP,
    GOLD_EXPIRED,
    GOLD_INVALIDATED,
    GOLD_SWEEP,
    WARNING,
    UiFixtures,
    build_fixtures,
)


class MockApi:
    """Allow same-origin frontend assets; block all unmocked and external API traffic."""

    def __init__(self, base_url: str, fixtures: UiFixtures, mode: str = "normal") -> None:
        parsed = urlsplit(base_url)
        self.origin = (parsed.scheme, parsed.netloc)
        self.fixtures, self.mode = fixtures, mode
        self.requests: list[tuple[str, str]] = []
        self.violations: list[str] = []
        self.held_snapshot_id: str | None = None
        self.pending: list[Route] = []

    def install(self, context: BrowserContext) -> None:
        context.route("**/*", self.route)
        # Vite's optional hot-reload socket is unnecessary for these fixed-page checks.
        context.route_web_socket("**/*", lambda socket: socket.close())

    def route(self, route: Route) -> None:
        request = route.request
        parsed = urlsplit(request.url)
        if (parsed.scheme, parsed.netloc) != self.origin:
            self.violations.append(
                f"Blocked external request: {request.method} {parsed.netloc}{parsed.path}"
            )
            route.abort("blockedbyclient")
            return
        if request.method != "GET":
            self.violations.append(f"Blocked non-GET request: {request.method} {parsed.path}")
            route.abort("blockedbyclient")
            return
        if not parsed.path.startswith("/api/"):
            route.continue_()
            return
        self.requests.append((request.method, parsed.path))
        if self.mode == "offline":
            route.abort("internetdisconnected")
            return
        if self.mode in {"auth", "unavailable"}:
            code = 401 if self.mode == "auth" else 503
            route.fulfill(
                status=code,
                json={
                    "detail": "Hypothetical authentication required"
                    if code == 401
                    else "Hypothetical service unavailable"
                },
            )
            return
        if parsed.path.startswith("/api/snapshots/"):
            snapshot_id = parsed.path.rsplit("/", 1)[1]
            if snapshot_id == self.held_snapshot_id:
                self.pending.append(route)
                return
        try:
            payload = self.fixtures.payload(parsed.path, self.mode)
        except KeyError:
            self.violations.append(f"Unmocked API route: {parsed.path}")
            route.fulfill(status=404, json={"detail": "No hypothetical fixture for this API route"})
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    def release_snapshot(self) -> None:
        snapshot_id, self.held_snapshot_id = self.held_snapshot_id, None
        for route in self.pending:
            route.fulfill(status=200, json=self.fixtures.snapshots[snapshot_id])
        self.pending.clear()

    def assert_read_only(self) -> None:
        assert self.requests, "The UI never requested its API"
        assert not self.violations, "\n".join(self.violations)
        assert all(method == "GET" for method, _ in self.requests)
        assert not any(path.endswith("/assessments") for _, path in self.requests), (
            "Use candidate.review.attempts, not legacy assessments"
        )


def assert_no_overflow(page: Page) -> None:
    width = page.evaluate(
        "({viewport: innerWidth, document: document.documentElement.scrollWidth})"
    )
    assert width["document"] <= width["viewport"] + 1, f"Document has horizontal overflow: {width}"


def screenshot(page: Page, folder: Path | None, name: str) -> None:
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / name), full_page=True, animations="disabled")


def navigate(page: Page, name: str) -> None:
    menu = page.get_by_role("button", name="Open navigation", exact=True)
    if menu.is_visible() and menu.get_attribute("aria-expanded") != "true":
        menu.click()
    page.get_by_test_id(f"nav-{name}").click()


def open_case(
    browser: Browser, base_url: str, fixtures: UiFixtures, mode: str = "normal"
) -> tuple[BrowserContext, Page, MockApi, list[str]]:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000}, service_workers="block", reduced_motion="reduce"
    )
    api = MockApi(base_url, fixtures, mode)
    api.install(context)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_default_timeout(10_000)
    page.goto(base_url, wait_until="domcontentloaded")
    return context, page, api, errors


def check_populated(
    browser: Browser, base_url: str, fixtures: UiFixtures, folder: Path | None
) -> None:
    context, page, api, errors = open_case(browser, base_url, fixtures)
    try:
        expect(page.get_by_text(WARNING, exact=True).first).to_be_visible()
        page.get_by_test_id("asset-GOLD").click()
        page.get_by_test_id(f"candidate-row-{GOLD_SWEEP}").click()
        panel = page.get_by_test_id("snapshot-panel")
        gold_snapshot, btc_snapshot = (
            fixtures.snapshot_id(GOLD_SWEEP),
            fixtures.snapshot_id(BTC_SWEEP),
        )
        expect(panel).to_have_attribute("data-snapshot-id", gold_snapshot)
        expect(page.get_by_test_id("price-map")).to_be_visible()
        assert_no_overflow(page)
        screenshot(page, folder, "01-overview-hypothetical.png")

        # Hold the next snapshot response so the loading state cannot borrow Gold's evidence.
        api.held_snapshot_id = btc_snapshot
        page.get_by_test_id("asset-BTC").click()
        expect(page.get_by_test_id(f"candidate-row-{BTC_SWEEP}")).to_be_visible()
        expect(page.get_by_test_id(f"candidate-row-{GOLD_SWEEP}")).to_have_count(0)
        expect(panel).not_to_have_attribute("data-snapshot-id", gold_snapshot)
        page.wait_for_function("document.querySelector('[data-testid=\"asset-BTC\"]') !== null")
        assert api.pending, "Expected the selected BTC snapshot request to be held"
        api.release_snapshot()
        expect(panel).to_have_attribute("data-snapshot-id", btc_snapshot)

        navigate(page, "sweeps")
        expect(page.get_by_test_id(f"candidate-row-{BTC_SWEEP}")).to_be_visible()
        expect(page.get_by_test_id("candidate-row-ui-btc-hourly-breakout")).to_have_count(0)
        expect(page.get_by_test_id("candidate-row-ui-btc-session-structure")).to_have_count(0)
        page.get_by_test_id("asset-GOLD").click()
        expect(page.get_by_test_id(f"candidate-row-{GOLD_SWEEP}")).to_be_visible()
        expect(page.get_by_test_id(f"candidate-row-{GOLD_INVALIDATED}")).to_have_count(0)
        expect(panel).to_have_attribute("data-snapshot-id", gold_snapshot)
        assert_no_overflow(page)
        screenshot(page, folder, "02-sweeps-hypothetical.png")

        navigate(page, "overview")
        for candidate_id, status in ((GOLD_INVALIDATED, "INVALIDATED"), (GOLD_EXPIRED, "EXPIRED")):
            page.get_by_test_id(f"candidate-row-{candidate_id}").click()
            expect(page.get_by_test_id("candidate-status")).to_have_text(
                re.compile(status, re.IGNORECASE)
            )
            expect(page.get_by_test_id("candidate-status")).not_to_contain_text("CONFIRMED")
        navigate(page, "ai")
        expect(page.get_by_test_id("provider-OPENAI")).to_contain_text("hypothetical-openai-model")
        expect(page.get_by_test_id("provider-ANTHROPIC")).to_contain_text(
            "hypothetical-anthropic-model"
        )
        for name in ("overview", "sweeps", "ai", "research", "system"):
            navigate(page, name)
            assert_no_overflow(page)

        page.set_viewport_size({"width": 390, "height": 844})
        for name in ("overview", "sweeps", "ai", "research", "system"):
            navigate(page, name)
            assert_no_overflow(page)
        navigate(page, "overview")
        page.get_by_test_id("asset-BTC").click()
        expect(page.get_by_test_id("snapshot-panel")).to_have_attribute(
            "data-snapshot-id", btc_snapshot
        )
        screenshot(page, folder, "03-mobile-hypothetical.png")
        api.assert_read_only()
        assert not errors, errors
    finally:
        context.close()


def check_unavailable(
    browser: Browser, base_url: str, fixtures: UiFixtures, folder: Path | None
) -> None:
    for mode in ("empty", "missing_snapshot", "unavailable", "auth", "offline"):
        context, page, api, errors = open_case(browser, base_url, fixtures, mode)
        try:
            if mode == "missing_snapshot":
                page.get_by_test_id("asset-GOLD").click()
                page.get_by_test_id(f"candidate-row-{GOLD_SWEEP}").click()
                panel = page.get_by_test_id("snapshot-panel")
                expect(panel).to_contain_text(
                    re.compile("unavailable|not found|missing", re.IGNORECASE)
                )
                assert not panel.get_attribute("data-snapshot-id"), (
                    "Missing snapshot must not appear loaded"
                )
            else:
                if mode == "empty":
                    expect(page.get_by_text(WARNING, exact=True).first).to_be_visible()
                    expect(
                        page.get_by_text(
                            re.compile("no .*candidates|no candidate|no recorded", re.IGNORECASE)
                        ).first
                    ).to_be_visible()
                    screenshot(page, folder, "04-empty.png")
                else:
                    expect(page.get_by_test_id("connection-status")).to_contain_text(
                        re.compile(
                            "offline|unavailable|error|failed|disconnected|auth|unauthorized|"
                            "not connected|interrupted|cannot reach|sign.in required|503|401",
                            re.IGNORECASE,
                        )
                    )
                    expect(page.get_by_role("alert").first).to_be_visible()
                expect(page.locator('[data-testid^="candidate-row-"]')).to_have_count(0)
                expect(page.get_by_test_id("price-map")).to_have_count(0)
            assert_no_overflow(page)
            api.assert_read_only()
            assert not errors, errors
        finally:
            context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    chromium = os.environ.get("CHROMIUM_PATH")
    if chromium and not Path(chromium).is_file():
        parser.error("CHROMIUM_PATH must point to an installed browser executable")
    chromium = chromium or shutil.which("chromium") or shutil.which("chromium-browser")
    fixtures = build_fixtures()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium, headless=True)
        try:
            check_populated(browser, args.base_url, fixtures, args.screenshots)
            check_unavailable(browser, args.base_url, fixtures, args.screenshots)
        finally:
            browser.close()
    print(
        json.dumps(
            {
                "status": "PASS",
                "evidence": "Hypothetical UI fixtures; no strategy or live-integration validation",
                "checks": [
                    "asset snapshot isolation",
                    "sweep filtering",
                    "terminal lifecycle versus historical review",
                    "provider attempts",
                    "desktop/mobile overflow",
                    "empty/missing snapshot/503/401/offline",
                    "GET-only intercepted API; no external requests",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
