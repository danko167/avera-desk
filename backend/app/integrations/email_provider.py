from __future__ import annotations

from .gmail import oauth as gmail_oauth
from .gmail.gmail_provider import GmailProvider
from .m365 import oauth as m365_oauth
from .m365.graph_provider import GraphProvider


def normalize_email_provider(value: str | None) -> str:
    provider = str(value or "m365").strip().lower()
    if provider not in {"m365", "gmail"}:
        return "m365"
    return provider


def get_oauth_module(provider: str):
    normalized = normalize_email_provider(provider)
    if normalized == "gmail":
        return gmail_oauth
    return m365_oauth


def get_email_api_provider(provider: str):
    normalized = normalize_email_provider(provider)
    if normalized == "gmail":
        return GmailProvider()
    return GraphProvider()
