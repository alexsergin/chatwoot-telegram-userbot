# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python service that acts as a regular Telegram user account (via MTProto, not a bot API) and bridges incoming private messages into Chatwoot. Agent replies from Chatwoot are sent back to the Telegram user. Supports text, photos, voice messages, video, audio, and files in both directions, plus typing indicators.

## Commands

```bash
# Create and activate virtualenv (required)
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e ".[dev]"

# First run — interactive Telegram auth (phone + code)
python -m src.main --auth

# Normal run
python -m src.main

# Tests
pytest tests/
pytest tests/test_router.py::test_handle_incoming_creates_mapping  # single test

# Lint / type-check
ruff check src/ tests/
mypy src/
```

## Architecture

Two concurrent loops share one asyncio event loop (via `asyncio.gather` in `main.py`):

1. **Telethon MTProto client** — listens for `NewMessage` and `UpdateUserTyping` events
2. **FastAPI + uvicorn** — receives `message_created`, `conversation_typing_on/off` webhooks from Chatwoot

Both paths converge on `core/router.py` (`MessageRouter`), which owns the business logic:

```
Telegram user DM / media
  → telegram/handlers.py (NewMessage → downloads media into MediaAttachment)
    → core/router.py (find_or_create contact/conversation, persist mapping)
      → chatwoot/client.py (REST API calls; multipart upload for attachments)
      → core/database.py (SQLite mapping store)

Chatwoot agent reply
  → chatwoot/webhook.py (POST /webhook/chatwoot; returns 200 immediately, processes in background)
    → core/router.py (look up telegram_chat_id, cancel typing indicator, send message/file)
      → chatwoot/client.py (download_attachment — follows Rails Active Storage 302 redirects)
      → telegram/client.py (send_message / send_file via Telethon)
```

### Webhook payload format

Chatwoot API inbox sends fields at **root level** (not nested under `"message"`). `message_type` arrives as integer `1` (outgoing) or string `"outgoing"` — both are handled via `_OUTGOING = {1, "outgoing"}`. Chatwoot does **not** sign channel webhook payloads, so no HMAC verification is performed.

The webhook handler returns `200 OK` immediately and dispatches work via `asyncio.create_task` to avoid Chatwoot marking messages as failed due to timeout.

### Media handling

- **Telegram → Chatwoot**: `msg.download_media(bytes)` downloads to memory; sent as multipart `attachments[]` to Chatwoot API.
- **Chatwoot → Telegram**: attachment `data_url` is downloaded via `httpx` with `follow_redirects=True` (Rails Active Storage returns 302). Filename is extracted from the URL path. Audio files (`file_type == "audio"`) are always sent as voice notes.

### ID Mapping

`core/database.py` maintains a single SQLite table:

```sql
CREATE TABLE mappings (
    telegram_chat_id          INTEGER PRIMARY KEY,
    chatwoot_contact_id       INTEGER NOT NULL,
    chatwoot_conversation_id  INTEGER NOT NULL
);
```

Telegram `user_id` is used as the Chatwoot contact `identifier`.

### Session

Telethon stores its session at `session/userbot.session` (SQLite file). In production, mount this file as a volume — the container must not lose it between restarts.

## Key Files

| File | Role |
|------|------|
| `src/main.py` | Entrypoint; wires Telethon + uvicorn via `asyncio.gather` |
| `src/core/router.py` | `MessageRouter` — all cross-system orchestration logic |
| `src/core/models.py` | `MediaAttachment` dataclass |
| `src/core/database.py` | `aiosqlite` wrapper; schema init and mapping CRUD |
| `src/core/config.py` | `pydantic-settings` model; single source of env config |
| `src/chatwoot/client.py` | Async Chatwoot REST API client; multipart upload; attachment download |
| `src/chatwoot/webhook.py` | FastAPI router; async task dispatch |
| `src/telegram/client.py` | Telethon session init |
| `src/telegram/handlers.py` | `NewMessage` + `UpdateUserTyping` event subscriptions |

## Environment Variables

Copy `.env.example` to `.env`:

```dotenv
TG_API_ID=
TG_API_HASH=
TG_SESSION_PATH=session/userbot.session

CHATWOOT_BASE_URL=https://your-chatwoot.example.com
CHATWOOT_API_TOKEN=
CHATWOOT_ACCOUNT_ID=
CHATWOOT_INBOX_ID=

WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000

DATABASE_PATH=data/mappings.db
```

## Testing Approach

Tests live in `tests/`. Each layer is isolated:

- **`test_chatwoot_client.py`** — mock `httpx.AsyncClient` via `respx`; verify request shape and multipart upload
- **`test_webhook.py`** — `httpx.AsyncClient` + FastAPI `ASGITransport`; uses `await asyncio.sleep(0)` to flush `create_task` before asserting
- **`test_router.py`** — double-mock (Chatwoot client + Telethon); verify mapping, media attachment, and typing call sequences
- **`test_database.py`** — in-memory SQLite (`:memory:`); no file I/O

`conftest.py` holds shared fixtures (in-memory DB). `asyncio_mode = "auto"` is set in `pyproject.toml`.
