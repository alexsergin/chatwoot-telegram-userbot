from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.database import Database
from src.telegram.catchup import catchup_missed_messages


def _make_user(user_id: int, first_name: str = "User", bot: bool = False) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.first_name = first_name
    user.last_name = None
    user.phone = None
    user.bot = bot
    return user


def _make_dialog(entity, is_user: bool = True) -> MagicMock:
    dialog = MagicMock()
    dialog.id = entity.id
    dialog.is_user = is_user
    dialog.entity = entity
    return dialog


def _make_message(msg_id: int, text: str, out: bool = False, media=None) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.out = out
    msg.media = media
    msg.voice = None
    msg.file = None
    return msg


async def _aiter(items):
    for item in items:
        yield item


@pytest.fixture
def mock_tg() -> MagicMock:
    # iter_dialogs / iter_messages are sync methods returning async iterators in Telethon,
    # so use MagicMock (not AsyncMock) to avoid wrapping their return values in coroutines.
    tg = MagicMock()
    tg.iter_dialogs.return_value = _aiter([])
    tg.iter_messages.return_value = _aiter([])
    return tg


@pytest.fixture
def mock_router() -> AsyncMock:
    return AsyncMock()


async def test_catchup_skips_group_dialogs(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    group = MagicMock()
    group.is_user = False
    mock_tg.iter_dialogs.return_value = _aiter([group])

    await catchup_missed_messages(mock_tg, mock_router, db)

    mock_router.handle_incoming.assert_not_awaited()


async def test_catchup_skips_bot_dialogs(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    bot = _make_user(1, bot=True)
    dialog = _make_dialog(bot)
    mock_tg.iter_dialogs.return_value = _aiter([dialog])

    await catchup_missed_messages(mock_tg, mock_router, db)

    mock_router.handle_incoming.assert_not_awaited()


async def test_catchup_skips_outgoing_messages(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    user = _make_user(42)
    dialog = _make_dialog(user)
    outgoing = _make_message(1, "sent by us", out=True)

    mock_tg.iter_dialogs.return_value = _aiter([dialog])
    mock_tg.iter_messages.return_value = _aiter([outgoing])

    await catchup_missed_messages(mock_tg, mock_router, db)

    mock_router.handle_incoming.assert_not_awaited()


async def test_catchup_forwards_missed_text_message(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    user = _make_user(42, "Alice")
    dialog = _make_dialog(user)
    msg = _make_message(101, "hello")

    mock_tg.iter_dialogs.return_value = _aiter([dialog])
    mock_tg.iter_messages.return_value = _aiter([msg])

    await catchup_missed_messages(mock_tg, mock_router, db)

    mock_router.handle_incoming.assert_awaited_once_with(
        user, 42, "hello", None, message_id=101
    )


async def test_catchup_uses_offset_id_for_known_dialog(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    await db.update_dialog_last_seen(42, 77)
    user = _make_user(42)
    dialog = _make_dialog(user)
    mock_tg.iter_dialogs.return_value = _aiter([dialog])
    mock_tg.iter_messages.return_value = _aiter([])

    await catchup_missed_messages(mock_tg, mock_router, db)

    mock_tg.iter_messages.assert_called_once_with(42, offset_id=77, reverse=True)


async def test_catchup_uses_offset_date_for_unknown_dialog(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    user = _make_user(99)
    dialog = _make_dialog(user)
    mock_tg.iter_dialogs.return_value = _aiter([dialog])
    mock_tg.iter_messages.return_value = _aiter([])

    await catchup_missed_messages(mock_tg, mock_router, db)

    call_kwargs = mock_tg.iter_messages.call_args.kwargs
    assert "offset_date" in call_kwargs
    assert call_kwargs.get("reverse") is True


async def test_catchup_skips_empty_messages(
    mock_tg: MagicMock, mock_router: AsyncMock, db: Database
) -> None:
    user = _make_user(42)
    dialog = _make_dialog(user)
    empty = _make_message(1, "")

    mock_tg.iter_dialogs.return_value = _aiter([dialog])
    mock_tg.iter_messages.return_value = _aiter([empty])

    await catchup_missed_messages(mock_tg, mock_router, db)

    mock_router.handle_incoming.assert_not_awaited()
