# UI Bot Spec

## Goal

Build a reusable UI automation agent that can navigate websites, fill forms, and ask the user for missing or ambiguous information instead of guessing. The product should work as a bottom-right chat widget, accept voice or typed commands, and store enough page/location metadata to reuse successful flows later.

## Non-Goals

- Full autonomous checkout, financial transaction, or account-management execution without a confirmation layer.
- Login, signup, account management, or user identity flows.
- A browser-agent benchmark harness.
- A hosted cloud browser service.
- Long-term secret storage beyond environment variables.

## User Experience

1. The user opens a page with the widget installed.
2. The user types or speaks an instruction.
3. The backend creates or resumes an automation session.
4. The agent uses deterministic Playwright actions first.
5. If a deterministic action cannot be inferred safely, the agent asks a specific question.
6. If page semantics require interpretation, the agent can call the configured LLM provider.
7. Important page states are stored as locations so a future workflow can reuse them.
8. The user can approve, reject, correct, or mark the workflow done after an agent action.
9. Corrections are saved as reusable templates for matching future pages.

## Agent Rules

- Ask for required form values when they are missing.
- Ask for clarification when multiple matching fields or buttons exist.
- Do not invent personal data, addresses, credentials, or form values.
- Do not submit a form when the user only asked to fill it.
- Save URL, title, discovered fields, and action notes after navigation or form inspection.
- Prefer Playwright selectors and accessible labels over generated coordinates.
- Use an LLM only for interpretation, planning, or fallback recovery.
- Check stored human corrections and workflow templates before LLM planning.

## Architecture

- `ui_bot.main`: FastAPI app, routes, and static demo hosting.
- `ui_bot.agent`: task orchestration and question-first policy.
- `ui_bot.browser`: Playwright browser/session controller.
- `ui_bot.llm`: OpenRouter free-model fallback, OpenAI, and Gemini adapters.
- `ui_bot.storage`: SQLite persistence for sessions, messages, snapshots, and locations.
- `ui_bot.static.widget.js`: embeddable bottom-right widget with voice support.

## Persistence

SQLite stores:

- Sessions: browser/chat session identity and timestamps.
- Messages: user and assistant turns.
- Page snapshots: URL, title, fields, buttons, and links.
- Locations: reusable saved URL/page metadata and notes.
- Workflow runs: user goal, trace id, status, and timestamps.
- Workflow steps: action payloads, result text, URL, and page title.
- Human feedback: approval, rejection, correction, or done markers.
- Workflow templates: promoted corrections such as stable field selectors.

The default database path is `./data/ui_bot.sqlite3`.

## LLM Providers

Supported providers:

- `openrouter`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_MODELS`.
- `openai`: `OPENAI_API_KEY`, `OPENAI_MODEL`, optional `OPENAI_BASE_URL`.
- `gemini`: `GEMINI_API_KEY`, `GEMINI_MODEL`.

The active provider is selected by `LLM_PROVIDER`. The default is `openrouter`
with a free-model fallback chain based on the SignalRank OpenRouter client. If
no provider is configured, deterministic browser commands still work and the
agent returns a setup question when LLM planning is required.

## Browser Behavior

The first implementation supports:

- Navigate to a URL.
- Snapshot current page metadata.
- Fill visible form controls by label, placeholder, name, id, or aria label.
- Click a visible button or link by resolved text and CSS selector.
- Scroll up or down.
- Go back to the previous browser history entry.
- Save a current page location.

## Safety

- `.env` is ignored and `.env.example` documents expected keys.
- Provider keys are read only from environment variables.
- The backend should not log raw request bodies containing secrets.
- Before submit-style actions, the agent should request explicit confirmation.

## HITL Feedback

Supported feedback kinds:

- `approve`: action was correct.
- `reject`: action was wrong or unsafe.
- `correct`: action needs a structured correction.
- `done`: workflow reached the user's intended endpoint.

The first promoted correction type is `field_selector`, which stores the page
URL pattern, human field label, and preferred CSS selector. On future matching
pages the agent rewrites that field label to the stored selector before filling.

## Update Log

- 2026-04-25: Marked login/signup/account flows out of scope for now.
- 2026-04-25: Added HITL workflow tracing, feedback capture, and promoted field-selector templates.
- 2026-04-25: Switched default LLM provider to OpenRouter free-model fallback while retaining OpenAI and Gemini support.
- 2026-04-25: Created initial spec, uv/FastAPI scaffold, provider adapters, Playwright controller, widget, Docker, and checks.
