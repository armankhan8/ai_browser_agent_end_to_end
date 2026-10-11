from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

import gradio as gr

from agent import run_browser_agent
from browser import BrowserSession
from config import get_settings


SETTINGS = get_settings()
SESSIONS: dict[str, BrowserSession] = {}


def _session_key(request: gr.Request | None) -> str:
    if request is not None and request.session_hash:
        return request.session_hash
    return "local-default"


def _get_session(request: gr.Request | None) -> BrowserSession:
    key = _session_key(request)
    if key not in SESSIONS:
        SESSIONS[key] = BrowserSession(settings=SETTINGS)
    return SESSIONS[key]


def _logs_text(session: BrowserSession) -> str:
    return "\n".join(session.logs[-120:])


async def run_task(
    task: str,
    model: str,
    headless: bool,
    request: gr.Request,
) -> AsyncIterator[tuple[str, str, str, str]]:
    session = _get_session(request)
    task = (task or "").strip()
    model = (model or SETTINGS.model).strip() or SETTINGS.model

    if not task:
        yield "Please enter a browser task.", "", "", ""
        return

    if not SETTINGS.openai_api_key or SETTINGS.openai_api_key.lower().startswith("your_"):
        yield (
            "Missing OPENAI_API_KEY",
            "Add your OpenAI API key to the .env file, restart the app, then run the task again.",
            "",
            "",
        )
        return

    async with session.run_lock:
        session.reset_run_state()
        session.log(f"🧠 Model: {model}")
        session.log(f"🎯 Task: {task}")
        session.status = "Launching browser"
        yield session.status, _logs_text(session), "", ""

        try:
            await session.ensure_started(headless=headless)
            session.status = "Agent running"
            state = await session.page_state()
            yield session.status, _logs_text(session), "", state.get("url", "")

            run_coro = run_browser_agent(session=session, user_task=task, model=model)
            session.current_run_task = asyncio.create_task(run_coro)
            last_log_len = -1

            while not session.current_run_task.done():
                if len(session.logs) != last_log_len:
                    last_log_len = len(session.logs)
                    current_url = session.page.url if session.page is not None else ""
                    yield session.status, _logs_text(session), "", current_url
                await asyncio.sleep(0.2)

            final_output = await session.current_run_task
            session.status = "Completed"
            session.log("✅ Agent finished.")
            current_url = session.page.url if session.page is not None else ""
            yield session.status, _logs_text(session), final_output, current_url

        except asyncio.CancelledError:
            session.status = "Stopped"
            session.log("⏹ Run stopped.")
            current_url = session.page.url if session.page is not None else ""
            yield session.status, _logs_text(session), "The run was stopped.", current_url
        except Exception as exc:
            session.status = "Error"
            message = f"{type(exc).__name__}: {exc}"
            session.log(f"❌ {message}")
            current_url = session.page.url if session.page is not None else ""
            yield session.status, _logs_text(session), message, current_url
        finally:
            session.current_run_task = None


async def stop_task(request: gr.Request) -> tuple[str, str]:
    session = _get_session(request)
    session.request_stop()
    return session.status, _logs_text(session)


async def close_browser(request: gr.Request) -> tuple[str, str, str]:
    session = _get_session(request)
    session.request_stop()
    await session.close()
    session.log("🧹 Browser closed.")
    return "Browser closed", _logs_text(session), ""


CSS = """
.gradio-container {max-width: 1180px !important; margin: 0 auto !important;}
.hero {text-align: center; margin-bottom: 8px;}
.hero h1 {font-size: 2rem; margin-bottom: 4px;}
.muted {opacity: 0.75;}
"""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="AI Browser Agent") as demo:
        gr.HTML(
            """
            <div class="hero">
              <h1>🤖 AI Browser Agent</h1>
              <div class="muted">OpenAI Agents SDK + Playwright + Chromium</div>
            </div>
            """
        )

        with gr.Row():
            task = gr.Textbox(
                label="Browser task",
                placeholder="Example: Open YouTube, search for lo-fi coding music, and play the first relevant video.",
                lines=3,
                scale=4,
            )
            with gr.Column(scale=1):
                run_btn = gr.Button("▶ Run Agent", variant="primary")
                stop_btn = gr.Button("⏹ Stop")
                close_btn = gr.Button("✖ Close Browser")

        with gr.Accordion("Settings", open=False):
            model = gr.Textbox(label="OpenAI model", value=SETTINGS.model)
            headless = gr.Checkbox(label="Headless browser", value=SETTINGS.headless)
            gr.Markdown(
                "For Instagram/demo recording, keep **Headless browser off** so Chromium opens visibly."
            )

        with gr.Row():
            status = gr.Textbox(label="Status", value="Idle", interactive=False, scale=1)
            current_url = gr.Textbox(label="Current URL", interactive=False, scale=3)

        activity = gr.Textbox(
            label="Agent Activity",
            lines=14,
            interactive=False,
            autoscroll=True,
        )
        final_result = gr.Textbox(label="Final Result", lines=4, interactive=False)

        gr.Examples(
            examples=[
                ["Open YouTube, search for Python tutorials, and open the first relevant video."],
                ["Go to Google and search for OpenAI Agents SDK."],
                ["Open Wikipedia and search for Artificial intelligence."],
                ["Go to python.org and open the Downloads page."],
            ],
            inputs=[task],
        )

        run_btn.click(
            fn=run_task,
            inputs=[task, model, headless],
            outputs=[status, activity, final_result, current_url],
            concurrency_limit=4,
        )
        task.submit(
            fn=run_task,
            inputs=[task, model, headless],
            outputs=[status, activity, final_result, current_url],
            concurrency_limit=4,
        )
        stop_btn.click(
            fn=stop_task,
            inputs=None,
            outputs=[status, activity],
            concurrency_limit=20,
        )
        close_btn.click(
            fn=close_browser,
            inputs=None,
            outputs=[status, activity, current_url],
            concurrency_limit=20,
        )

    return demo


def main() -> None:
    # The Agents SDK reads OPENAI_API_KEY lazily from the environment.
    if SETTINGS.openai_api_key:
        os.environ["OPENAI_API_KEY"] = SETTINGS.openai_api_key

    demo = build_ui()
    demo.queue(default_concurrency_limit=8).launch(
        server_name=SETTINGS.gradio_host,
        server_port=SETTINGS.gradio_port,
        show_error=True,
        inbrowser=True,
        css=CSS,
    )


if __name__ == "__main__":
    main()
