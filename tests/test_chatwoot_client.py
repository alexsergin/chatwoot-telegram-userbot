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
async def test_find_or_create_contact_sends_username_and_phone(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(200, json={"payload": []})
    )
    create_route = respx.post(f"{API_PREFIX}/contacts").mock(
        return_value=httpx.Response(200, json={"payload": {"id": 42, "name": "Alice", "identifier": "111"}})
    )

    await client.find_or_create_contact(111, "Alice", phone="+79001234567", username="alice_tg")

    import json
    body = json.loads(create_route.calls[0].request.content)
    assert body["phone_number"] == "+79001234567"
    assert body["additional_attributes"]["social_profiles"]["telegram"] == "alice_tg"


@respx.mock
async def test_find_or_create_contact_finds_existing(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(
            200,
            json={"payload": [{"id": 7, "name": "Bob", "identifier": "222"}]},
        )
    )
    respx.patch(f"{API_PREFIX}/contacts/7").mock(return_value=httpx.Response(200, json={}))

    contact = await client.find_or_create_contact(222, "Bob")
    assert contact.id == 7
    assert contact.name == "Bob"


@respx.mock
async def test_find_or_create_contact_patches_existing_with_phone_and_username(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(
            200,
            json={"payload": [{"id": 7, "name": "Bob", "identifier": "222"}]},
        )
    )
    patch_route = respx.patch(f"{API_PREFIX}/contacts/7").mock(return_value=httpx.Response(200, json={}))

    await client.find_or_create_contact(222, "Bob", phone="+79001234567", username="bob_tg")

    import json
    patch_body = json.loads(patch_route.calls[0].request.content)
    assert patch_body["phone_number"] == "+79001234567"
    assert patch_body["additional_attributes"]["social_profiles"]["telegram"] == "bob_tg"


@respx.mock
async def test_find_or_create_contact_patches_after_phone_422_retry(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(return_value=httpx.Response(200, json={"payload": []}))
    respx.post(f"{API_PREFIX}/contacts").mock(
        side_effect=[
            httpx.Response(422, json={"message": "Phone number has already been taken", "attributes": ["phone_number"]}),
            httpx.Response(200, json={"payload": {"id": 42, "name": "Alice", "identifier": "111"}}),
        ]
    )
    patch_route = respx.patch(f"{API_PREFIX}/contacts/42").mock(return_value=httpx.Response(200, json={}))

    await client.find_or_create_contact(111, "Alice", phone="+79001234567")

    import json
    patch_body = json.loads(patch_route.calls[0].request.content)
    assert patch_body["phone_number"] == "+79001234567"


@respx.mock
async def test_find_or_create_contact_retries_without_phone_on_phone_conflict(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(200, json={"payload": []})
    )
    respx.post(f"{API_PREFIX}/contacts").mock(
        side_effect=[
            httpx.Response(422, json={"message": "Phone number has already been taken", "attributes": ["phone_number"]}),
            httpx.Response(200, json={"payload": {"id": 42, "name": "Alice", "identifier": "111"}}),
        ]
    )

    respx.patch(f"{API_PREFIX}/contacts/42").mock(return_value=httpx.Response(200, json={}))

    contact = await client.find_or_create_contact(111, "Alice", phone="+79001234567")
    assert contact.id == 42
    # second POST (retry) must not include phone_number
    import json
    post_calls = [c for c in respx.calls if c.request.method == "POST" and "/contacts" in str(c.request.url) and "/filter" not in str(c.request.url)]
    retry_body = json.loads(post_calls[-1].request.content)
    assert "phone_number" not in retry_body


@respx.mock
async def test_find_or_create_contact_recovers_soft_deleted_via_filter(client: ChatwootClient) -> None:
    respx.get(f"{API_PREFIX}/contacts/search").mock(
        return_value=httpx.Response(200, json={"payload": []})
    )
    respx.post(f"{API_PREFIX}/contacts").mock(
        return_value=httpx.Response(422, json={"message": "Identifier has already been taken", "attributes": ["identifier"]})
    )
    respx.post(f"{API_PREFIX}/contacts/filter").mock(
        return_value=httpx.Response(200, json={"payload": [{"id": 55, "name": "Alice", "identifier": "111"}]})
    )

    contact = await client.find_or_create_contact(111, "Alice")
    assert contact.id == 55
    assert contact.identifier == "111"


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
