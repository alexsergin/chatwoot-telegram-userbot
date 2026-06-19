import httpx
import pytest
import respx

from src.chatwoot.client import ChatwootClient

BASE_URL = "https://chatwoot.example.com"
ACCOUNT_ID = 1
INBOX_ID = 10
API_PREFIX = f"{BASE_URL}/api/v1/accounts/{ACCOUNT_ID}"


@pytest.fixture
def client() -> ChatwootClient:
    return ChatwootClient(BASE_URL, "test-token", ACCOUNT_ID, INBOX_ID)


@respx.mock
async def test_find_or_create_contact_creates_new(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(200, json={"payload": []})
    )
    respx.post(f"{API_PREFIX}/contacts").mock(
        return_value=httpx.Response(200, json={"payload": {"id": 42, "name": "Alice", "identifier": "111"}})
    )

    contact = await client.find_or_create_contact(111, "Alice")
    assert contact.id == 42
    assert contact.name == "Alice"
    assert contact.identifier == "111"


@respx.mock
async def test_find_or_create_contact_finds_existing(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(
            200,
            json={"payload": [{"id": 7, "name": "Bob", "identifier": "222"}]},
        )
    )

    contact = await client.find_or_create_contact(222, "Bob")
    assert contact.id == 7
    assert contact.name == "Bob"


@respx.mock
async def test_find_or_create_conversation_creates_new(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/3/conversations").mock(
        return_value=httpx.Response(200, json={"payload": []})
    )
    respx.post(f"{API_PREFIX}/conversations").mock(
        return_value=httpx.Response(200, json={"payload": {"id": 11, "contact_id": 3}})
    )

    conv = await client.find_or_create_conversation(3)
    assert conv.id == 11
    assert conv.contact_id == 3


@respx.mock
async def test_find_or_create_conversation_finds_open(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/3/conversations").mock(
        return_value=httpx.Response(
            200,
            json={"payload": [{"id": 5, "inbox_id": INBOX_ID, "status": "open", "contact_id": 3}]},
        )
    )

    conv = await client.find_or_create_conversation(3)
    assert conv.id == 5


@respx.mock
async def test_create_message(client: ChatwootClient) -> None:
    respx.post(f"{API_PREFIX}/conversations/5/messages").mock(
        return_value=httpx.Response(200, json={"id": 99})
    )

    await client.create_message(5, "Hello!")
