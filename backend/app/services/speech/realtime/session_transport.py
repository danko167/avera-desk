from __future__ import annotations

import json
from typing import Type
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

TRANSCRIPTION_LANGUAGE = "en"
TRANSCRIPTION_DELAY = "high"
TRANSCRIPTION_DELAY_SUPPORTED_MODELS = {
    "gpt-realtime-whisper",
}


def create_transcription_client_secret(
    *,
    base_url: str,
    api_key: str,
    model: str,
    error_cls: Type[Exception],
) -> str:
    normalized_model = model.strip().lower()
    transcription: dict[str, str] = {
        "model": model,
        "language": TRANSCRIPTION_LANGUAGE,
    }
    if normalized_model in TRANSCRIPTION_DELAY_SUPPORTED_MODELS:
        transcription["delay"] = TRANSCRIPTION_DELAY

    request_body = {
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": transcription,
                    "turn_detection": None,
                }
            },
        }
    }
    request = Request(
        f"{base_url}/realtime/client_secrets",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = extract_http_error_detail(exc)
        raise error_cls(
            f"Failed to create transcription session: {detail}"
        ) from exc
    except URLError as exc:
        raise error_cls(
            f"Failed to create transcription session: {exc.reason}"
        ) from exc
    except (TimeoutError, OSError, ValueError) as exc:
        raise error_cls(
            f"Failed to create transcription session: {exc}"
        ) from exc

    secret = str(payload.get("value") or "").strip()
    if not secret:
        raise error_cls("OpenAI did not return a realtime client secret.")

    return secret


def extract_http_error_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        return f"HTTP {exc.code}"

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or f"HTTP {exc.code}")
    return f"HTTP {exc.code}"


def build_realtime_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"

    base_path = parsed.path.rstrip("/")
    realtime_path = f"{base_path}/realtime" if base_path else "/realtime"
    query = ""
    return urlunparse((ws_scheme, parsed.netloc, realtime_path, "", query, ""))
