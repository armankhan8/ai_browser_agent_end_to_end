from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    model: str
    headless: bool
    max_turns: int
    browser_timeout_ms: int
    action_delay_ms: int
    max_elements: int
    page_text_chars: int
    gradio_host: str
    gradio_port: int


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna",
        headless=_as_bool(os.getenv("HEADLESS"), False),
        max_turns=max(5, int(os.getenv("MAX_AGENT_TURNS", "30"))),
        browser_timeout_ms=max(1_000, int(os.getenv("BROWSER_TIMEOUT_MS", "15000"))),
        action_delay_ms=max(0, int(os.getenv("ACTION_DELAY_MS", "650"))),
        max_elements=max(20, int(os.getenv("MAX_INTERACTIVE_ELEMENTS", "90"))),
        page_text_chars=max(500, int(os.getenv("PAGE_TEXT_CHARS", "3000"))),
        gradio_host=os.getenv("GRADIO_HOST", "127.0.0.1").strip() or "127.0.0.1",
        gradio_port=int(os.getenv("GRADIO_PORT", "7860")),
    )
