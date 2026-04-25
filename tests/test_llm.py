import json

import httpx
import pytest

from ui_bot.llm import OpenRouterFallbackClient, _parse_json


def test_parse_json_handles_fenced_output() -> None:
    assert _parse_json('```json\n{"action": "ask"}\n```') == {"action": "ask"}


def test_parse_json_handles_nested_output() -> None:
    assert _parse_json('Answer: {"action": "ask", "value": null}') == {
        "action": "ask",
        "value": None,
    }


@pytest.mark.asyncio
async def test_openrouter_falls_back_to_second_model() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = payload["model"]
        calls.append(model)
        if payload["messages"][0]["content"].startswith("Return JSON"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps({"ok": True})}},
                    ]
                },
            )
        if model == "first:free":
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"action": "ask"})}},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    client = OpenRouterFallbackClient(
        api_key="test-key",
        models=["first:free", "second:free"],
        base_url="https://openrouter.ai/api/v1",
        http_referer="http://localhost:8000",
        app_title="UI Bot",
        http=http,
    )

    response = await client.complete_json("system", "user")

    assert response == {"action": "ask"}
    assert "first:free" in calls
    assert calls[-1] == "second:free"
    await http.aclose()
