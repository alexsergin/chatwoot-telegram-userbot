import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass
class Contact:
    id: int
    name: str
    identifier: str


@dataclass
class Conversation:
    id: int
    contact_id: int


def _unwrap(data: dict) -> dict:
    return data["payload"] if "payload" in data and isinstance(data["payload"], dict) else data


class ChatwootClient:
    def __init__(self, base_url: str, api_token: str, account_id: int, inbox_id: int) -> None:
        self._inbox_id = inbox_id
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/api/v1/accounts/{account_id}/",
            headers={"api_access_token": api_token},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def find_or_create_contact(
        self, telegram_user_id: int, name: str, phone: str | None = None
    ) -> Contact:
        identifier = str(telegram_user_id)

        found = await self._search_contact(identifier)
        if found:
            return found

        create_payload: dict[str, str | int] = {"name": name, "identifier": identifier}
        if phone:
            create_payload["phone_number"] = phone if phone.startswith("+") else f"+{phone}"
        resp = await self._http.post("contacts", json=create_payload)

        if resp.status_code == 422:
            body = resp.json()
            attrs = body.get("attributes", [])

            # Phone number uniqueness conflict — retry without it; identifier is the real key.
            if "phone_number" in attrs and "phone_number" in create_payload:
                log.info(
                    "POST /contacts 422 on phone_number for identifier=%s, retrying without phone", identifier
                )
                del create_payload["phone_number"]
                resp = await self._http.post("contacts", json=create_payload)
                if resp.is_success:
                    data = _unwrap(resp.json())
                    contact_data = data.get("contact", data)
                    return Contact(id=contact_data["id"], name=contact_data.get("name", ""), identifier=identifier)

            # Identifier may still be reserved (soft-deleted contact).
            # Try the filter endpoint which can locate soft-deleted records.
            log.info("POST /contacts 422 for identifier=%s, trying filter fallback", identifier)
            found = await self._filter_contact(identifier)
            if found:
                return found
            log.error("POST /contacts 422 response body: %s", resp.text)
            resp.raise_for_status()

        resp.raise_for_status()
        data = _unwrap(resp.json())
        contact_data = data.get("contact", data)
        return Contact(id=contact_data["id"], name=contact_data.get("name", ""), identifier=identifier)

    async def _search_contact(self, identifier: str) -> Contact | None:
        resp = await self._http.get("contacts/search", params={"q": identifier, "include_contacts": True})
        resp.raise_for_status()
        payload = resp.json().get("payload", [])
        contacts = payload if isinstance(payload, list) else payload.get("contacts", [])
        for c in contacts:
            if c.get("identifier") == identifier:
                return Contact(id=c["id"], name=c["name"], identifier=identifier)
        return None

    async def _filter_contact(self, identifier: str) -> Contact | None:
        resp = await self._http.post(
            "contacts/filter",
            json={"payload": [{"attribute_key": "identifier", "filter_operator": "equal_to",
                               "values": [identifier], "query_operator": None}]},
        )
        if not resp.is_success:
            return None
        for c in resp.json().get("payload", []):
            if c.get("identifier") == identifier:
                return Contact(id=c["id"], name=c["name"], identifier=identifier)
        return None

    async def find_or_create_conversation(self, contact_id: int) -> Conversation:
        resp = await self._http.get(f"contacts/{contact_id}/conversations")
        resp.raise_for_status()
        for c in resp.json().get("payload", []):
            if c.get("inbox_id") == self._inbox_id and c.get("status") == "open":
                return Conversation(id=c["id"], contact_id=contact_id)

        resp = await self._http.post(
            "conversations",
            json={"contact_id": contact_id, "inbox_id": self._inbox_id},
        )
        resp.raise_for_status()
        data = _unwrap(resp.json())
        return Conversation(id=data["id"], contact_id=contact_id)

    async def create_message(
        self,
        conversation_id: int,
        content: str,
        attachment: tuple[str, bytes, str] | None = None,
    ) -> None:
        if attachment:
            filename, data, mime_type = attachment
            resp = await self._http.post(
                f"conversations/{conversation_id}/messages",
                data={"content": content, "message_type": "incoming", "private": "false"},
                files={"attachments[]": (filename, data, mime_type)},
            )
        else:
            resp = await self._http.post(
                f"conversations/{conversation_id}/messages",
                json={"content": content, "message_type": "incoming", "private": False},
            )
        resp.raise_for_status()

    async def download_attachment(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def set_contact_typing(self, conversation_id: int, is_typing: bool) -> None:
        await self._http.post(
            f"conversations/{conversation_id}/typing_status",
            json={"typing_status": "on" if is_typing else "off"},
        )
