from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.tables import EmailItem
from ...integrations.email_provider import get_email_api_provider, normalize_email_provider
from ..shared.preferences import get_settings


@dataclass(slots=True)
class ContactCandidate:
    email: str
    label: str | None
    confidence: float
    source: str


def _strip_contact_command_prefix(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^(?:send|write|compose|draft)\s+(?:an?\s+)?(?:email|mail)\s+(?:to\s+)?", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" ,.;:-")


def _normalize_local_name_query(text: str) -> str:
    lowered = _strip_contact_command_prefix(text).lower()
    ascii_folded = unicodedata.normalize("NFKD", lowered)
    ascii_folded = "".join(ch for ch in ascii_folded if not unicodedata.combining(ch))
    ascii_folded = re.sub(r"[^a-z0-9._@\-\s]", " ", ascii_folded)
    ascii_folded = re.sub(r"\s+", " ", ascii_folded).strip()
    return ascii_folded


def _normalize_provider_name_query(text: str) -> str:
    return _strip_contact_command_prefix(text)


def _token_overlap_score(query: str, candidate: str) -> float:
    q_tokens = {tok for tok in query.split() if tok}
    c_tokens = {tok for tok in re.split(r"[^a-z0-9]+", candidate.lower()) if tok}
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    return overlap / max(1, len(q_tokens))


async def _local_candidates(db: AsyncSession, query: str) -> list[ContactCandidate]:
    result = await db.execute(
        select(EmailItem.from_address, EmailItem.from_name).order_by(EmailItem.received_at.desc()).limit(500)
    )
    seen: set[str] = set()
    candidates: list[ContactCandidate] = []
    for from_address, from_name in result.all():
        email = (from_address or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        label = (from_name or "").strip() or None
        score = max(
            _token_overlap_score(query, email),
            _token_overlap_score(query, label or ""),
        )
        if query and query not in email and (label is None or query not in label.lower()) and score < 0.6:
            continue
        candidates.append(
            ContactCandidate(
                email=email,
                label=label,
                confidence=max(0.4, min(0.95, 0.55 + score * 0.4)),
                source="local",
            )
        )
    return candidates


async def _graph_candidates(db: AsyncSession, query: str) -> list[ContactCandidate]:
    if not query:
        return []
    settings = await get_settings(db)
    email_provider = normalize_email_provider(settings.get("email_provider"))
    provider = get_email_api_provider(email_provider)
    people = await provider.search_people(db, query=query, limit=8)
    candidates: list[ContactCandidate] = []
    for person in people:
        email = (person.get("email") or "").strip().lower()
        if not email:
            continue
        label = (person.get("display_name") or "").strip() or None
        score = float(person.get("score") or 0.0)
        candidates.append(
            ContactCandidate(
                email=email,
                label=label,
                confidence=max(0.45, min(0.99, 0.5 + score * 0.5)),
                source="graph",
            )
        )
    return candidates


async def resolve_contact_candidates(db: AsyncSession, *, raw_query: str) -> list[ContactCandidate]:
    local_query = _normalize_local_name_query(raw_query)
    provider_query = _normalize_provider_name_query(raw_query)
    local = await _local_candidates(db, local_query)
    graph = await _graph_candidates(db, provider_query)

    merged: dict[str, ContactCandidate] = {}
    for candidate in local + graph:
        current = merged.get(candidate.email)
        if current is None or candidate.confidence > current.confidence:
            merged[candidate.email] = candidate

    ordered = sorted(merged.values(), key=lambda item: item.confidence, reverse=True)
    return ordered[:8]
