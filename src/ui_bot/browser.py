from collections.abc import Mapping
from contextlib import suppress

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ui_bot.models import PageField, PageSnapshot


class BrowserController:
    def __init__(self, headless: bool, timeout_ms: int) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}

    async def start(self) -> None:
        if self._playwright is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def stop(self) -> None:
        for page in self._pages.values():
            with suppress(Exception):
                await page.close()
        for context in self._contexts.values():
            with suppress(Exception):
                await context.close()
        self._contexts.clear()
        self._pages.clear()
        if self._browser and self._browser.is_connected():
            with suppress(Exception):
                await self._browser.close()
        self._browser = None
        if self._playwright:
            with suppress(Exception):
                await self._playwright.stop()
        self._playwright = None

    async def navigate(self, session_id: str, url: str) -> PageSnapshot:
        page = await self._page(session_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        return await self.snapshot(session_id)

    async def current_url(self, session_id: str) -> str:
        page = await self._page(session_id)
        return page.url

    async def snapshot(self, session_id: str) -> PageSnapshot:
        page = await self._page(session_id)
        data = await page.evaluate("""
            () => {
              const textOf = (node) => (node?.innerText || node?.textContent || "")
                .replace(/\\s+/g, " ").trim();
              const directTextOf = (node) => Array.from(node?.childNodes || [])
                .filter((child) => child.nodeType === Node.TEXT_NODE)
                .map((child) => child.textContent || "")
                .join(" ")
                .replace(/\\s+/g, " ")
                .trim();
              const cssPath = (el) => {
                if (el.id) return `#${CSS.escape(el.id)}`;
                const tag = el.tagName.toLowerCase();
                const name = el.getAttribute("name");
                if (name) return `${tag}[name="${CSS.escape(name)}"]`;
                const aria = el.getAttribute("aria-label");
                if (aria) return `${tag}[aria-label="${CSS.escape(aria)}"]`;
                const all = Array.from(document.querySelectorAll(el.tagName));
                return `${tag}:nth-of-type(${all.indexOf(el) + 1})`;
              };
              const visible = (el) => !el.disabled && el.offsetParent !== null;
              const labelFor = (el) => {
                const id = el.id;
                if (id) {
                  const escaped = CSS.escape(id);
                  const label = document.querySelector(`label[for="${escaped}"]`);
                  if (label) return directTextOf(label) || textOf(label);
                }
                const wrapping = el.closest("label");
                if (wrapping) return directTextOf(wrapping) || textOf(wrapping);
                return el.getAttribute("aria-label")
                  || el.getAttribute("placeholder")
                  || el.getAttribute("name")
                  || el.id
                  || el.type
                  || el.tagName.toLowerCase();
              };
              const controls = Array.from(document.querySelectorAll(
                "input:not([type=hidden]), textarea, select"
              )).filter(visible);
              const fields = controls.map((el) => ({
                label: labelFor(el),
                selector: cssPath(el),
                field_type: el.type || el.tagName.toLowerCase(),
                required: Boolean(el.required),
                value: el.value || null
              }));
              const buttons = Array.from(document.querySelectorAll(
                "button, input[type=button], input[type=submit], [role=button]"
              )).filter(visible)
                .map((el) => (
                  textOf(el) || el.value || el.getAttribute("aria-label") || ""
                ))
                .filter(Boolean).slice(0, 30);
              const links = Array.from(document.querySelectorAll("a[href]"))
                .filter(visible)
                .map((el) => ({
                  text: textOf(el),
                  href: el.href,
                  selector: cssPath(el)
                }))
                .filter((item) => item.text || item.href)
                .slice(0, 30);
              const actions = [
                ...Array.from(document.querySelectorAll("a[href]"))
                  .filter(visible)
                  .map((el) => ({
                    role: "link",
                    text: textOf(el),
                    selector: cssPath(el),
                    href: el.href
                  })),
                ...Array.from(document.querySelectorAll(
                  "button, input[type=button], input[type=submit], [role=button]"
                ))
                  .filter(visible)
                  .map((el) => ({
                    role: "button",
                    text: textOf(el) || el.value || el.getAttribute("aria-label") || "",
                    selector: cssPath(el),
                    href: ""
                  }))
              ].filter((item) => item.text || item.href).slice(0, 60);
              return {
                url: location.href,
                title: document.title,
                fields,
                buttons,
                links,
                actions
              };
            }
            """)
        return PageSnapshot(
            url=data["url"],
            title=data["title"],
            fields=[PageField(**field) for field in data["fields"]],
            buttons=data["buttons"],
            links=data["links"],
            actions=data["actions"],
        )

    async def fill_form(
        self, session_id: str, values: Mapping[str, str]
    ) -> PageSnapshot:
        page = await self._page(session_id)
        snapshot = await self.snapshot(session_id)
        for key, value in values.items():
            field = _match_field(snapshot.fields, key)
            if field is None:
                continue
            locator = page.locator(field.selector).first
            field_type = field.field_type.lower()
            if field_type in {"checkbox", "radio"}:
                await locator.set_checked(
                    _truthy(value),
                    timeout=self.timeout_ms,
                )
            elif "select" in field_type:
                await locator.select_option(
                    label=value,
                    timeout=self.timeout_ms,
                )
            else:
                await locator.fill(
                    value,
                    timeout=self.timeout_ms,
                )
        return await self.snapshot(session_id)

    async def click_text(
        self,
        session_id: str,
        text: str | None = None,
        selector: str | None = None,
    ) -> PageSnapshot:
        page = await self._page(session_id)
        if selector:
            locator = page.locator(selector).first
        elif text:
            locator = page.get_by_text(text, exact=False).first
        else:
            raise ValueError("click_text requires text or selector")
        await locator.click(timeout=self.timeout_ms)
        return await self.snapshot(session_id)

    async def scroll(self, session_id: str, direction: str = "down") -> PageSnapshot:
        page = await self._page(session_id)
        delta = -700 if direction == "up" else 700
        await page.mouse.wheel(0, delta)
        return await self.snapshot(session_id)

    async def go_back(self, session_id: str) -> PageSnapshot:
        page = await self._page(session_id)
        await page.go_back(wait_until="domcontentloaded", timeout=self.timeout_ms)
        return await self.snapshot(session_id)

    async def _page(self, session_id: str) -> Page:
        await self.start()
        if self._browser is None:
            raise RuntimeError("Browser failed to start")
        if session_id not in self._pages:
            context = await self._browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(self.timeout_ms)
            self._contexts[session_id] = context
            self._pages[session_id] = page
        return self._pages[session_id]


def _match_field(fields: list[PageField], key: str) -> PageField | None:
    normalized = _normalize(key)
    for field in fields:
        candidates = [field.label, field.selector, field.field_type]
        if normalized in {_normalize(candidate) for candidate in candidates}:
            return field
    for field in fields:
        if normalized in _normalize(field.label):
            return field
    return None


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "checked"}
