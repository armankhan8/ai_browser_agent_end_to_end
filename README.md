# AI Browser Agent

A small end-to-end autonomous browser project built specifically around:

- **OpenAI Agents SDK** — agent loop and function-tool calling
- **Playwright** — deterministic browser actions
- **Chromium** — the real browser controlled by Playwright
- **Gradio** — simple local UI
- **python-dotenv / `.env`** — API key and runtime configuration

There is **no MCP, no LangChain, and no browser-use** in this version.

## What it does

You enter a normal-language task such as:

> Open YouTube, search for Python tutorials, and open the first relevant video.

The app launches Chromium. The agent observes a compact representation of the visible page, chooses one browser tool at a time, Playwright executes it, and the tool returns the updated page state. This repeats until the task is complete or blocked.

## Architecture

```text
User task
   ↓
Gradio UI
   ↓
OpenAI Agent (Agents SDK)
   ↓
Function tools
   ↓
BrowserSession
   ↓
Playwright async API
   ↓
Chromium
   ↑
Updated page state after each action
```

## Browser tools

The agent has these local tools:

- `get_page_state()`
- `navigate(url)`
- `click_element(index)`
- `type_text(index, text, clear_first=True)`
- `press_key(key)`
- `scroll_page(direction, amount)`
- `go_back()`
- `select_option(index, value)`
- `wait(seconds)`

The page inspector assigns temporary `data-ai-browser-id` indexes to visible interactive elements. The model never receives the entire raw HTML; it receives the current URL, title, visible text, and a compact list like:

```text
[0] <button> role=button name="Search"
[1] <input> role=textbox name="Search" placeholder="Search"
[2] <a> role=link name="Python Tutorial"
```

After every action the IDs are regenerated, so the agent must use indexes only from the latest state.

---

# Run in VS Code

## Requirements

- Python **3.11 or 3.12 recommended**
- Internet connection
- An OpenAI API key

## Windows

1. Unzip the project and open the folder in VS Code.
2. Run:

```bat
setup_windows.bat
```

3. Open `.env` and replace:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

with your real key.

4. Run:

```bat
run_windows.bat
```

## macOS / Linux

```bash
chmod +x setup_mac_linux.sh run_mac_linux.sh
./setup_mac_linux.sh
```

Edit `.env` and add your real API key, then:

```bash
./run_mac_linux.sh
```

## Manual setup (all platforms)

```bash
python -m venv .venv
```

Activate it, then:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
python smoke_test.py
python app.py
```

Gradio opens at:

```text
http://127.0.0.1:7860
```

A Chromium window also opens when you run a task if `HEADLESS=false`.

---

# `.env` settings

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.6-luna
HEADLESS=false
MAX_AGENT_TURNS=30
BROWSER_TIMEOUT_MS=15000
ACTION_DELAY_MS=650
MAX_INTERACTIVE_ELEMENTS=90
PAGE_TEXT_CHARS=3000
GRADIO_HOST=127.0.0.1
GRADIO_PORT=7860
```

`gpt-5.6-luna` is the default configured model. You can also change the model directly in the UI.

---

# Good demo tasks

Start with deterministic, public websites:

```text
Go to Google and search for OpenAI Agents SDK.
```

```text
Open Wikipedia and search for Artificial intelligence.
```

```text
Go to python.org and open the Downloads page.
```

For your reel, try:

```text
Open YouTube, search for lo-fi coding music, and play the first relevant video.
```

YouTube can occasionally show consent dialogs, ads, region-specific UI, sign-in prompts, or anti-automation checks. Those are website behaviors, not a hard-coded part of this project. If a login/CAPTCHA blocks the flow, the agent is instructed not to bypass it.

---

# Files

```text
ai_browser_agent_instagram/
├── app.py                 # Gradio UI + per-session lifecycle
├── agent.py               # OpenAI Agent + Runner configuration
├── browser.py             # Playwright BrowserSession + DOM state extraction
├── browser_tools.py       # Function tools exposed to the agent
├── config.py              # .env loading and settings
├── smoke_test.py          # Playwright/Chromium test; no API tokens
├── requirements.txt
├── .env                   # placeholder; put your key here locally
├── .env.example
├── .gitignore
├── setup_windows.bat
├── run_windows.bat
├── setup_mac_linux.sh
├── run_mac_linux.sh
└── README.md
```

## Important implementation details

- The same Chromium session is reused across actions in one browser session.
- Provider-side parallel tool calls are disabled.
- SDK-side local function-tool concurrency is limited to one action at a time.
- Tools return the **new page state** after the action, reducing extra inspection calls.
- `navigate()` accepts only `http://` and `https://` destinations.
- Stop cancels the active Agents SDK runner task.
- Close Browser shuts down Playwright and Chromium cleanly.

## Scope

This is intentionally a focused V1 for browser-agent demos and learning. It does not try to automate CAPTCHAs, credentials, payments, or other protected/irreversible workflows.

## Optional environment check

Before adding API usage, you can verify only the browser layer with:

```bash
python smoke_test.py
```

This launches Chromium headlessly, inspects a local in-memory page, types into an indexed element, and exits. It does **not** call OpenAI and uses no API tokens.
