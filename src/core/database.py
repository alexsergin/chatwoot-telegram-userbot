import aiosqlite

_CREATE_MAPPINGS = """
CREATE TABLE IF NOT EXISTS mappings (
    telegram_chat_id          INTEGER PRIMARY KEY,
    chatwoot_contact_id       INTEGER NOT NULL,
    chatwoot_conversation_id  INTEGER NOT NULL
)
"""

_CREATE_DIALOG_STATE = """
CREATE TABLE IF NOT EXISTS dialog_state (
    telegram_chat_id     INTEGER PRIMARY KEY,
    last_seen_message_id INTEGER NOT NULL
)
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute(_CREATE_MAPPINGS)
        await self._conn.execute(_CREATE_DIALOG_STATE)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    async def get_mapping(self, telegram_chat_id: int) -> tuple[int, int] | None:
        async with self.conn.execute(
            "SELECT chatwoot_contact_id, chatwoot_conversation_id "
            "FROM mappings WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else None

    async def save_mapping(
        self,
        telegram_chat_id: int,
        chatwoot_contact_id: int,
        chatwoot_conversation_id: int,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO mappings (telegram_chat_id, chatwoot_contact_id, chatwoot_conversation_id)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_chat_id) DO UPDATE SET
                chatwoot_contact_id = excluded.chatwoot_contact_id,
                chatwoot_conversation_id = excluded.chatwoot_conversation_id
            """,
            (telegram_chat_id, chatwoot_contact_id, chatwoot_conversation_id),
        )
        await self.conn.commit()

    async def delete_mapping(self, telegram_chat_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM mappings WHERE telegram_chat_id = ?", (telegram_chat_id,)
        )
        await self.conn.commit()

    async def get_telegram_chat_id(self, chatwoot_conversation_id: int) -> int | None:
        async with self.conn.execute(
            "SELECT telegram_chat_id FROM mappings WHERE chatwoot_conversation_id = ?",
            (chatwoot_conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_dialog_last_seen(self, telegram_chat_id: int) -> int:
        async with self.conn.execute(
            "SELECT last_seen_message_id FROM dialog_state WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def update_dialog_last_seen(self, telegram_chat_id: int, message_id: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO dialog_state (telegram_chat_id, last_seen_message_id) VALUES (?, ?)
            ON CONFLICT(telegram_chat_id) DO UPDATE SET
                last_seen_message_id = MAX(excluded.last_seen_message_id, last_seen_message_id)
            """,
            (telegram_chat_id, message_id),
        )
        await self.conn.commit()
