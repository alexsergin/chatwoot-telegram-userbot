from telethon import TelegramClient, events
from telethon.tl.types import SendMessageTypingAction, UpdateUserTyping, User

from src.core.models import MediaAttachment
from src.core.router import MessageRouter


def _filename(msg) -> str:
    name = getattr(msg.file, "name", None)
    if name:
        return name
    if msg.photo:
        return "photo.jpg"
    if msg.voice:
        return "voice.ogg"
    if msg.video_note:
        return "video_note.mp4"
    if msg.video:
        return "video.mp4"
    if msg.audio:
        return "audio.mp3"
    return "file"


def register_handlers(client: TelegramClient, router: MessageRouter) -> None:
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def on_message(event: events.NewMessage.Event) -> None:
        sender = await event.get_sender()
        if not isinstance(sender, User) or sender.bot or sender.id == 777000:
            return

        msg = event.message
        text: str = msg.text or ""

        attachment: MediaAttachment | None = None
        if msg.media:
            raw: bytes | None = await msg.download_media(bytes)
            if raw:
                attachment = MediaAttachment(
                    filename=_filename(msg),
                    data=raw,
                    mime_type=getattr(msg.file, "mime_type", None) or "application/octet-stream",
                    is_voice=bool(msg.voice),
                )

        if not text and not attachment:
            return

        await router.handle_incoming(sender, event.chat_id, text, attachment, message_id=msg.id)

    @client.on(events.Raw(UpdateUserTyping))
    async def on_typing(event: UpdateUserTyping) -> None:
        is_typing = isinstance(event.action, SendMessageTypingAction)
        await router.handle_telegram_typing(event.user_id, is_typing)
