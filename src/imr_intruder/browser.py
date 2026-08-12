from __future__ import annotations

from pathlib import Path
from typing import Any


def fetch_page(url: str, output: Path | None = None, timeout_ms: int = 30000) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Browser mode requires: python -m pip install 'imr-intruder[browser]' and playwright install chromium"
        ) from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        title = page.title()
        content = page.content()
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output), full_page=True)
        browser.close()
    return {
        "url": url,
        "status": response.status if response else None,
        "title": title,
        "html_bytes": len(content.encode()),
        "screenshot": str(output) if output else "",
    }
