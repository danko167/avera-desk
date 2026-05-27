from __future__ import annotations

import logging
import os
from typing import Final

try:
    import keyring
except ImportError:  # pragma: no cover - depends on local runtime environment
    keyring = None


_DEFAULT_KEYRING_SERVICE: Final[str] = "avera_desk"
_fallback_secrets: dict[str, str] = {}
logger = logging.getLogger(__name__)


def _get_keyring_service() -> str:
    configured = os.getenv("KEYRING_SERVICE", "").strip()
    return configured or _DEFAULT_KEYRING_SERVICE


def get_secret(name: str) -> str | None:
    secret_name = name.strip()
    if not secret_name:
        return None

    if keyring is not None:
        try:
            value = keyring.get_password(_get_keyring_service(), secret_name)
            if value:
                return value
        except Exception as exc:  # pragma: no cover - OS/keyring backend dependent
            logger.warning("keyring_read_failed secret_name=%s error=%s", secret_name, exc)

    return _fallback_secrets.get(secret_name)


def set_secret(name: str, value: str) -> bool:
    secret_name = name.strip()
    secret_value = value.strip()
    if not secret_name:
        return False

    if not secret_value:
        clear_secret(secret_name)
        return False

    if keyring is not None:
        try:
            keyring.set_password(_get_keyring_service(), secret_name, secret_value)
            _fallback_secrets.pop(secret_name, None)
            return True
        except Exception as exc:  # pragma: no cover - OS/keyring backend dependent
            logger.warning("keyring_write_failed secret_name=%s error=%s", secret_name, exc)

    _fallback_secrets[secret_name] = secret_value
    return False


def clear_secret(name: str) -> None:
    secret_name = name.strip()
    if not secret_name:
        return

    if keyring is not None:
        try:
            keyring.delete_password(_get_keyring_service(), secret_name)
        except Exception as exc:  # pragma: no cover - OS/keyring backend dependent
            logger.debug("keyring_delete_failed secret_name=%s error=%s", secret_name, exc)

    _fallback_secrets.pop(secret_name, None)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def get_secret_persistence(name: str) -> str:
    secret_name = name.strip()
    if not secret_name:
        return "none"

    if keyring is not None:
        try:
            value = keyring.get_password(_get_keyring_service(), secret_name)
            if value:
                return "persistent"
        except Exception as exc:  # pragma: no cover - OS/keyring backend dependent
            logger.warning("keyring_persistence_check_failed secret_name=%s error=%s", secret_name, exc)

    if secret_name in _fallback_secrets:
        return "session"

    return "none"
