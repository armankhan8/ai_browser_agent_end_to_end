from __future__ import annotations

from agents import Agent, ModelSettings, RunConfig, Runner
from agents.run_config import ToolExecutionConfig

from browser import BrowserSession
from browser_tools import BROWSER_TOOLS
from config import Settings


AGENT_INSTRUCTIONS = """
You are an autonomous web-browser agent controlling one real Chromium tab through Playwright tools.

Your job is to complete the user's browser task accurately with minimal actions.

Operating rules:
1. Use only the provided browser tools to interact with websites. Never pretend you clicked, typed, opened, or played something if you did not actually do it.
2. The browser state contains visible interactive elements with numeric indexes. Use those indexes only from the most recent returned state.
3. Perform one browser action at a time. After every action, read the updated state returned by the tool and decide the next action.
4. Prefer direct navigation to an official URL when the destination is obvious (for example, https://www.youtube.com or https://www.google.com).
5. If the target element is not visible, inspect the state, scroll, or wait. If an action fails because the DOM changed, use the fresh state in the error result and retry with a current index.
6. For search boxes, type the requested query and normally press Enter unless the page clearly provides a better visible search action.
7. Treat success as something you can verify from the current page. Do not stop merely because an action was attempted.
8. Do not solve CAPTCHAs, bypass access controls, or guess passwords/credentials. If a login/CAPTCHA blocks the task, explain that human interaction is required.
9. Do not make purchases, payments, delete data, publish/send messages, or confirm irreversible actions unless the user explicitly asked for that exact action. Even when explicitly requested, do not handle passwords, payment-card data, one-time codes, or other secrets.
10. Keep the final response short: say what was completed and mention any blocker if the task could not be completed.
""".strip()


def create_browser_agent(settings: Settings, model: str | None = None) -> Agent[BrowserSession]:
    selected_model = (model or settings.model).strip() or settings.model
    return Agent[BrowserSession](
        name="Autonomous Browser Agent",
        model=selected_model,
        instructions=AGENT_INSTRUCTIONS,
        tools=BROWSER_TOOLS,
        model_settings=ModelSettings(parallel_tool_calls=False),
    )


async def run_browser_agent(
    session: BrowserSession,
    user_task: str,
    model: str | None = None,
) -> str:
    agent = create_browser_agent(session.settings, model=model)
    initial_state = await session.state_for_agent()

    prompt = (
        "USER TASK:\n"
        f"{user_task.strip()}\n\n"
        "INITIAL BROWSER STATE:\n"
        f"{initial_state}\n\n"
        "Complete the task using the browser tools."
    )

    result = await Runner.run(
        agent,
        prompt,
        context=session,
        max_turns=session.settings.max_turns,
        run_config=RunConfig(
            tool_execution=ToolExecutionConfig(max_function_tool_concurrency=1),
            tool_not_found_behavior="return_error_to_model",
        ),
    )
    return str(result.final_output)
