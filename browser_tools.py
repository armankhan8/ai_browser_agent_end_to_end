from __future__ import annotations

import asyncio
import contextlib

from agents import RunContextWrapper, function_tool
from browser import BrowserSession


async def _state_after(ctx: RunContextWrapper[BrowserSession]) -> str:
    await ctx.context.after_action()
    return await ctx.context.state_for_agent()


def _tool_error_message(exc: Exception, state: str) -> str:
    return f"ACTION ERROR: {type(exc).__name__}: {exc}\n\nCURRENT BROWSER STATE:\n{state}"


@function_tool
async def get_page_state(ctx: RunContextWrapper[BrowserSession]) -> str:
    """Inspect the current webpage and return visible interactive elements with numeric indexes."""
    ctx.context.check_stop()
    ctx.context.log("👀 Inspecting the current page...")
    return await ctx.context.state_for_agent()


@function_tool
async def navigate(ctx: RunContextWrapper[BrowserSession], url: str) -> str:
    """Navigate the current browser tab to an HTTP or HTTPS URL.

    Args:
        url: Destination URL, for example https://www.youtube.com.
    """
    ctx.context.check_stop()
    page = ctx.context.require_page()
    try:
        destination = ctx.context.normalize_url(url)
        ctx.context.log(f"➡️ Navigate: {destination}")
        await page.goto(destination, wait_until="domcontentloaded")
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def click_element(ctx: RunContextWrapper[BrowserSession], index: int) -> str:
    """Click a visible interactive element by the numeric index from the latest browser state.

    Args:
        index: Element index shown in the latest page state, such as 3.
    """
    ctx.context.check_stop()
    try:
        locator = await ctx.context.locator_for_index(index)
        label = (await locator.get_attribute("aria-label")) or ""
        if not label:
            with contextlib.suppress(Exception):
                label = (await locator.text_content(timeout=1000)) or ""
        ctx.context.log(f"🖱️ Click element [{index}] {label.strip()[:80]!r}")
        await locator.scroll_into_view_if_needed()
        await locator.click()
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def type_text(
    ctx: RunContextWrapper[BrowserSession],
    index: int,
    text: str,
    clear_first: bool = True,
) -> str:
    """Type text into an input, textarea, or contenteditable element.

    Args:
        index: Element index shown in the latest page state.
        text: Text to enter.
        clear_first: If true, replace existing text; otherwise append to it.
    """
    ctx.context.check_stop()
    try:
        locator = await ctx.context.locator_for_index(index)
        ctx.context.log(f"⌨️ Type into [{index}]: {text[:100]!r}")
        await locator.scroll_into_view_if_needed()
        if clear_first:
            try:
                await locator.fill(text)
            except Exception:
                await locator.click()
                with contextlib.suppress(Exception):
                    await locator.press("ControlOrMeta+A")
                await locator.press_sequentially(text)
        else:
            await locator.click()
            await locator.press_sequentially(text)
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def press_key(ctx: RunContextWrapper[BrowserSession], key: str) -> str:
    """Press a keyboard key on the current page, such as Enter, Escape, Tab, ArrowDown, or ControlOrMeta+L.

    Args:
        key: Playwright keyboard key name or shortcut.
    """
    ctx.context.check_stop()
    page = ctx.context.require_page()
    try:
        ctx.context.log(f"⌨️ Press key: {key}")
        await page.keyboard.press(key)
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def scroll_page(ctx: RunContextWrapper[BrowserSession], direction: str = "down", amount: int = 700) -> str:
    """Scroll the current page to reveal more content.

    Args:
        direction: Either 'down' or 'up'.
        amount: Number of pixels to scroll, normally 400 to 1200.
    """
    ctx.context.check_stop()
    page = ctx.context.require_page()
    direction = direction.strip().lower()
    if direction not in {"down", "up"}:
        direction = "down"
    amount = max(100, min(abs(amount), 2000))
    delta = amount if direction == "down" else -amount
    try:
        ctx.context.log(f"🧭 Scroll {direction} {amount}px")
        await page.mouse.wheel(0, delta)
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def go_back(ctx: RunContextWrapper[BrowserSession]) -> str:
    """Go back one page in browser history."""
    ctx.context.check_stop()
    page = ctx.context.require_page()
    try:
        ctx.context.log("↩️ Browser back")
        await page.go_back(wait_until="domcontentloaded")
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def select_option(ctx: RunContextWrapper[BrowserSession], index: int, value: str) -> str:
    """Select an option from a visible HTML select element.

    Args:
        index: Select element index from the latest page state.
        value: Option value or visible label to select.
    """
    ctx.context.check_stop()
    try:
        locator = await ctx.context.locator_for_index(index)
        ctx.context.log(f"🔽 Select on [{index}]: {value!r}")
        try:
            await locator.select_option(value=value)
        except Exception:
            await locator.select_option(label=value)
        return await _state_after(ctx)
    except Exception as exc:
        state = await ctx.context.state_for_agent()
        return _tool_error_message(exc, state)


@function_tool
async def wait(ctx: RunContextWrapper[BrowserSession], seconds: float = 2.0) -> str:
    """Wait briefly for a dynamic page to update, then inspect it again.

    Args:
        seconds: Seconds to wait. Values are clamped between 0.2 and 8 seconds.
    """
    ctx.context.check_stop()
    seconds = max(0.2, min(float(seconds), 8.0))
    ctx.context.log(f"⏳ Wait {seconds:.1f}s")
    await asyncio.sleep(seconds)
    return await ctx.context.state_for_agent()


BROWSER_TOOLS = [
    get_page_state,
    navigate,
    click_element,
    type_text,
    press_key,
    scroll_page,
    go_back,
    select_option,
    wait,
]
