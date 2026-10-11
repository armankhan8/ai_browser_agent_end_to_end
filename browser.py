from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from config import Settings


_STATE_SCRIPT = r"""
(args) => {
  const maxElements = args.maxElements;
  const maxTextChars = args.maxTextChars;
  const attr = "data-ai-browser-id";

  document.querySelectorAll(`[${attr}]`).forEach((el) => el.removeAttribute(attr));

  function isVisible(el) {
    if (!(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
      return false;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width < 3 || rect.height < 3) return false;
    return rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
  }

  function clean(value, maxLen = 160) {
    return (value || "").replace(/\s+/g, " ").trim().slice(0, maxLen);
  }

  function inferredRole(el) {
    const explicit = clean(el.getAttribute("role"), 40);
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (["button", "submit", "reset"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      return "textbox";
    }
    if (el.isContentEditable) return "textbox";
    return "interactive";
  }

  const selectors = [
    "a[href]",
    "button",
    "input:not([type='hidden'])",
    "textarea",
    "select",
    "[contenteditable='true']",
    "[role='button']",
    "[role='link']",
    "[role='textbox']",
    "[role='combobox']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='menuitem']",
    "[role='option']",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  const all = Array.from(document.querySelectorAll(selectors));
  const unique = [];
  const seen = new Set();
  for (const el of all) {
    if (seen.has(el) || !isVisible(el)) continue;
    if (el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true") continue;
    seen.add(el);
    unique.push(el);
    if (unique.length >= maxElements) break;
  }

  const elements = unique.map((el, index) => {
    el.setAttribute(attr, String(index));
    const tag = el.tagName.toLowerCase();
    const role = inferredRole(el);
    const label = clean(el.getAttribute("aria-label"));
    const placeholder = clean(el.getAttribute("placeholder"));
    const title = clean(el.getAttribute("title"));
    const value = clean(el.value || "");
    const text = clean(el.innerText || el.textContent || "");
    const href = tag === "a" ? clean(el.href, 220) : "";
    const type = clean(el.getAttribute("type"), 40);
    const name = label || placeholder || title || text || value;
    return {index, tag, role, name, text, placeholder, value, href, type};
  });

  const bodyText = clean(document.body ? document.body.innerText : "", maxTextChars);
  return {
    url: location.href,
    title: document.title || "",
    viewport: {width: window.innerWidth, height: window.innerHeight, scrollY: Math.round(window.scrollY)},
    bodyText,
    elements,
  };
}
"""


@dataclass
class BrowserSession:
    settings: Settings
    headless: bool | None = None
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    logs: list[str] = field(default_factory=list)
    status: str = "Idle"
    stop_requested: bool = False
    current_run_task: asyncio.Task[Any] | None = None
    run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def log(self, message: str) -> None:
        message = message.strip()
        if not message:
            return
        self.logs.append(message)
        if len(self.logs) > 250:
            self.logs[:] = self.logs[-250:]

    def reset_run_state(self) -> None:
        self.logs.clear()
        self.stop_requested = False
        self.status = "Starting"

    def request_stop(self) -> None:
        self.stop_requested = True
        self.status = "Stopping"
        self.log("⏹ Stop requested by user.")
        task = self.current_run_task
        if task is not None and not task.done():
            task.cancel()

    def check_stop(self) -> None:
        if self.stop_requested:
            raise asyncio.CancelledError("Run stopped by user")

    async def ensure_started(self, headless: bool | None = None) -> None:
        desired_headless = self.settings.headless if headless is None else headless

        if self.browser is not None and self.page is not None:
            if self.headless == desired_headless and self.browser.is_connected():
                return
            await self.close()

        self.log("🌐 Launching Chromium...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=desired_headless,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--disable-notifications",
                "--start-maximized",
            ],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        self.context.set_default_timeout(self.settings.browser_timeout_ms)
        self.page = await self.context.new_page()
        self.headless = desired_headless
        self.log(f"✅ Chromium ready ({'headless' if desired_headless else 'visible'} mode).")

    async def close(self) -> None:
        self.stop_requested = True
        self.current_run_task = None

        if self.context is not None:
            with contextlib.suppress(Exception):
                await self.context.close()
        if self.browser is not None:
            with contextlib.suppress(Exception):
                await self.browser.close()
        if self.playwright is not None:
            with contextlib.suppress(Exception):
                await self.playwright.stop()

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.headless = None
        self.status = "Browser closed"

    def require_page(self) -> Page:
        self.check_stop()
        if self.page is None:
            raise RuntimeError("Browser is not started yet.")
        return self.page

    @staticmethod
    def normalize_url(url: str) -> str:
        raw = url.strip()
        if not raw:
            raise ValueError("URL cannot be empty.")
        if "://" not in raw:
            raw = "https://" + raw
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only http:// and https:// URLs are allowed.")
        if not parsed.netloc:
            raise ValueError("Invalid URL.")
        return raw

    def sync_active_page(self) -> None:
        """Follow the newest open tab/popup if an action created one."""
        if self.context is None:
            return
        open_pages = [p for p in self.context.pages if not p.is_closed()]
        if not open_pages:
            return
        newest = open_pages[-1]
        if self.page is not newest:
            self.page = newest
            self.log("🗂️ Switched to the newly opened browser tab.")

    async def after_action(self) -> None:
        self.sync_active_page()
        page = self.require_page()
        if self.settings.action_delay_ms:
            await page.wait_for_timeout(self.settings.action_delay_ms)
        self.sync_active_page()
        page = self.require_page()
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("domcontentloaded", timeout=2500)

    async def page_state(self) -> dict[str, Any]:
        self.sync_active_page()
        page = self.require_page()
        try:
            state = await page.evaluate(
                _STATE_SCRIPT,
                {
                    "maxElements": self.settings.max_elements,
                    "maxTextChars": self.settings.page_text_chars,
                },
            )
        except Exception as exc:
            return {
                "url": page.url,
                "title": "",
                "viewport": {},
                "bodyText": "",
                "elements": [],
                "error": f"Could not inspect page: {type(exc).__name__}: {exc}",
            }
        return state

    async def state_for_agent(self) -> str:
        state = await self.page_state()
        return self.format_state(state)

    @staticmethod
    def format_state(state: dict[str, Any]) -> str:
        lines = [
            f"URL: {state.get('url', '')}",
            f"Title: {state.get('title', '')}",
        ]
        viewport = state.get("viewport") or {}
        if viewport:
            lines.append(
                f"Viewport: {viewport.get('width', '?')}x{viewport.get('height', '?')}, scrollY={viewport.get('scrollY', '?')}"
            )
        if state.get("error"):
            lines.append(f"Inspection error: {state['error']}")

        lines.append("\nVisible interactive elements:")
        elements = state.get("elements") or []
        if not elements:
            lines.append("(none detected in the current viewport)")
        else:
            for item in elements:
                extras: list[str] = []
                if item.get("placeholder"):
                    extras.append(f"placeholder={json.dumps(item['placeholder'], ensure_ascii=False)}")
                if item.get("value"):
                    extras.append(f"value={json.dumps(item['value'], ensure_ascii=False)}")
                if item.get("href"):
                    extras.append(f"href={json.dumps(item['href'], ensure_ascii=False)}")
                if item.get("type"):
                    extras.append(f"type={item['type']}")
                name = item.get("name") or item.get("text") or ""
                suffix = (" | " + ", ".join(extras)) if extras else ""
                lines.append(
                    f"[{item['index']}] <{item.get('tag', '?')}> role={item.get('role', '?')} name={json.dumps(name, ensure_ascii=False)}{suffix}"
                )

        body_text = (state.get("bodyText") or "").strip()
        if body_text:
            lines.append("\nVisible page text (truncated):")
            lines.append(body_text)
        return "\n".join(lines)

    async def locator_for_index(self, index: int):
        page = self.require_page()
        # IMPORTANT: do not regenerate indexes here. The action must target the exact
        # element ID from the most recently returned page state. If a dynamic rerender
        # removed that element, fail safely so the tool can return a fresh state.
        locator = page.locator(f'[data-ai-browser-id="{index}"]').first
        if await locator.count() == 0:
            raise ValueError(
                f"Element index {index} is stale or no longer visible. Use the refreshed browser state and choose a current index."
            )
        return locator
