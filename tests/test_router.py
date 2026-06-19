from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.database import Database
from src.core.models import MediaAttachment
from src.core.router import MessageRouter


@pytest.fixture
def mock_chatwoot() -> AsyncMock:
    client = AsyncMock()
    client.find_or_create_contact.return_value = MagicMock(id=1)
    client.find_or_create_conversation.return_value = MagicMock(id=10)
    client.download_attachment.return_value = b"fake-image-data"
    return client


@pytest.fixture
def mock_tg() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def router(db: Database, mock_chatwoot: AsyncMock, mock_tg: AsyncMock) -> MessageRouter:
    return MessageRouter(db=db, chatwoot=mock_chatwoot, tg=mock_tg)


def _make_sender(user_id: int, first_name: str, last_name: str | None = None) -> MagicMock:
    sender = MagicMock()
    sender.id = user_id
    sender.first_name = first_name
    sender.last_name = last_name
    sender.phone = None
    return sender


async def test_handle_incoming_creates_mapping(
    router: MessageRouter, mock_chatwoot: AsyncMock, db: Database
) -> None:
    sender = _make_sender(999, "Alice")
    await router.handle_incoming(sender, chat_id=999, text="Hello")

    mock_chatwoot.find_or_create_contact.assert_awaited_once_with(999, "Alice", None)
    mock_chatwoot.find_or_create_conversation.assert_awaited_once_with(1)
    mock_chatwoot.create_message.assert_awaited_once_with(10, "Hello", None)
    assert await db.get_mapping(999) == (1, 10)


async def test_handle_incoming_with_attachment(
    router: MessageRouter, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=5, chatwoot_conversation_id=20)
    sender = _make_sender(100, "Bob")
    att = MediaAttachment(filename="photo.jpg", data=b"img", mime_type="image/jpeg")

    await router.handle_incoming(sender, chat_id=100, text="", attachment=att)

    mock_chatwoot.create_message.assert_awaited_once_with(20, "", ("photo.jpg", b"img", "image/jpeg"))


async def test_handle_incoming_uses_existing_mapping(
    router: MessageRouter, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=5, chatwoot_conversation_id=20)
    sender = _make_sender(100, "Bob")
    await router.handle_incoming(sender, chat_id=100, text="Hi again")

    mock_chatwoot.find_or_create_contact.assert_not_awaited()
    mock_chatwoot.create_message.assert_awaited_once_with(20, "Hi again", None)


async def test_handle_incoming_recreates_deleted_conversation(
    router: MessageRouter, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=5, chatwoot_conversation_id=20)
    sender = _make_sender(100, "Bob")

    err_response = MagicMock()
    err_response.status_code = 404
    mock_chatwoot.create_message.side_effect = [
        httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=err_response),
        None,
    ]
    mock_chatwoot.find_or_create_conversation.return_value = MagicMock(id=99)

    await router.handle_incoming(sender, chat_id=100, text="Hi after delete")

    mock_chatwoot.find_or_create_conversation.assert_awaited_once_with(5)
    assert mock_chatwoot.create_message.await_count == 2
    mock_chatwoot.create_message.assert_awaited_with(99, "Hi after delete", None)
    assert await db.get_mapping(100) == (5, 99)


async def test_handle_incoming_reraises_non_404_error(
    router: MessageRouter, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=5, chatwoot_conversation_id=20)
    sender = _make_sender(100, "Bob")

    err_response = MagicMock()
    err_response.status_code = 500
    mock_chatwoot.create_message.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error", request=MagicMock(), response=err_response
    )

    with pytest.raises(httpx.HTTPStatusError):
        await router.handle_incoming(sender, chat_id=100, text="Hi")

    mock_chatwoot.find_or_create_conversation.assert_not_awaited()


async def test_handle_incoming_full_name(
    router: MessageRouter, mock_chatwoot: AsyncMock
) -> None:
    sender = _make_sender(111, "John", "Doe")
    await router.handle_incoming(sender, chat_id=111, text="Hey")
    mock_chatwoot.find_or_create_contact.assert_awaited_once_with(111, "John Doe", None)


async def test_handle_outgoing_sends_message(
    router: MessageRouter, mock_tg: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=200, chatwoot_contact_id=3, chatwoot_conversation_id=30)
    await router.handle_outgoing(chatwoot_conversation_id=30, text="Reply from agent")
    mock_tg.send_message.assert_awaited_once_with(200, "Reply from agent")


async def test_handle_outgoing_with_image(
    router: MessageRouter, mock_tg: AsyncMock, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=200, chatwoot_contact_id=3, chatwoot_conversation_id=30)
    attachments = [{"data_url": "https://example.com/img.jpg", "file_type": "image", "extension": "jpg"}]

    await router.handle_outgoing(30, "look", attachments)

    mock_chatwoot.download_attachment.assert_awaited_once_with("https://example.com/img.jpg")
    mock_tg.send_file.assert_awaited_once()
    _, kwargs = mock_tg.send_file.call_args
    assert kwargs.get("caption") == "look"


async def test_handle_outgoing_with_voice_ogg(
    router: MessageRouter, mock_tg: AsyncMock, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=200, chatwoot_contact_id=3, chatwoot_conversation_id=30)
    attachments = [{"data_url": "https://example.com/voice.ogg", "file_type": "audio", "extension": "ogg"}]

    await router.handle_outgoing(30, "", attachments)

    _, kwargs = mock_tg.send_file.call_args
    assert kwargs.get("voice_note") is True


async def test_handle_outgoing_with_voice_mp3(
    router: MessageRouter, mock_tg: AsyncMock, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=200, chatwoot_contact_id=3, chatwoot_conversation_id=30)
    attachments = [{"data_url": "https://example.com/voice.mp3", "file_type": "audio", "extension": "mp3"}]

    await router.handle_outgoing(30, "", attachments)

    _, kwargs = mock_tg.send_file.call_args
    assert kwargs.get("voice_note") is True


async def test_handle_outgoing_ignores_unknown_conversation(
    router: MessageRouter, mock_tg: AsyncMock
) -> None:
    await router.handle_outgoing(chatwoot_conversation_id=999, text="Orphan")
    mock_tg.send_message.assert_not_awaited()


async def test_handle_chatwoot_typing_sends_action(
    router: MessageRouter, mock_tg: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=200, chatwoot_contact_id=3, chatwoot_conversation_id=30)
    await router.handle_chatwoot_typing(30, True)
    mock_tg.assert_awaited()


async def test_handle_chatwoot_typing_ignores_unknown(
    router: MessageRouter, mock_tg: AsyncMock
) -> None:
    await router.handle_chatwoot_typing(999, True)
    mock_tg.assert_not_awaited()


async def test_handle_telegram_typing(
    router: MessageRouter, mock_chatwoot: AsyncMock, db: Database
) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=1, chatwoot_conversation_id=10)
    await router.handle_telegram_typing(100, True)
    mock_chatwoot.set_contact_typing.assert_awaited_once_with(10, True)


async def test_handle_telegram_typing_ignores_unknown(
    router: MessageRouter, mock_chatwoot: AsyncMock
) -> None:
    await router.handle_telegram_typing(999, True)
    mock_chatwoot.set_contact_typing.assert_not_awaited()
