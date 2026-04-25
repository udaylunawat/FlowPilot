import json
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ui_bot.config import Settings


class LLMUnavailable(RuntimeError):
    pass


OPENROUTER_FREE_MODELS = [
    "google/gemma-4-31b-it:free",
    "arcee-ai/trinity-large-preview:free",
    "google/gemma-4-26b-a4b-it:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-3-4b-it:free",
]

OPENROUTER_MAX_RETRIES_PER_MODEL = 2
OPENROUTER_PROBE_TTL_SECONDS = 3600
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.I | re.S)


class LLMClient(ABC):
    @abstractmethod
    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        raise NotImplementedError


class OpenAICompatibleClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        headers = {"authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_json(content)


class OpenRouterFallbackClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        models: list[str],
        base_url: str,
        http_referer: str,
        app_title: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.models = models or OPENROUTER_FREE_MODELS
        self.base_url = base_url.rstrip("/")
        self.http_referer = http_referer
        self.app_title = app_title
        self._http = http or httpx.AsyncClient(timeout=30)
        self._own_http = http is None
        self._healthy_models: list[str] = []
        self._healthy_at = 0.0

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        healthy = await self._ensure_healthy(limit=3)
        models_to_try = healthy + [
            model for model in self.models if model not in healthy
        ]
        last_error = "no models configured"
        for model in models_to_try:
            raw = await self._call_json_model(model, messages)
            if raw is None:
                last_error = f"{model} returned no content"
                continue
            parsed = _extract_json(raw)
            if isinstance(parsed, dict):
                return parsed
            last_error = f"{model} returned non-JSON"
        raise LLMUnavailable(f"OpenRouter fallback exhausted: {last_error}")

    async def close(self) -> None:
        if self._own_http:
            await self._http.aclose()

    async def _ensure_healthy(self, limit: int | None = None) -> list[str]:
        now = time.monotonic()
        cache_age = now - self._healthy_at
        if self._healthy_models and cache_age < OPENROUTER_PROBE_TTL_SECONDS:
            return self._healthy_models

        candidates = self.models[:limit] if limit else self.models
        healthy: list[str] = []
        for model in candidates:
            if await self._probe(model):
                healthy.append(model)
        self._healthy_models = healthy
        self._healthy_at = now
        return healthy

    async def _probe(self, model: str) -> bool:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": 'Return JSON: {"ok": true}'}],
            "max_tokens": 20,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self._http.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        content = _extract_response_content(response.json()) or ""
        return _extract_json(content) is not None

    async def _call_json_model(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> str | None:
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        raw = await self._post_with_retries(model, payload)
        if raw is not None:
            return raw

        fallback_payload = dict(payload)
        fallback_payload.pop("response_format", None)
        fallback_payload["messages"] = [
            *messages,
            {"role": "system", "content": "Return only valid JSON."},
        ]
        return await self._post_with_retries(model, fallback_payload)

    async def _post_with_retries(
        self,
        model: str,
        payload: dict[str, Any],
    ) -> str | None:
        for attempt in range(OPENROUTER_MAX_RETRIES_PER_MODEL + 1):
            try:
                response = await self._http.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                    timeout=30,
                )
                response.raise_for_status()
                return _extract_response_content(response.json())
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    await _sleep_for_rate_limit(exc, attempt)
                    continue
                if exc.response.status_code in {401, 403}:
                    return None
                return None
            except httpx.HTTPError:
                return None
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.api_key}",
            "http-referer": self.http_referer,
            "x-title": self.app_title,
        }


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        prompt = f"{system}\n\n{user}\n\nReturn only valid JSON."
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_json(text)


def build_llm(settings: Settings) -> LLMClient | None:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAICompatibleClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
    if settings.llm_provider == "openrouter" and settings.openrouter_api_key:
        return OpenRouterFallbackClient(
            api_key=settings.openrouter_api_key,
            models=settings.openrouter_model_list,
            base_url=settings.openrouter_base_url,
            http_referer=settings.openrouter_http_referer,
            app_title=settings.openrouter_app_title,
        )
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )
    return None


def _parse_json(content: str) -> dict[str, Any]:
    data = _extract_json(content)
    if data is None:
        raise LLMUnavailable("LLM returned non-JSON content")
    if not isinstance(data, dict):
        raise LLMUnavailable("LLM returned JSON that is not an object")
    return data


def _extract_response_content(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = _coerce_content_text(message.get("content"))
                if content:
                    return content
            content = _coerce_content_text(first.get("text"))
            if content:
                return content
    for key in ("content", "text", "output_text", "response"):
        content = _coerce_content_text(payload.get(key))
        if content:
            return content
    return None


def _coerce_content_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        joined = "".join(parts).strip()
        return joined or None
    if isinstance(value, dict):
        for key in ("text", "content", "output_text"):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    candidates = [block.strip() for block in _FENCED_JSON_RE.findall(text)]
    candidates.append(text)
    for candidate in candidates:
        parsed = _try_json_loads(candidate)
        if parsed is not None:
            return parsed
        repaired = _TRAILING_COMMA_RE.sub(r"\1", candidate)
        parsed = _try_json_loads(repaired)
        if parsed is not None:
            return parsed
        for nested in _extract_json_objects(repaired):
            parsed = _try_json_loads(nested)
            if parsed is not None:
                return parsed
    return None


def _try_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_json_objects(text: str) -> list[str]:
    stack = 0
    start_idx = None
    in_string = False
    escape = False
    candidates: list[str] = []

    for index, character in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if character == "\\":
                escape = True
                continue
            if character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
            continue
        if character == "{":
            if stack == 0:
                start_idx = index
            stack += 1
            continue
        if character == "}" and stack > 0:
            stack -= 1
            if stack == 0 and start_idx is not None:
                candidates.append(text[start_idx : index + 1])
    return list(reversed(candidates))


async def _sleep_for_rate_limit(exc: httpx.HTTPStatusError, attempt: int) -> None:
    retry_after = exc.response.headers.get("retry-after")
    if retry_after:
        sleep_seconds = float(retry_after)
    else:
        sleep_seconds = min(2 ** (attempt + 1), 30) + random.uniform(0.1, 1.0)
    await asyncio_sleep(sleep_seconds)


async def asyncio_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
