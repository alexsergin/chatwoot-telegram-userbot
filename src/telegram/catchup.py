import logging
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient

from src.core.database import Database
from src.core.models import MediaAttachment
from src.core.router import MessageRouter
from src.telegram.handlers import _filename

log = logging.getLogger(__name__)

# Fallback window for dialogs with no recorded last_seen_message_id.
_CATCHUP_FALLBACK_HOURS = 48


async def catchup_missed_messages(
    tg: TelegramClient,
    router: MessageRouter,
    db: Database,
) -> None:
    fallback_cutoff = datetime.now(timezone.utc) - timedelta(hours=_CATCHUP_FALLBACK_HOURS)
    total = 0

    async for dialog in tg.iter_dialogs():
        if not dialog.is_user:
            continue
        entity = dialog.entity
        # 777000 is Telegram's system notifications account; not a bot flag but not a real user.
        if getattr(entity, "bot", False) or getattr(entity, "id", None) == 777000:
            continue

        last_seen_id = await db.get_dialog_last_seen(dialog.id)

        if last_seen_id:
            # Known dialog: fetch messages with ID strictly greater than last_seen_id.
            # offset_id with reverse=True acts as a lower bound, so messages with
            # ID > last_seen_id are returned oldest-first.
            iterator = tg.iter_messages(dialog.id, offset_id=last_seen_id, reverse=True)
        else:
            # Unknown dialog: fall back to a time-based window to avoid replaying
            # the entire history.
            iterator = tg.iter_messages(dialog.id, offset_date=fallback_cutoff, reverse=True)

        async for msg in iterator:
            if msg.out:
                continue

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
                continue

            log.info("catch-up: msg id=%s from user_id=%s at %s", msg.id, entity.id, msg.date)
            try:
                await router.handle_incoming(entity, dialog.id, text, attachment, message_id=msg.id)
                total += 1
            except Exception:
                log.exception("catch-up: failed to forward msg id=%s from user_id=%s", msg.id, entity.id)

    log.info("catch-up: forwarded %d missed message(s) to Chatwoot", total)
