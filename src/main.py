import argparse
import asyncio
import os

import uvicorn
from fastapi import FastAPI

from src.chatwoot.client import ChatwootClient
from src.chatwoot.webhook import create_webhook_router
from src.core.config import settings
from src.core.database import Database
from src.core.router import MessageRouter
from src.telegram.catchup import catchup_missed_messages
from src.telegram.client import build_client
from src.telegram.handlers import register_handlers


async def main(auth_only: bool = False) -> None:

    os.makedirs(os.path.dirname(settings.database_path) or ".", exist_ok=True)

    db = Database(settings.database_path)
    await db.connect()

    chatwoot = ChatwootClient(
        base_url=settings.chatwoot_base_url,
        api_token=settings.chatwoot_api_token,
        account_id=settings.chatwoot_account_id,
        inbox_id=settings.chatwoot_inbox_id,
    )

    tg = build_client(settings.tg_api_id, settings.tg_api_hash, settings.tg_session_path)

    if auth_only:
        await tg.start()
        print("Authentication successful. Session saved to", settings.tg_session_path)
        await tg.disconnect()
        await db.close()
        await chatwoot.close()
        return

    await tg.connect()
    if not await tg.is_user_authorized():
        raise RuntimeError("Not authorized. Run with --auth first to authenticate.")

    msg_router = MessageRouter(db=db, chatwoot=chatwoot, tg=tg)
    register_handlers(tg, msg_router)

    app = FastAPI()
    app.include_router(create_webhook_router(msg_router))

    uv_config = uvicorn.Config(
        app, host=settings.webhook_host, port=settings.webhook_port, log_level="info"
    )
    uv_server = uvicorn.Server(uv_config)

    async def _catchup_after_server_ready() -> None:
        while not uv_server.started:
            await asyncio.sleep(0.05)
        await catchup_missed_messages(tg, msg_router, db)

    try:
        await asyncio.gather(
            tg.run_until_disconnected(),
            uv_server.serve(),
            _catchup_after_server_ready(),
        )
    finally:
        await tg.disconnect()
        await db.close()
        await chatwoot.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram userbot → Chatwoot bridge")
    parser.add_argument("--auth", action="store_true", help="Authenticate and exit")
    args = parser.parse_args()
    asyncio.run(main(auth_only=args.auth))
