"""Microsoft Graph API provider for Outlook email sync."""

from datetime import datetime, timezone
import httpx
import logging
from typing import Any
from urllib.parse import quote

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
            "graph_json_decode_failed operation=%s status_code=%s error=%s",
            operation,
            response.status_code,
            exc,
        )
        return fallback

    if not isinstance(payload, expected_types):
        expected = "/".join(value_type.__name__ for value_type in expected_types)
        logger.warning(
            "graph_json_type_mismatch operation=%s status_code=%s expected=%s actual=%s",
            operation,
            response.status_code,
            expected,
            type(payload).__name__,
        )
        return fallback

    return payload


def _to_graph_datetime(value: datetime) -> str:
    as_utc = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return as_utc.isoformat().replace("+00:00", "Z")


class GraphProvider:
    """Handle MS Graph API calls for email sync."""

    base_url = "https://graph.microsoft.com/v1.0"

    async def _get_access_token(self, db) -> str | None:
        return await oauth.get_access_token(db)

    async def _mailbox_root(self, db) -> str:
        authenticated_mailbox = (await oauth.get_authenticated_mailbox(db) or "").strip()
        if authenticated_mailbox:
            return f"/users/{quote(authenticated_mailbox, safe='@.-_')}"
        return "/me"

    async def _get_mailbox_path(self, db) -> str:
        return f"{await self._mailbox_root(db)}/mailfolders/inbox/messages/delta"

    async def get_inbox_delta(
        self,
        db,
        delta_token: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """
        Fetch incremental changes to Inbox using delta query.
        Follows all @odata.nextLink pages until a stable @odata.deltaLink is reached,
        ensuring the caller always gets a proper incremental cursor.
        Returns (messages, delta_link_url).
        """
        access_token = await self._get_access_token(db)
        if not access_token:
            return [], None

        mailbox_path = await self._get_mailbox_path(db)
        base_delta_url = f"{self.base_url}{mailbox_path}"

        # Build initial URL
        if delta_token:
            url = delta_token if delta_token.startswith("https://") else (
                f"{base_delta_url}?$deltatoken={delta_token}"
            )
            cursor_label = "incremental"
        else:
            url = (
                f"{base_delta_url}"
                "?$select=subject,bodyPreview,from,receivedDateTime,isRead,id,conversationId"
                "&$top=50"
            )
            cursor_label = "initial"

        headers = {"Authorization": f"Bearer {access_token}"}
        all_messages: list[dict] = []
        max_pages = 40  # safety limit

        for page_num in range(1, max_pages + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, headers=headers, timeout=30)
                    response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if delta_token:
                    logger.warning(
                        "graph_inbox_delta_cursor_invalid_resetting_full_sync"
                    )
                    return await self.get_inbox_delta(db, None)
                logger.warning("graph_inbox_delta_http_status_error error=%s", e)
                return [], None
            except httpx.HTTPError as e:
                logger.warning("graph_inbox_delta_http_error error=%s", e)
                return [], None

            data = _parse_json_payload(
                response,
                operation="get_inbox_delta",
                expected_types=(dict,),
                fallback={},
            )
            all_messages.extend(data.get("value", []))

            if "@odata.deltaLink" in data:
                logger.info(
                    "graph_inbox_sync_complete cursor=%s messages=%s pages=%s",
                    cursor_label,
                    len(all_messages),
                    page_num,
                )
                return all_messages, data["@odata.deltaLink"]

            if "@odata.nextLink" in data:
                url = data["@odata.nextLink"]
                # Refresh token for long pagination chains
                refreshed = await oauth.get_access_token(db)
                if refreshed:
                    access_token = refreshed
                    headers = {"Authorization": f"Bearer {access_token}"}
            else:
                logger.warning("graph_inbox_delta_missing_continuation_link")
                return all_messages, None

        logger.warning("graph_inbox_delta_pagination_limit_reached max_pages=%s", max_pages)
        return all_messages, None

    async def send_mail(
        self,
        db,
        *,
        to_recipients: list[str],
        subject: str,
        body_text: str,
    ) -> bool:
        access_token = await self._get_access_token(db)
        if not access_token:
            return False

        recipients = [
            {"emailAddress": {"address": recipient.strip()}}
            for recipient in to_recipients
            if recipient and recipient.strip()
        ]
        if not recipients:
            return False

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        mailbox_root = await self._mailbox_root(db)
        url = f"{self.base_url}{mailbox_root}/sendMail"
        payload = {
            "message": {
                "subject": (subject or "").strip() or "Update",
                "body": {
                    "contentType": "Text",
                    "content": (body_text or "").strip() or "Quick update.",
                },
                "toRecipients": recipients,
            },
            "saveToSentItems": True,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("graph_send_mail_failed error=%s", exc)
            return False

        return True

    async def reply_to_message(
        self,
        db,
        *,
        message_id: str,
        body_text: str,
    ) -> bool:
        access_token = await self._get_access_token(db)
        if not access_token:
            return False

        if not message_id.strip():
            return False

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        mailbox_root = await self._mailbox_root(db)
        encoded_message_id = quote(message_id, safe="")
        url = f"{self.base_url}{mailbox_root}/messages/{encoded_message_id}/reply"
        payload = {
            "message": {
                "body": {
                    "contentType": "Text",
                    "content": (body_text or "").strip() or "Thanks for your email.",
                }
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("graph_reply_failed error=%s", exc)
            return False

        return True

    async def create_calendar_event(
        self,
        db,
        *,
        subject: str,
        start_at: datetime,
        end_at: datetime,
        attendees: list[str] | None = None,
        timezone_name: str = "UTC",
        body_text: str | None = None,
    ) -> dict | None:
        access_token = await self._get_access_token(db)
        if not access_token:
            return None

        url = f"{self.base_url}/me/events"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        attendee_payload = [
            {
                "emailAddress": {"address": attendee.strip()},
                "type": "required",
            }
            for attendee in (attendees or [])
            if attendee and attendee.strip()
        ]

        payload = {
            "subject": (subject or "").strip() or "Meeting",
            "body": {
                "contentType": "Text",
                "content": (body_text or "").strip() or "",
            },
            "start": {
                "dateTime": _to_graph_datetime(start_at),
                "timeZone": timezone_name or "UTC",
            },
            "end": {
                "dateTime": _to_graph_datetime(end_at),
                "timeZone": timezone_name or "UTC",
            },
            "attendees": attendee_payload,
            "responseRequested": True,
            "allowNewTimeProposals": True,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                return _parse_json_payload(
                    response,
                    operation="create_calendar_event",
                    expected_types=(dict,),
                    fallback=None,
                )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                raise RuntimeError(
                    "Microsoft 365 calendar write permission is missing. Reconnect your account to grant Calendars.ReadWrite."
                ) from exc
            logger.warning("graph_create_calendar_event_failed error=%s", exc)
            return None
        except httpx.HTTPError as exc:
            logger.warning("graph_create_calendar_event_failed error=%s", exc)
            return None

    async def search_people(self, db, *, query: str, limit: int = 8) -> list[dict]:
        access_token = await self._get_access_token(db)
        if not access_token:
            return []

        query = (query or "").strip()
        if not query:
            return []

        mailbox_root = await self._mailbox_root(db)
        url = f"{self.base_url}{mailbox_root}/people"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        params = {
            "$search": f'"{query}"',
            "$top": str(max(1, min(20, int(limit)))),
            "$select": "displayName,scoredEmailAddresses",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=20)
                response.raise_for_status()
                payload = _parse_json_payload(
                    response,
                    operation="search_people",
                    expected_types=(dict,),
                    fallback={},
                )
        except httpx.HTTPError:
            return []

        results: list[dict] = []
        for person in payload.get("value", []):
            display_name = (person.get("displayName") or "").strip() or None
            for item in person.get("scoredEmailAddresses", []) or []:
                address = (item.get("address") or "").strip().lower()
                score = float(item.get("relevanceScore") or 0.0)
                if not address:
                    continue
                results.append({
                    "email": address,
                    "display_name": display_name,
                    "score": score,
                })

        return results

    async def get_upcoming_events(
        self,
        db,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int = 25,
    ) -> list[dict]:
        access_token = await self._get_access_token(db)
        if not access_token:
            return []

        mailbox_root = await self._mailbox_root(db)
        url = f"{self.base_url}{mailbox_root}/calendarView"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="UTC"',
        }
        params = {
            "startDateTime": _to_graph_datetime(start_at),
            "endDateTime": _to_graph_datetime(end_at),
            "$top": str(max(1, min(100, int(limit)))),
            "$orderby": "start/dateTime",
            "$select": (
                "id,subject,start,end,isAllDay,organizer,attendees,location,webLink,onlineMeeting,showAs"
            ),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                payload = _parse_json_payload(
                    response,
                    operation="get_upcoming_events",
                    expected_types=(dict,),
                    fallback={},
                )
        except httpx.HTTPError as exc:
            logger.warning("graph_get_upcoming_events_failed error=%s", exc)
            return []

        events: list[dict] = []
        for item in payload.get("value", []):
            attendees = [
                {
                    "email": (attendee.get("emailAddress") or {}).get("address"),
                    "name": (attendee.get("emailAddress") or {}).get("name"),
                    "type": attendee.get("type"),
                    "status": (attendee.get("status") or {}).get("response"),
                }
                for attendee in item.get("attendees", []) or []
            ]
            events.append(
                {
                    "id": item.get("id"),
                    "subject": item.get("subject") or "",
                    "start_at": (item.get("start") or {}).get("dateTime"),
                    "end_at": (item.get("end") or {}).get("dateTime"),
                    "timezone": (item.get("start") or {}).get("timeZone") or "UTC",
                    "is_all_day": bool(item.get("isAllDay", False)),
                    "show_as": item.get("showAs"),
                    "organizer_email": ((item.get("organizer") or {}).get("emailAddress") or {}).get("address"),
                    "organizer_name": ((item.get("organizer") or {}).get("emailAddress") or {}).get("name"),
                    "location": (item.get("location") or {}).get("displayName"),
                    "attendees": attendees,
                    "web_link": item.get("webLink"),
                    "online_meeting_url": (item.get("onlineMeeting") or {}).get("joinUrl"),
                }
            )

        return events

    async def get_availability(
        self,
        db,
        *,
        attendees: list[str],
        start_at: datetime,
        end_at: datetime,
        interval_minutes: int = 30,
    ) -> list[dict]:
        access_token = await self._get_access_token(db)
        if not access_token:
            return []

        normalized_attendees = [email.strip().lower() for email in attendees if email and email.strip()]
        if not normalized_attendees:
            return []

        mailbox_root = await self._mailbox_root(db)
        url = f"{self.base_url}{mailbox_root}/calendar/getSchedule"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="UTC"',
        }
        payload = {
            "schedules": normalized_attendees,
            "startTime": {
                "dateTime": _to_graph_datetime(start_at),
                "timeZone": "UTC",
            },
            "endTime": {
                "dateTime": _to_graph_datetime(end_at),
                "timeZone": "UTC",
            },
            "availabilityViewInterval": max(5, min(60, int(interval_minutes))),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = _parse_json_payload(
                    response,
                    operation="get_availability",
                    expected_types=(dict,),
                    fallback={},
                )
        except httpx.HTTPError as exc:
            logger.warning("graph_get_schedule_failed error=%s", exc)
            return []

        schedules: list[dict] = []
        for item in data.get("value", []) or []:
            schedule_items = [
                {
                    "status": schedule_item.get("status"),
                    "subject": schedule_item.get("subject"),
                    "is_private": bool(schedule_item.get("isPrivate", False)),
                    "start_at": (schedule_item.get("start") or {}).get("dateTime"),
                    "end_at": (schedule_item.get("end") or {}).get("dateTime"),
                    "location": schedule_item.get("location"),
                }
                for schedule_item in item.get("scheduleItems", []) or []
            ]
            schedules.append(
                {
                    "email": item.get("scheduleId"),
                    "availability_view": item.get("availabilityView") or "",
                    "items": schedule_items,
                }
            )
        return schedules
