import json
import re
from uuid import uuid4

from ui_bot.browser import BrowserController
from ui_bot.llm import LLMClient
from ui_bot.models import AgentAction, ChatRequest, ChatResponse, LocationCreate
from ui_bot.storage import Storage

URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


class UiAgent:
    def __init__(
        self,
        browser: BrowserController,
        storage: Storage,
        llm: LLMClient | None,
        llm_provider: str,
    ) -> None:
        self.browser = browser
        self.storage = storage
        self.llm = llm
        self.llm_provider = llm_provider

    async def handle(self, request: ChatRequest) -> ChatResponse:
        session_id = request.session_id or str(uuid4())
        trace_id = str(uuid4())
        self.storage.start_workflow_run(trace_id, session_id, request.message)
        self.storage.add_message(session_id, "user", request.message)

        response = await self._handle(session_id, request)
        response.trace_id = trace_id

        self.storage.add_message(session_id, "assistant", response.message)
        if response.snapshot:
            self.storage.add_snapshot(
                session_id,
                response.snapshot.url,
                response.snapshot.title,
                response.snapshot.model_dump(),
            )
        for action in response.actions:
            self.storage.add_workflow_step(
                trace_id,
                session_id,
                action,
                result=response.message,
                url=response.snapshot.url if response.snapshot else "",
                title=response.snapshot.title if response.snapshot else "",
            )
        status = "needs_human" if response.question else "completed"
        self.storage.finish_workflow_run(trace_id, status)
        return response

    async def _handle(self, session_id: str, request: ChatRequest) -> ChatResponse:
        message = request.message.strip()
        url_match = URL_PATTERN.search(message)
        if url_match:
            snapshot = await self.browser.navigate(session_id, url_match.group(0))
            self._save_auto_location(session_id, snapshot.url, snapshot.title, snapshot)
            return ChatResponse(
                session_id=session_id,
                message=f"Opened {snapshot.title or snapshot.url}.",
                actions=[AgentAction(type="navigate", value=snapshot.url)],
                snapshot=snapshot,
            )

        await self._sync_initial_page(session_id, request)

        lowered = message.lower()
        if lowered in {"inspect", "snapshot", "what is on this page"}:
            snapshot = await self.browser.snapshot(session_id)
            self._save_auto_location(session_id, snapshot.url, snapshot.title, snapshot)
            return ChatResponse(
                session_id=session_id,
                message=_snapshot_summary(snapshot),
                actions=[AgentAction(type="snapshot")],
                snapshot=snapshot,
            )

        if "save" in lowered and "location" in lowered:
            snapshot = await self.browser.snapshot(session_id)
            self._save_auto_location(session_id, snapshot.url, snapshot.title, snapshot)
            return ChatResponse(
                session_id=session_id,
                message=f"Saved location for {snapshot.title or snapshot.url}.",
                actions=[AgentAction(type="save_location", value=snapshot.url)],
                snapshot=snapshot,
            )

        if lowered in {"back", "go back", "previous page"}:
            snapshot = await self.browser.go_back(session_id)
            return ChatResponse(
                session_id=session_id,
                message=f"Went back to {snapshot.title or snapshot.url}.",
                actions=[AgentAction(type="back")],
                snapshot=snapshot,
            )

        if lowered.startswith("scroll") or lowered in {"page down", "page up"}:
            direction = "up" if "up" in lowered else "down"
            snapshot = await self.browser.scroll(session_id, direction)
            return ChatResponse(
                session_id=session_id,
                message=f"Scrolled {direction}.",
                actions=[AgentAction(type="scroll", value=direction)],
                snapshot=snapshot,
            )

        click_target = _extract_click_target(message)
        if click_target:
            snapshot = await self.browser.snapshot(session_id)
            target = _resolve_click_target(snapshot.actions, click_target)
            if target is None:
                question = f"I found no clear clickable target for '{click_target}'."
                return ChatResponse(
                    session_id=session_id,
                    message=question,
                    question=question,
                    actions=[
                        AgentAction(
                            type="ask",
                            value=click_target,
                            reason="click_target_not_found",
                        )
                    ],
                    snapshot=snapshot,
                )
            next_snapshot = await self.browser.click_text(
                session_id,
                text=target.get("text") or click_target,
                selector=target.get("selector"),
            )
            return ChatResponse(
                session_id=session_id,
                message=f"Clicked {target.get('text') or click_target}.",
                actions=[
                    AgentAction(
                        type="click",
                        value=target.get("text") or click_target,
                        selector=target.get("selector"),
                    )
                ],
                snapshot=next_snapshot,
            )

        if "fill" in lowered or request.answers:
            return await self._fill_or_ask(session_id, request)

        if self.llm is None:
            return ChatResponse(
                session_id=session_id,
                message=(
                    f"I need an LLM provider for that interpretation. Configure "
                    f"{self.llm_provider} in .env or use a direct command like "
                    f"'open https://example.com'."
                ),
                question="Which page or exact form fields should I act on?",
                actions=[AgentAction(type="ask", reason="llm_provider_not_configured")],
            )

        return await self._llm_plan(session_id, request)

    async def _sync_initial_page(
        self,
        session_id: str,
        request: ChatRequest,
    ) -> None:
        if request.current_url is None:
            return
        current = await self.browser.current_url(session_id)
        if current == "about:blank":
            await self.browser.navigate(session_id, str(request.current_url))

    async def _fill_or_ask(self, session_id: str, request: ChatRequest) -> ChatResponse:
        snapshot = await self.browser.snapshot(session_id)
        required_missing = [
            field.label
            for field in snapshot.fields
            if field.required and not field.value
        ]
        provided = {key.lower() for key in request.answers}
        unanswered = [
            field for field in required_missing if field.lower() not in provided
        ]

        if unanswered:
            question = "Please provide values for: " + ", ".join(unanswered)
            return ChatResponse(
                session_id=session_id,
                message=question,
                question=question,
                actions=[
                    AgentAction(
                        type="ask",
                        reason="required_form_values_missing",
                    )
                ],
                snapshot=snapshot,
            )

        values = dict(request.answers) or _extract_inline_fields(request.message)
        if not values and self.llm is not None:
            values = await self._llm_extract_fields(
                request.message,
                snapshot.model_dump(),
            )
        if not values:
            question = "Which fields should I fill, and what values should I use?"
            return ChatResponse(
                session_id=session_id,
                message=question,
                question=question,
                actions=[AgentAction(type="ask", reason="no_field_values")],
                snapshot=snapshot,
            )

        values = self._apply_field_templates(values, snapshot.url)
        next_snapshot = await self.browser.fill_form(session_id, values)
        return ChatResponse(
            session_id=session_id,
            message=(
                "Filled the matching fields. I have not submitted the form. "
                "Please approve, correct, or reject this action."
            ),
            actions=[AgentAction(type="fill", fields=values)],
            snapshot=next_snapshot,
        )

    async def _llm_extract_fields(self, message: str, snapshot: dict) -> dict[str, str]:
        if self.llm is None:
            return {}
        system = (
            "Extract form-fill values from the user request. Return JSON with one "
            "object key named fields. Use page field labels as keys when possible. "
            "Do not invent values."
        )
        data = await self.llm.complete_json(
            system=system,
            user=json.dumps({"message": message, "page": snapshot}),
        )
        fields = data.get("fields", {})
        return fields if isinstance(fields, dict) else {}

    async def _llm_plan(self, session_id: str, request: ChatRequest) -> ChatResponse:
        snapshot = await self.browser.snapshot(session_id)
        system = (
            "Plan one safe browser action for a Playwright UI agent. Return JSON with "
            "action in navigate, snapshot, fill, click, scroll, back, ask, "
            "save_location; value; selector; fields; question; message. Prefer "
            "selectors from page.actions for clicks. Ask questions instead of guessing."
        )
        data = await self.llm.complete_json(
            system=system,
            user=json.dumps(
                {
                    "message": request.message,
                    "answers": request.answers,
                    "page": snapshot.model_dump(),
                }
            ),
        )
        action = data.get("action", "ask")
        if action == "click" and (data.get("value") or data.get("selector")):
            next_snapshot = await self.browser.click_text(
                session_id,
                text=str(data.get("value") or ""),
                selector=data.get("selector"),
            )
            return ChatResponse(
                session_id=session_id,
                message=data.get("message")
                or f"Clicked {data.get('value') or data.get('selector')}.",
                actions=[
                    AgentAction(
                        type="click",
                        value=str(data.get("value") or ""),
                        selector=data.get("selector"),
                    )
                ],
                snapshot=next_snapshot,
            )
        if action == "scroll":
            direction = str(data.get("value") or "down")
            next_snapshot = await self.browser.scroll(session_id, direction)
            return ChatResponse(
                session_id=session_id,
                message=data.get("message") or f"Scrolled {direction}.",
                actions=[AgentAction(type="scroll", value=direction)],
                snapshot=next_snapshot,
            )
        if action == "back":
            next_snapshot = await self.browser.go_back(session_id)
            return ChatResponse(
                session_id=session_id,
                message=data.get("message") or "Went back.",
                actions=[AgentAction(type="back")],
                snapshot=next_snapshot,
            )
        if action == "fill" and isinstance(data.get("fields"), dict):
            fields = self._apply_field_templates(data["fields"], snapshot.url)
            next_snapshot = await self.browser.fill_form(session_id, fields)
            return ChatResponse(
                session_id=session_id,
                message=data.get("message")
                or (
                    "Filled the matching fields. Please approve, correct, or reject "
                    "this action."
                ),
                actions=[AgentAction(type="fill", fields=fields)],
                snapshot=next_snapshot,
            )
        question = data.get("question") or "What should I do next?"
        return ChatResponse(
            session_id=session_id,
            message=data.get("message") or question,
            question=question,
            actions=[AgentAction(type="ask", reason="llm_requested_clarification")],
            snapshot=snapshot,
        )

    def _save_auto_location(
        self,
        session_id: str,
        url: str,
        title: str,
        snapshot,
    ) -> None:
        self.storage.save_location(
            LocationCreate(
                session_id=session_id,
                name=title or url,
                url=url,
                title=title,
                notes="Auto-saved from agent navigation.",
                metadata=snapshot.model_dump(),
            )
        )

    def _apply_field_templates(
        self,
        values: dict[str, str],
        url: str,
    ) -> dict[str, str]:
        updated = dict(values)
        templates = self.storage.list_templates(url=url)
        for template in templates:
            if template.kind != "field_selector":
                continue
            for field_label, value in list(updated.items()):
                if _normalize(field_label) != _normalize(template.field_label):
                    continue
                updated.pop(field_label)
                updated[template.selector] = value
                self.storage.increment_template_use(template.id)
        return updated


def _extract_inline_fields(message: str) -> dict[str, str]:
    pairs = re.findall(r"([\w\s-]{2,40})\s*[:=]\s*([^,;]+)", message)
    return {key.strip(): value.strip() for key, value in pairs}


def _extract_click_target(message: str) -> str | None:
    match = re.search(
        r"^(?:click|press|select|open)\s+(?:the\s+)?(.+?)(?:\s+(?:button|link))?$",
        message.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    target = match.group(1).strip().strip("\"'")
    if target.lower().startswith("http"):
        return None
    return target


def _resolve_click_target(
    actions: list[dict[str, str]],
    target: str,
) -> dict[str, str] | None:
    normalized = _normalize(target)
    exact = [
        action for action in actions if _normalize(action.get("text", "")) == normalized
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [
        action
        for action in actions
        if normalized and normalized in _normalize(action.get("text", ""))
    ]
    if len(partial) == 1:
        return partial[0]
    return None


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _snapshot_summary(snapshot) -> str:
    parts = [f"Page: {snapshot.title or snapshot.url}."]
    if snapshot.fields:
        field_names = ", ".join(field.label for field in snapshot.fields[:8])
        parts.append(f"Fields: {field_names}.")
    if snapshot.buttons:
        parts.append(f"Buttons: {', '.join(snapshot.buttons[:8])}.")
    return " ".join(parts)
