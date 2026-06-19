import asyncio
import json

from fastapi import APIRouter, Request, Response

from src.core.router import MessageRouter

_OUTGOING = {1, "outgoing"}


def create_webhook_router(message_router: MessageRouter) -> APIRouter:
    api_router = APIRouter()

    @api_router.post("/webhook/chatwoot", response_model=None)
    async def chatwoot_webhook(request: Request) -> Response:
        payload: dict = await request.json()

        def _ok(status: str = "ok") -> Response:
            return Response(content=json.dumps({"status": status}), media_type="application/json")

        if "event" in payload:
            event = payload.get("event")
            conversation_id: int | None = payload.get("conversation", {}).get("id")

            if event == "conversation_typing_on":
                if conversation_id:
                    asyncio.create_task(message_router.handle_chatwoot_typing(conversation_id, True))
                return _ok()

            if event == "conversation_typing_off":
                if conversation_id:
                    asyncio.create_task(message_router.handle_chatwoot_typing(conversation_id, False))
                return _ok()

            if event != "message_created":
                return _ok("ignored")
            if payload.get("message_type") not in _OUTGOING or payload.get("private"):
                return _ok("ignored")

            content: str = payload.get("content") or ""
            attachments: list[dict] = payload.get("attachments") or []
        else:
            if payload.get("message_type") not in _OUTGOING:
                return _ok("ignored")
            content = payload.get("content") or ""
            conversation_id = payload.get("conversation", {}).get("id")
            attachments = payload.get("attachments") or []

        if conversation_id and (content or attachments):
            asyncio.create_task(
                message_router.handle_outgoing(conversation_id, content, attachments or None)
            )

        return _ok()

    return api_router
