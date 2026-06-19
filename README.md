# Telegram Userbot → Chatwoot

Bridges Telegram private messages into [Chatwoot](https://www.chatwoot.com/) using a real user account (MTProto via Telethon, not the Bot API). Agent replies in Chatwoot are sent back to the Telegram user automatically.

## Features

- Text messages in both directions
- Media in both directions: photos, voice messages, video, audio, files
- Typing indicators in both directions
- Agent replies delivered asynchronously (Chatwoot does not wait for Telegram delivery)

## How it works

```
Telegram user DM  →  Telethon (MTProto)  →  Chatwoot conversation
Chatwoot agent reply  →  webhook  →  Telethon  →  Telegram user
```

The service runs two loops concurrently in one asyncio event loop:
- **Telethon client** — listens for incoming private messages and typing events
- **FastAPI server** — receives `message_created` and typing webhooks from Chatwoot

## Requirements

- Python 3.11+
- A Telegram account (not a bot) with API credentials from [my.telegram.org](https://my.telegram.org/apps)
- A running Chatwoot instance with an API inbox

## Setup

**1. Install dependencies**

```bash
make install
```

**2. Configure environment**

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Where to get it |
|----------|----------------|
| `TG_API_ID` / `TG_API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `CHATWOOT_BASE_URL` | Your Chatwoot instance URL |
| `CHATWOOT_API_TOKEN` | Chatwoot → Profile Settings → Access Token |
| `CHATWOOT_ACCOUNT_ID` | Number in the URL: `/app/accounts/<id>/` |
| `CHATWOOT_INBOX_ID` | Chatwoot → Settings → Inboxes → your API inbox |

**3. Authenticate Telegram session (once)**

```bash
make auth
```

This prompts for your phone number and the confirmation code. The session is saved to `session/userbot.session`.

**4. Configure Chatwoot API inbox**

In Chatwoot go to **Settings → Inboxes → Add Inbox → API** and fill in:

- **Channel Name** — any name, e.g. `Telegram`
- **Webhook URL** — `http://<your-host>:8000/webhook/chatwoot`

Copy the **Inbox ID** from the inbox list (shown in the URL or inbox settings) and set it as `CHATWOOT_INBOX_ID` in `.env`.

**5. Run**

```bash
make run
```

## Development

```bash
make test        # run all tests
make lint        # ruff
make typecheck   # mypy
```

Run a single test:

```bash
.venv/bin/pytest tests/test_router.py::test_handle_incoming_creates_mapping
```

## Docker

**1. Build the image**

```bash
docker build -t chatwoot-telegram-userbot .
```

**2. Authenticate (one-time, interactive)**

```bash
docker run --rm -it \
  --env-file .env \
  -v $(pwd)/session:/app/session \
  chatwoot-telegram-userbot python -m src.main --auth
```

**3. Run**

```bash
docker run -d \
  --name chatwoot-telegram-userbot \
  --env-file .env \
  -p 8000:8000 \
  -v $(pwd)/session:/app/session \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  chatwoot-telegram-userbot
```

**Re-authenticate** (if the session expires):

```bash
docker run --rm -it \
  --env-file .env \
  -v $(pwd)/session:/app/session \
  chatwoot-telegram-userbot python -m src.main --auth
```
