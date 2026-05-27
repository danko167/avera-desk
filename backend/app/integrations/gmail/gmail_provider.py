"""Gmail API provider for inbox sync and sending."""

from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import logging
from typing import Any
from urllib.parse import quote
import base64

import httpx

from . import oauth

logger = logging.getLogger(__name__)


def _parse_json_payload(
    response: httpx.Response,
    *,
    operation: str,
    expected_types: tuple[type, ...],
    fallback: Any,
) -> Any:
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning(
            "gmail_json_decode_failed operation=%s status_code=%s error=%s",
            operation,
            response.status_code,
            exc,
        )
        return fallback

    if not isinstance(payload, expected_types):
        expected = "/".join(value_type.__name__ for value_type in expected_types)
        logger.warning(
            "gmail_json_type_mismatch operation=%s status_code=%s expected=%s actual=%s",
            operation,
            response.status_code,
            expected,
            type(payload).__name__,
        )
        return fallback

    return payload


class GmailProvider:
    base_url = "https://gmail.googleapis.com/gmail/v1/users/me"

    async def _get_access_token(self, db) -> str | None:
        return await oauth.get_access_token(db)

    async def _api_get(self, url: str, access_token: str, params: dict[str, Any] | None = None) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return _parse_json_payload(
                response,
                operation="api_get",
                expected_types=(dict,),
                fallback={},
            )

    async def _api_post(self, url: str, access_token: str, payload: dict[str, Any]) -> dict:
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            if not response.content:
                return {}
            return _parse_json_payload(
                response,
                operation="api_post",
                expected_types=(dict,),
                fallback={},
            )

    async def _list_inbox_message_ids(self, access_token: str) -> list[str]:
        payload = await self._api_get(
            f"{self.base_url}/messages",
            access_token,
            params={"maxResults": 50, "labelIds": "INBOX"},
        )
        return [str(item.get("id")) for item in payload.get("messages", []) if item.get("id")]

    async def _list_delta_message_ids(self, access_token: str, history_id: str) -> list[str] | None:
        try:
            payload = await self._api_get(
                f"{self.base_url}/history",
                access_token,
                params={
                    "startHistoryId": history_id,
                    "historyTypes": "messageAdded",
                    "labelId": "INBOX",
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

        ids: list[str] = []
        seen: set[str] = set()
        for item in payload.get("history", []) or []:
            for added in item.get("messagesAdded", []) or []:
                message = added.get("message", {}) if isinstance(added, dict) else {}
                message_id = str(message.get("id") or "").strip()
                if message_id and message_id not in seen:
                    seen.add(message_id)
                    ids.append(message_id)
        return ids

    async def _get_message(self, access_token: str, message_id: str) -> dict | None:
        try:
            payload = await self._api_get(
                f"{self.base_url}/messages/{quote(message_id, safe='')}",
                access_token,
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Message-ID", "References"]},
            )
            return payload
        except httpx.HTTPError as exc:
            logger.warning("gmail_fetch_message_failed message_id=%s error=%s", message_id, exc)
            return None

    @staticmethod
    def _header_value(headers: list[dict[str, Any]], name: str) -> str:
        for header in headers:
            if str(header.get("name", "")).lower() == name.lower():
                return str(header.get("value") or "")
        return ""

    @classmethod
    def _to_sync_message(cls, item: dict) -> dict:
        payload = item.get("payload", {}) if isinstance(item, dict) else {}
        headers = payload.get("headers", []) if isinstance(payload, dict) else []
        labels = item.get("labelIds", []) if isinstance(item, dict) else []
        internal_date_ms = int(str(item.get("internalDate") or "0") or "0")
        received_at = datetime.fromtimestamp(max(0, internal_date_ms) / 1000.0, tz=timezone.utc)

        subject = cls._header_value(headers, "Subject")
        from_header = cls._header_value(headers, "From")
        from_name, from_email = parseaddr(from_header)
        snippet = str(item.get("snippet") or "")

        return {
            "id": str(item.get("id") or ""),
            "subject": subject,
            "bodyPreview": snippet,
            "from": {"emailAddress": {"address": from_email or from_header, "name": from_name or None}},
            "receivedDateTime": received_at.isoformat(),
            "conversationId": str(item.get("threadId") or ""),
            "isRead": "UNREAD" not in labels,
        }

    async def _latest_history_id(self, access_token: str) -> str | None:
        payload = await self._api_get(f"{self.base_url}/profile", access_token)
        history_id = str(payload.get("historyId") or "").strip()
        return history_id or None

    async def get_inbox_delta(self, db, delta_token: str | None = None) -> tuple[list[dict], str | None]:
        access_token = await self._get_access_token(db)
        if not access_token:
            return [], None

        try:
            if delta_token:
                message_ids = await self._list_delta_message_ids(access_token, delta_token)
                if message_ids is None:
                    message_ids = await self._list_inbox_message_ids(access_token)
            else:
                message_ids = await self._list_inbox_message_ids(access_token)

            messages: list[dict] = []
            for message_id in message_ids:
                raw = await self._get_message(access_token, message_id)
                if raw is None:
                    continue
                messages.append(self._to_sync_message(raw))

            next_delta = await self._latest_history_id(access_token)
            return messages, next_delta
        except httpx.HTTPError as exc:
            logger.warning("gmail_inbox_delta_failed error=%s", exc)
            return [], None

    async def send_mail(self, db, *, to_recipients: list[str], subject: str, body_text: str) -> bool:
        access_token = await self._get_access_token(db)
        if not access_token:
            return False

        recipients = [value.strip() for value in to_recipients if value and value.strip()]
        if not recipients:
            return False

        msg = EmailMessage()
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = (subject or "").strip() or "Update"
        msg.set_content((body_text or "").strip() or "Quick update.")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        try:
            await self._api_post(f"{self.base_url}/messages/send", access_token, {"raw": raw})
            return True
        except httpx.HTTPError as exc:
            logger.warning("gmail_send_failed error=%s", exc)
            return False

    async def reply_to_message(self, db, *, message_id: str, body_text: str) -> bool:
        access_token = await self._get_access_token(db)
        if not access_token:
            return False

        if not message_id.strip():
            return False

        original = await self._get_message(access_token, message_id)
        if original is None:
            return False

        payload = original.get("payload", {}) if isinstance(original, dict) else {}
        headers = payload.get("headers", []) if isinstance(payload, dict) else []
        from_header = self._header_value(headers, "From")
        subject = self._header_value(headers, "Subject")
        message_id_header = self._header_value(headers, "Message-ID")
        references_header = self._header_value(headers, "References")

        msg = EmailMessage()
        msg["To"] = from_header
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}" if subject else "Re:"
        if message_id_header:
            msg["In-Reply-To"] = message_id_header
            msg["References"] = (f"{references_header} {message_id_header}".strip() if references_header else message_id_header)
        msg.set_content((body_text or "").strip() or "Thanks for your email.")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        try:
            await self._api_post(
                f"{self.base_url}/messages/send",
                access_token,
                {"raw": raw, "threadId": str(original.get("threadId") or "")},
            )
            return True
        except httpx.HTTPError as exc:
            logger.warning("gmail_reply_failed error=%s", exc)
            return False

    async def search_people(self, db, *, query: str, limit: int = 8) -> list[dict]:
        # Gmail API does not provide a direct people search endpoint under gmail.* scopes.
        # Local sender history fallback is used by callers.
        return []
