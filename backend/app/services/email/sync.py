"""Email sync and storage."""

from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.tables import EmailItem
from ...integrations.email_provider import get_email_api_provider, normalize_email_provider
from ..shared.preferences import get_settings

logger = logging.getLogger(__name__)


async def get_latest_delta_token(db: AsyncSession) -> str | None:
    """Get the last stored delta token for inbox sync."""
    result = await db.execute(
        select(EmailItem.delta_token)
        .where(EmailItem.delta_token.isnot(None))
        .order_by(EmailItem.synced_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def sync_inbox(db: AsyncSession) -> tuple[int, list[dict]]:
    """
    Fetch incremental changes from Inbox and store new/updated emails.
    Returns count plus new unread emails that should trigger attention.
    """
    settings = await get_settings(db)
    email_provider = normalize_email_provider(settings.get("email_provider"))
    provider = get_email_api_provider(email_provider)
    delta_token = await get_latest_delta_token(db)
    had_delta_cursor = delta_token is not None

    messages, next_delta_token = await provider.get_inbox_delta(db, delta_token)

    count = 0
    new_unread_emails: list[dict] = []
    now = datetime.now(timezone.utc)
    latest_item: EmailItem | None = None

    for msg in messages:
        # Skip deleted items (they have @removed)
        if "@removed" in msg:
            continue

        msg_id = msg.get("id")
        if not msg_id:
            continue

        # Upsert: update if exists, insert if new
        stmt = select(EmailItem).where(EmailItem.id == msg_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        from_name: str | None = None
        from_addr = msg.get("from", {})
        if isinstance(from_addr, dict):
            from_addr = from_addr.get("emailAddress", {})
            if isinstance(from_addr, dict):
                from_name = (from_addr.get("name") or "").strip() or None
                from_addr = from_addr.get("address", "unknown")

        is_new = False
        if existing:
            existing.subject = msg.get("subject", "")
            existing.from_address = from_addr
            existing.from_name = from_name
            existing.body_preview = msg.get("bodyPreview", "")
            existing.conversation_id = msg.get("conversationId")
            existing.is_read = msg.get("isRead", False)
            existing.synced_at = now
            # DB stores naive datetimes; normalise to UTC-aware for comparisons
            received_at = existing.received_at
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        else:
            is_new = True
            # Graph returns ISO 8601 with 'Z' suffix; replace for cross-version compat
            received_str = msg.get("receivedDateTime", now.isoformat()).replace("Z", "+00:00")
            received_at = datetime.fromisoformat(received_str)
            item = EmailItem(
                id=msg_id,
                subject=msg.get("subject", ""),
                from_address=from_addr,
                from_name=from_name,
                body_preview=msg.get("bodyPreview", ""),
                conversation_id=msg.get("conversationId"),
                received_at=received_at,
                is_read=msg.get("isRead", False),
                synced_at=now,
            )
            db.add(item)
            latest_item = item

        # Track new unread emails for attention trigger
        # Only notify for truly new emails when we already had a delta cursor.
        # On first sync (no cursor) we're seeding the DB silently — no notifications.
        if is_new and not msg.get("isRead", False) and had_delta_cursor:
            preview = str(msg.get("bodyPreview", "") or "")
            new_unread_emails.append({
                "id": msg_id,
                "subject": msg.get("subject", ""),
                "from": from_addr,
                "body_preview": preview,
            })

        count += 1

        if existing is not None and (latest_item is None or existing.synced_at >= latest_item.synced_at):
            latest_item = existing

    # Store the new delta token on the most recently synced item.
    # Always update — even on 0-message incremental polls the server may
    # return a new deltaLink that should replace the old cursor.
    if next_delta_token:
        last = latest_item
        if last is None:
            last_item = await db.execute(
                select(EmailItem).order_by(EmailItem.synced_at.desc()).limit(1)
            )
            last = last_item.scalar_one_or_none()
        if last:
            last.delta_token = next_delta_token

    await db.commit()
    logger.info("email_sync_completed count=%s new_unread=%s", count, len(new_unread_emails))
    return count, new_unread_emails
