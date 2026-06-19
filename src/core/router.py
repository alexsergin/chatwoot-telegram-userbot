import io
import logging
from urllib.parse import urlparse

from telethon import TelegramClient
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageCancelAction, SendMessageTypingAction, User

from src.chatwoot.client import ChatwootClient
from src.core.database import Database
from src.core.models import MediaAttachment

log = logging.getLogger(__name__)

_FALLBACK_NAMES = {"image": "photo.jpg", "audio": "audio.mp3", "video": "video.mp4"}


def _filename_from_attachment(attachment: dict) -> str:
    url = attachment.get("data_url", "")
    if url:
        basename = urlparse(url).path.split("/")[-1]
        if "." in basename:
            return basename
    extension = (attachment.get("extension") or "").lower()
    file_type = attachment.get("file_type", "file")
    return f"file.{extension}" if extension else _FALLBACK_NAMES.get(file_type, "file")


class MessageRouter:
    def __init__(self, db: Database, chatwoot: ChatwootClient, tg: TelegramClient) -> None:
        self._db = db
        self._chatwoot = chatwoot
        self._tg = tg

    async def handle_incoming(
        self,
        sender: User,
        chat_id: int,
        text: str,
        attachment: MediaAttachment | None = None,
    ) -> None:
        mapping = await self._db.get_mapping(chat_id)
        if mapping:
            _, conversation_id = mapping
        else:
            name = " ".join(filter(None, [sender.first_name, sender.last_name])) or "Unknown"
            phone: str | None = getattr(sender, "phone", None)
            contact = await self._chatwoot.find_or_create_contact(sender.id, name, phone)
            conversation = await self._chatwoot.find_or_create_conversation(contact.id)
            await self._db.save_mapping(chat_id, contact.id, conversation.id)
            conversation_id = conversation.id

        chatwoot_att = (attachment.filename, attachment.data, attachment.mime_type) if attachment else None
        await self._chatwoot.create_message(conversation_id, text, chatwoot_att)

    async def handle_outgoing(
        self,
        chatwoot_conversation_id: int,
        text: str,
        attachments: list[dict] | None = None,
    ) -> None:
        telegram_chat_id = await self._db.get_telegram_chat_id(chatwoot_conversation_id)
        if telegram_chat_id is None:
            log.warning("no mapping for chatwoot conversation_id=%s", chatwoot_conversation_id)
            return
        try:
            await self._tg(SetTypingRequest(peer=telegram_chat_id, action=SendMessageCancelAction()))
        except Exception:
            pass

        if attachments:
            caption = text
            for att in attachments:
                await self._send_attachment(telegram_chat_id, att, caption)
                caption = ""
        else:
            await self._tg.send_message(telegram_chat_id, text)

    async def _send_attachment(self, chat_id: int, attachment: dict, caption: str = "") -> None:
        url = attachment.get("data_url", "")
        if not url:
            return
        file_type = attachment.get("file_type", "file")
        extension = (attachment.get("extension") or "").lower()

        data = io.BytesIO(await self._chatwoot.download_attachment(url))
        data.name = _filename_from_attachment(attachment)

        kwargs: dict = {"caption": caption or None}
        if file_type == "image":
            pass
        elif file_type == "audio":
            kwargs["voice_note"] = True
        elif file_type == "video":
            pass
        else:
            kwargs["force_document"] = True

        await self._tg.send_file(chat_id, data, **kwargs)

    async def handle_chatwoot_typing(self, conversation_id: int, is_typing: bool) -> None:
        telegram_chat_id = await self._db.get_telegram_chat_id(conversation_id)
        if telegram_chat_id is None:
            return
        action = SendMessageTypingAction() if is_typing else SendMessageCancelAction()
        try:
            await self._tg(SetTypingRequest(peer=telegram_chat_id, action=action))
        except Exception:
            pass

    async def handle_telegram_typing(self, user_id: int, is_typing: bool) -> None:
        mapping = await self._db.get_mapping(user_id)
        if mapping is None:
            return
        _, conversation_id = mapping
        await self._chatwoot.set_contact_typing(conversation_id, is_typing)
