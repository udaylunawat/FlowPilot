import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ui_bot.agent import UiAgent
from ui_bot.browser import BrowserController
from ui_bot.config import get_settings
from ui_bot.llm import build_llm
from ui_bot.models import (
    ChatRequest,
    ChatResponse,
    FeedbackCreate,
    LocationCreate,
    SavedLocation,
    StoredFeedback,
    WorkflowRun,
    WorkflowTemplate,
)
from ui_bot.storage import Storage

settings = get_settings()
storage = Storage(settings.database_path)
browser = BrowserController(
    headless=settings.headless,
    timeout_ms=settings.browser_timeout_ms,
)
agent = UiAgent(
    browser=browser,
    storage=storage,
    llm=build_llm(settings),
    llm_provider=settings.llm_provider,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.get_running_loop().set_exception_handler(_handle_loop_exception)
    await browser.start()
    yield
    await browser.stop()
    storage.close()


def _handle_loop_exception(loop: asyncio.AbstractEventLoop, context: dict[str, Any]):
    exception = context.get("exception")
    message = str(exception or context.get("message", ""))
    ignored = (
        "Connection closed while reading from the driver",
        "Target page, context or browser has been closed",
    )
    if any(item in message for item in ignored):
        return
    loop.default_exception_handler(context)


app = FastAPI(title="UI Bot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="src/ui_bot/static"), name="static")
app.mount("/fixtures", StaticFiles(directory="fixtures", html=True), name="fixtures")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>UI Bot Demo</title>
        <style>
          body {
            font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont,
              sans-serif;
            margin: 0;
            padding: 40px;
            color: #17202a;
            background: #f7f8fa;
          }
          main { max-width: 760px; margin: 0 auto; }
          form {
            display: grid;
            gap: 12px;
            max-width: 420px;
            margin-top: 24px;
          }
          input, textarea, button {
            font: inherit;
            padding: 10px 12px;
            border: 1px solid #cad1d8;
            border-radius: 6px;
          }
          button {
            width: fit-content;
            background: #1f6feb;
            color: white;
            border-color: #1f6feb;
          }
        </style>
      </head>
      <body>
        <main>
          <h1>UI Bot Demo</h1>
          <p>
            Use the bottom-right assistant to navigate, inspect, and fill this form.
          </p>
          <form>
            <label>Name <input name="name" required autocomplete="name"></label>
            <label>
              Email
              <input name="email" type="email" required autocomplete="email">
            </label>
            <label>Notes <textarea name="notes"></textarea></label>
            <button type="button">Preview</button>
          </form>
        </main>
        <script src="/static/widget.js" data-api-base=""></script>
      </body>
    </html>
    """


@app.get("/api/health")
async def health() -> dict[str, str | bool]:
    return {
        "ok": True,
        "llm_provider": settings.llm_provider,
        "llm_configured": build_llm(settings) is not None,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await agent.handle(request)


@app.post("/api/locations", response_model=SavedLocation)
async def create_location(location: LocationCreate) -> SavedLocation:
    return storage.save_location(location)


@app.get("/api/locations", response_model=list[SavedLocation])
async def list_locations(session_id: str | None = None) -> list[SavedLocation]:
    return storage.list_locations(session_id=session_id)


@app.post("/api/feedback", response_model=StoredFeedback)
async def create_feedback(feedback: FeedbackCreate) -> StoredFeedback:
    return storage.add_feedback(feedback)


@app.get("/api/feedback", response_model=list[StoredFeedback])
async def list_feedback(session_id: str | None = None) -> list[StoredFeedback]:
    return storage.list_feedback(session_id=session_id)


@app.get("/api/workflows", response_model=list[WorkflowRun])
async def list_workflows(session_id: str | None = None) -> list[WorkflowRun]:
    return storage.list_workflow_runs(session_id=session_id)


@app.get("/api/workflow-templates", response_model=list[WorkflowTemplate])
async def list_workflow_templates(url: str | None = None) -> list[WorkflowTemplate]:
    return storage.list_templates(url=url)
