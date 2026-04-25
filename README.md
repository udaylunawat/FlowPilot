# FlowPilot

FlowPilot is a local-first browser automation assistant with a bottom-right chat
widget, voice input, Playwright browser control, and LLM fallback planning. It
is designed to become a reusable template for web tasks that need page
navigation, form filling, saved locations, and explicit user questions when
required data is missing.

## Current Scope

- FastAPI backend with `/api/chat`, health, and saved-location endpoints.
- Playwright browser controller for navigation, page snapshots, form filling, and clicks.
- LLM providers for OpenRouter free-model fallback, OpenAI, and Gemini.
- Bottom-right embeddable chat widget with text and browser voice input.
- Human-in-the-loop feedback capture with approval, rejection, correction, and
  reusable workflow templates.
- SQLite storage for sessions, messages, page snapshots, and reusable locations.
- Docker and `uv` package management.

See [docs/spec.md](docs/spec.md) for product behavior, architecture, and the update log.
See [docs/testing.md](docs/testing.md) for workflow and voice-control test cases.

## Reference Projects

This scaffold takes inspiration from active browser-agent projects without depending on any one of them:

- [browser-use](https://github.com/browser-use/browser-use) for Playwright-backed agent workflows.
- [Stagehand](https://github.com/browserbase/stagehand-python) for mixing deterministic automation with AI recovery.
- [LaVague](https://github.com/lavague-ai/LaVague) for natural-language web actions.
- [HyperAgent](https://github.com/hyperbrowserai/HyperAgent) for Playwright-first LLM browser control.

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Edit `.env` with whichever provider you want to use. The default provider is
OpenRouter and the default model list uses free models. Do not commit `.env`.

## Run

```bash
uv run uvicorn ui_bot.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) for the demo page. The
widget script is available at `/static/widget.js` and can be embedded in another
page:

```html
<script src="http://localhost:8000/static/widget.js" data-api-base="http://localhost:8000"></script>
```

## Test With A Locally Downloaded React Website

FlowPilot ships with a local fixture under `fixtures/react-site/`. It includes a
downloaded `react.dev` HTML snapshot plus a React-style page with navigation,
search, select, checkbox, and support form fields.

Start the app:

```bash
uv run uvicorn ui_bot.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000/fixtures/react-site/
```

Try these widget commands:

```text
inspect
click Support
fill the form
```

When the bot asks for values, provide:

```json
{
  "Name": "React Tester",
  "Email": "tester@example.test",
  "Topic": "Deployment",
  "Message": "Please help test this UI navigator workflow.",
  "Send me updates": "yes"
}
```

Then run:

```text
click Review request
```

To test your own downloaded React website, put its files under `fixtures/`, for
example:

```text
fixtures/my-react-site/index.html
```

Inject the widget before `</body>` in the downloaded page:

```html
<script
  src="/static/widget.js"
  data-api-base="http://localhost:8000"
></script>
```

Then open:

```text
http://localhost:8000/fixtures/my-react-site/
```

If the downloaded site uses absolute asset URLs or strict CSP, keep the fixture
simple first: save the HTML locally, preserve visible links/forms, and use
FlowPilot to validate navigation, form discovery, HITL corrections, and
selector reuse before trying a full mirrored asset copy.

## Chrome Extension

The minimal unpacked Chrome extension lives in `extensions/chrome/`. It injects
the same bottom-right FlowPilot widget into ordinary `http` and `https` pages
and sends chat/feedback requests to your local backend.

Start FlowPilot first:

```bash
uv run uvicorn ui_bot.main:app --reload --host 0.0.0.0 --port 8000
```

Load the extension:

1. Open `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked`.
4. Select the repo folder `extensions/chrome`.
5. Open any test page and reload it.

The extension defaults to `http://127.0.0.1:8000`. If your server is running on
another port, open the FlowPilot extension popup, change `Local backend URL`,
click `Save`, and reload the page.

Suggested extension test pages:

```text
http://localhost:8000/fixtures/react-site/
https://example.com
https://httpbin.org/forms/post
```

Suggested commands:

```text
inspect
click Support
fill the form
scroll down
go back
```

Some production sites block extension-like behavior, cross-origin requests, or
speech recognition. For those, start with the local fixture and then test real
sites one at a time.

## Docker

```bash
docker compose up --build
```

The service listens on [http://localhost:8000](http://localhost:8000). SQLite data is stored in the `ui_bot_data` volume.

## API

```bash
curl -s http://localhost:8000/api/health
```

```bash
curl -s http://localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"open https://example.com"}'
```

```bash
curl -s http://localhost:8000/api/feedback \
  -H 'content-type: application/json' \
  -d '{
    "session_id":"session-id",
    "trace_id":"trace-id",
    "kind":"correct",
    "url":"https://example.com/contact",
    "correction":{
      "kind":"field_selector",
      "field_label":"Email",
      "selector":"input[name=email]"
    }
  }'
```

## LLM Providers

OpenRouter is the default provider. Set `OPENROUTER_API_KEY` in `.env`; the
client will probe the first free models and fall back through:

```text
google/gemma-4-31b-it:free
arcee-ai/trinity-large-preview:free
google/gemma-4-26b-a4b-it:free
openai/gpt-oss-120b:free
google/gemma-3-4b-it:free
```

OpenAI and Gemini remain supported with `LLM_PROVIDER=openai` or
`LLM_PROVIDER=gemini`.

## HITL Learning

Every chat turn creates a workflow trace. Feedback from the widget or
`/api/feedback` is stored with the trace, URL, action, and correction payload.
Field-selector corrections are promoted into reusable templates and checked
before future LLM planning.

## Checks

```bash
just check
```

Equivalent commands:

```bash
uv run ruff check .
uv run black --check .
uv run pytest
```

## Secret Handling

Secrets are loaded from `.env` or environment variables. Never hardcode provider keys in source, tests, docs, Docker images, or prompts.
