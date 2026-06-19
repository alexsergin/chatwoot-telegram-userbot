from src.core.database import Database


async def test_get_mapping_returns_none_when_missing(db: Database) -> None:
    assert await db.get_mapping(12345) is None


async def test_save_and_get_mapping(db: Database) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=1, chatwoot_conversation_id=2)
    assert await db.get_mapping(100) == (1, 2)


async def test_get_telegram_chat_id(db: Database) -> None:
    await db.save_mapping(telegram_chat_id=100, chatwoot_contact_id=1, chatwoot_conversation_id=2)
    assert await db.get_telegram_chat_id(2) == 100


async def test_get_telegram_chat_id_returns_none_when_missing(db: Database) -> None:
    assert await db.get_telegram_chat_id(999) is None


async def test_save_mapping_upsert(db: Database) -> None:
    await db.save_mapping(100, 1, 2)
    await db.save_mapping(100, 3, 4)
    assert await db.get_mapping(100) == (3, 4)


async def test_get_dialog_last_seen_returns_zero_when_missing(db: Database) -> None:
    assert await db.get_dialog_last_seen(12345) == 0


async def test_update_and_get_dialog_last_seen(db: Database) -> None:
    await db.update_dialog_last_seen(100, 42)
    assert await db.get_dialog_last_seen(100) == 42


async def test_update_dialog_last_seen_keeps_max(db: Database) -> None:
    await db.update_dialog_last_seen(100, 50)
    await db.update_dialog_last_seen(100, 30)  # older — should be ignored
    assert await db.get_dialog_last_seen(100) == 50


async def test_update_dialog_last_seen_advances(db: Database) -> None:
    await db.update_dialog_last_seen(100, 50)
    await db.update_dialog_last_seen(100, 75)  # newer — should advance
    assert await db.get_dialog_last_seen(100) == 75
