from pathlib import Path

import pytest

from ui_bot.agent import UiAgent
from ui_bot.models import ChatRequest, FeedbackCreate, PageField, PageSnapshot
from ui_bot.storage import Storage


class FakeBrowser:
    def __init__(self) -> None:
        self.values = {}
        self.clicked = []
        self.scrolled = []
        self.back_count = 0
        self.snapshot_data = PageSnapshot(
            url="https://example.test/form",
            title="Form",
            fields=[
                PageField(
                    label="Email",
                    selector="input[name=email]",
                    field_type="email",
                    required=True,
                )
            ],
            buttons=["Preview"],
            actions=[
                {
                    "role": "button",
                    "text": "Preview",
                    "selector": "button.preview",
                    "href": "",
                },
                {
                    "role": "link",
                    "text": "Contact",
                    "selector": "a.contact",
                    "href": "https://example.test/contact",
                },
            ],
        )

    async def snapshot(self, session_id: str) -> PageSnapshot:
        return self.snapshot_data

    async def fill_form(self, session_id: str, values: dict[str, str]) -> PageSnapshot:
        self.values.update(values)
        self.snapshot_data.fields[0].value = values.get("Email")
        return self.snapshot_data

    async def navigate(self, session_id: str, url: str) -> PageSnapshot:
        self.snapshot_data.url = url
        return self.snapshot_data

    async def current_url(self, session_id: str) -> str:
        return self.snapshot_data.url

    async def click_text(
        self,
        session_id: str,
        text: str | None = None,
        selector: str | None = None,
    ) -> PageSnapshot:
        self.clicked.append({"text": text, "selector": selector})
        if text == "Contact":
            self.snapshot_data.url = "https://example.test/contact"
            self.snapshot_data.title = "Contact"
        return self.snapshot_data

    async def scroll(self, session_id: str, direction: str = "down") -> PageSnapshot:
        self.scrolled.append(direction)
        return self.snapshot_data

    async def go_back(self, session_id: str) -> PageSnapshot:
        self.back_count += 1
        return self.snapshot_data


@pytest.mark.asyncio
async def test_agent_asks_for_required_field(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")
    agent = UiAgent(
        browser=FakeBrowser(),
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    response = await agent.handle(ChatRequest(message="fill the form"))

    assert response.question == "Please provide values for: Email"
    storage.close()


@pytest.mark.asyncio
async def test_agent_fills_answered_field(tmp_path: Path) -> None:
    browser = FakeBrowser()
    storage = Storage(tmp_path / "test.sqlite3")
    agent = UiAgent(
        browser=browser,
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    response = await agent.handle(
        ChatRequest(message="fill the form", answers={"Email": "user@example.test"})
    )

    assert browser.values == {"Email": "user@example.test"}
    assert response.question is None
    storage.close()


@pytest.mark.asyncio
async def test_agent_uses_promoted_field_selector_template(tmp_path: Path) -> None:
    browser = FakeBrowser()
    storage = Storage(tmp_path / "test.sqlite3")
    storage.add_feedback(
        FeedbackCreate(
            session_id="session-1",
            kind="correct",
            url="https://example.test/form",
            correction={
                "kind": "field_selector",
                "field_label": "Email",
                "selector": "input[name=email]",
            },
        )
    )
    agent = UiAgent(
        browser=browser,
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    response = await agent.handle(
        ChatRequest(
            session_id="session-1",
            message="fill the form",
            answers={"Email": "user@example.test"},
        )
    )

    assert browser.values == {"input[name=email]": "user@example.test"}
    assert response.actions[0].fields == {"input[name=email]": "user@example.test"}
    assert storage.list_templates("https://example.test/form")[0].uses == 1
    storage.close()


@pytest.mark.asyncio
async def test_agent_clicks_resolved_target_without_llm(tmp_path: Path) -> None:
    browser = FakeBrowser()
    storage = Storage(tmp_path / "test.sqlite3")
    agent = UiAgent(
        browser=browser,
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    response = await agent.handle(ChatRequest(message="click Contact"))

    assert browser.clicked == [{"text": "Contact", "selector": "a.contact"}]
    assert response.actions[0].type == "click"
    assert response.snapshot.title == "Contact"
    storage.close()


@pytest.mark.asyncio
async def test_agent_asks_when_click_target_is_ambiguous(tmp_path: Path) -> None:
    browser = FakeBrowser()
    browser.snapshot_data.actions.append(
        {
            "role": "button",
            "text": "Contact",
            "selector": "button.contact",
            "href": "",
        }
    )
    storage = Storage(tmp_path / "test.sqlite3")
    agent = UiAgent(
        browser=browser,
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    response = await agent.handle(ChatRequest(message="click Contact"))

    assert response.question == "I found no clear clickable target for 'Contact'."
    assert not browser.clicked
    storage.close()


@pytest.mark.asyncio
async def test_agent_scrolls_and_goes_back_without_llm(tmp_path: Path) -> None:
    browser = FakeBrowser()
    storage = Storage(tmp_path / "test.sqlite3")
    agent = UiAgent(
        browser=browser,
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    scroll_response = await agent.handle(ChatRequest(message="scroll down"))
    back_response = await agent.handle(ChatRequest(message="go back"))

    assert browser.scrolled == ["down"]
    assert browser.back_count == 1
    assert scroll_response.actions[0].type == "scroll"
    assert back_response.actions[0].type == "back"
    storage.close()


@pytest.mark.asyncio
async def test_agent_syncs_widget_current_url_on_blank_page(tmp_path: Path) -> None:
    browser = FakeBrowser()
    browser.snapshot_data.url = "about:blank"
    storage = Storage(tmp_path / "test.sqlite3")
    agent = UiAgent(
        browser=browser,
        storage=storage,
        llm=None,
        llm_provider="openai",
    )

    response = await agent.handle(
        ChatRequest(message="inspect", current_url="https://example.test/widget-page")
    )

    assert response.snapshot.url == "https://example.test/widget-page"
    storage.close()
