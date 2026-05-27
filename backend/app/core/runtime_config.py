from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from .paths import get_backend_root, is_packaged_runtime
from ..services.shared.preferences import get_settings

_DEFAULT_SPEECH_MODEL = "whisper-1"


def _load_env() -> None:
    if is_packaged_runtime():
        return

    # Load backend/.env explicitly because the dev server is started from frontend/.
    env_path = get_backend_root() / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


_load_env()


@dataclass(frozen=True)
class AiConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _default_base_url(provider: str) -> str:
    if provider == "openrouter":
        return _first_non_empty(
            os.getenv("OPENROUTER_BASE_URL"),
            "https://openrouter.ai/api/v1",
        )

    if provider == "local":
        return _first_non_empty(
            os.getenv("LOCAL_AI_BASE_URL"),
            "http://localhost:11434/v1",
        )

    return _first_non_empty(
        os.getenv("OPENAI_BASE_URL"),
        "https://api.openai.com/v1",
    )


def _default_api_key(provider: str) -> str:
    if provider == "openrouter":
        return _first_non_empty(os.getenv("OPENROUTER_API_KEY"))

    if provider == "local":
        return _first_non_empty(os.getenv("LOCAL_AI_API_KEY"))

    return _first_non_empty(os.getenv("OPENAI_API_KEY"))


async def get_speech_config(db: AsyncSession | None = None) -> AiConfig:
    settings = await get_settings(db) if db is not None else None

    provider = _first_non_empty(
        settings.get("speech_provider") if settings is not None else None,
        os.getenv("STT_PROVIDER"),
        os.getenv("LLM_PROVIDER"),
        "openai",
    ).lower()
    if provider not in {"openai", "openrouter", "local"}:
        provider = "openai"

    model = _first_non_empty(
        settings.get("speech_model") if settings is not None else None,
        os.getenv("STT_MODEL"),
        os.getenv("LLM_MODEL"),
        _DEFAULT_SPEECH_MODEL,
    )
    base_url = _first_non_empty(
        settings.get("speech_base_url") if settings is not None else None,
        _default_base_url(provider),
    )
    api_key = _default_api_key(provider)

    if settings is not None:
        from .secret_store import get_secret
        api_key = _first_non_empty(get_secret("speech_api_key"), api_key)

    if not api_key:
        raise ValueError(
            f"Missing speech API key for provider={provider}. Set the matching key in backend/.env or save it in Settings."
        )

    return AiConfig(
        provider=provider,
        model=model,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
    )


async def get_llm_config(db: AsyncSession | None = None) -> AiConfig:
    settings = await get_settings(db) if db is not None else None

    provider = _first_non_empty(os.getenv("LLM_PROVIDER"), "openai").lower()
    model = _first_non_empty(os.getenv("LLM_MODEL"), os.getenv("STT_MODEL"))
    base_url = _default_base_url(provider)
    api_key = _default_api_key(provider)

    if settings is not None:
        provider = _first_non_empty(settings.get("llm_provider"), provider).lower()
        if provider not in {"openai", "openrouter", "local"}:
            provider = "openai"
        model = _first_non_empty(settings.get("llm_model"), model)
        base_url = _first_non_empty(settings.get("llm_base_url"), base_url)
        from .secret_store import get_secret
        api_key = _first_non_empty(get_secret("llm_api_key"), api_key)

    return AiConfig(
        provider=provider,
        model=model,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
    )
