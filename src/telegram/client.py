import os

from telethon import TelegramClient


def build_client(api_id: int, api_hash: str, session_path: str) -> TelegramClient:
    os.makedirs(os.path.dirname(session_path) or ".", exist_ok=True)
    return TelegramClient(session_path, api_id, api_hash)
