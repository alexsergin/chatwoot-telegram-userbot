import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.chatwoot.webhook import create_webhook_router
from src.core.router import MessageRouter


@pytest.fixture
def mock_router() -> AsyncMock:
    return AsyncMock(spec=MessageRouter)


@pytest.fixture
async def client(mock_router: AsyncMock) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(create_webhook_router(mock_router))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _post(client: httpx.AsyncClient, payload: dict):
    return client.post(
        "/webhook/chatwoot",
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )


async def _flush() -> None:
    """Let pending create_task coroutines run."""
    await asyncio.sleep(0)


# --- API inbox format (no "event" key) ---

async def test_api_inbox_handles_outgoing_string(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {
        "content": "Hi from agent",
        "message_type": "outgoing",
        "conversation": {"id": 42},
        "contact": {"id": 1},
    })
    assert resp.status_code == 200
    await _flush()
    mock_router.handle_outgoing.assert_awaited_once_with(42, "Hi from agent", None)


async def test_api_inbox_handles_outgoing_int(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {
        "content": "Hi from agent",
        "message_type": 1,
        "conversation": {"id": 42},
        "contact": {"id": 1},
    })
    assert resp.status_code == 200
    await _flush()
    mock_router.handle_outgoing.assert_awaited_once_with(42, "Hi from agent", None)


async def test_api_inbox_ignores_incoming(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {
        "content": "Hi",
        "message_type": "incoming",
        "conversation": {"id": 1},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_router.handle_outgoing.assert_not_awaited()


# --- Global webhook format (has "event" key) ---

async def test_global_webhook_handles_outgoing(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {
        "event": "message_created",
        "message_type": "outgoing",
        "private": False,
        "content": "Hi there",
        "conversation": {"id": 42},
    })
    assert resp.status_code == 200
    await _flush()
    mock_router.handle_outgoing.assert_awaited_once_with(42, "Hi there", None)


async def test_global_webhook_handles_outgoing_with_attachment(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    att = [{"data_url": "https://example.com/img.jpg", "file_type": "image", "extension": "jpg"}]
    resp = await _post(client, {
        "event": "message_created",
        "message_type": "outgoing",
        "private": False,
        "content": "",
        "attachments": att,
        "conversation": {"id": 42},
    })
    assert resp.status_code == 200
    await _flush()
    mock_router.handle_outgoing.assert_awaited_once_with(42, "", att)


async def test_global_webhook_typing_on(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {"event": "conversation_typing_on", "conversation": {"id": 7}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    await _flush()
    mock_router.handle_chatwoot_typing.assert_awaited_once_with(7, True)


async def test_global_webhook_typing_off(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {"event": "conversation_typing_off", "conversation": {"id": 7}})
    assert resp.status_code == 200
    await _flush()
    mock_router.handle_chatwoot_typing.assert_awaited_once_with(7, False)


async def test_global_webhook_ignores_unknown_event(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {"event": "conversation_created"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_router.handle_outgoing.assert_not_awaited()


async def test_global_webhook_ignores_private_message(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {
        "event": "message_created",
        "message_type": "outgoing",
        "private": True,
        "content": "Internal note",
        "conversation": {"id": 1},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_router.handle_outgoing.assert_not_awaited()


async def test_global_webhook_ignores_incoming_message(client: httpx.AsyncClient, mock_router: AsyncMock) -> None:
    resp = await _post(client, {
        "event": "message_created",
        "message_type": "incoming",
        "private": False,
        "content": "Hello",
        "conversation": {"id": 1},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
