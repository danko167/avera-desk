from __future__ import annotations

import threading
import time
import uuid
import json
from datetime import datetime

from .paths import get_logs_dir


TRACE_DIR = get_logs_dir()
TRACE_JSONL_FILE = TRACE_DIR / "transcription_trace.jsonl"
_TRACE_LOCK = threading.Lock()
_TRACE_ENABLED = False


def set_trace_enabled(enabled: bool) -> None:
    global _TRACE_ENABLED
    _TRACE_ENABLED = bool(enabled)


def _timestamp() -> str:
    # Use local machine time with offset so logs match what the user sees on desktop.
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _format_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f}ms"


def _append_json_event(event: dict[str, object]) -> None:
    if not _TRACE_ENABLED:
        return
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    with _TRACE_LOCK:
        with TRACE_JSONL_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False))
            handle.write("\n")


def _append_trace(source: str, event: str, message: str) -> None:
    timestamp = _timestamp()
    _append_json_event(
        {
            "timestamp": timestamp,
            "source": source,
            "event": event,
            "message": message,
        }
    )


class TranscriptionTrace:
    def __init__(self, *, mode: str, wake_word_required: bool, wake_word: str, provider: str, model: str) -> None:
        self.session_id = uuid.uuid4().hex[:12]
        self.mode = mode
        self.wake_word_required = wake_word_required
        self.wake_word = wake_word
        self.provider = provider
        self.model = model
        self.created_at = time.monotonic()
        self.upstream_opened_at: float | None = None
        self.audio_bytes_from_fe = 0
        self.audio_chunks_from_fe = 0
        self.audio_commits_to_openai = 0
        self.partial_count = 0
        self.final_count = 0
        self.wake_word_hits = 0
        self._write(
            "SESSION_START",
            (
                f"mode={self.mode} wake_word_required={self.wake_word_required} "
                f"wake_word={self.wake_word} provider={self.provider} model={self.model}"
            ),
        )

    def _write(self, event: str, message: str) -> None:
        _append_trace(source=self.session_id, event=event, message=message)

    def log_frontend_audio_start(self) -> None:
        self._write("FE->BE AUDIO_START", f"mode={self.mode}")

    def log_frontend_audio_chunk(self, *, byte_count: int) -> None:
        self.audio_chunks_from_fe += 1
        self.audio_bytes_from_fe += max(byte_count, 0)
        self._write(
            "FE->BE AUDIO_CHUNK",
            (
                f"chunk_index={self.audio_chunks_from_fe} bytes={byte_count} "
                f"cumulative_bytes={self.audio_bytes_from_fe}"
            ),
        )

    def log_frontend_audio_stop(self) -> None:
        self._write(
            "FE->BE AUDIO_STOP",
            f"chunks={self.audio_chunks_from_fe} bytes={self.audio_bytes_from_fe}",
        )

    def log_client_secret_created(self, *, elapsed_seconds: float) -> None:
        self._write(
            "BE->OPENAI CLIENT_SECRET",
            f"purpose=realtime_transcription elapsed={_format_ms(elapsed_seconds)}",
        )

    def log_upstream_connecting(self, *, url: str) -> None:
        self._write("BE->OPENAI CONNECT_START", f"url={url}")

    def log_upstream_connected(self, *, elapsed_seconds: float) -> None:
        self.upstream_opened_at = time.monotonic()
        self._write(
            "BE->OPENAI CONNECT_OK",
            f"elapsed={_format_ms(elapsed_seconds)}",
        )

    def log_upstream_connect_failed(self, *, error: str) -> None:
        self._write("BE->OPENAI CONNECT_FAILED", error)

    def log_audio_append(self, *, byte_count: int, pending_bytes: int) -> None:
        self._write(
            "BE->OPENAI AUDIO_APPEND",
            f"bytes={byte_count} pending_bytes={pending_bytes}",
        )

    def log_audio_commit(self, *, wait_for_result: bool, pending_before_commit: int) -> None:
        self.audio_commits_to_openai += 1
        self._write(
            "BE->OPENAI AUDIO_COMMIT",
            (
                f"commit_index={self.audio_commits_to_openai} wait_for_result={wait_for_result} "
                f"bytes={pending_before_commit}"
            ),
        )

    def log_upstream_event(self, *, event_type: str) -> None:
        self._write("OPENAI->BE EVENT", event_type)

    def log_partial_transcript(self, *, text: str, source: str) -> None:
        self.partial_count += 1
        self._write(
            "OPENAI->BE->FE PARTIAL",
            f"source={source} index={self.partial_count} text={text!r}",
        )

    def log_final_transcript(self, *, text: str, source: str) -> None:
        self.final_count += 1
        self._write(
            "OPENAI->BE->FE FINAL",
            f"source={source} index={self.final_count} text={text!r}",
        )

    def log_error(self, *, source: str, message: str) -> None:
        self._write("ERROR", f"source={source} message={message}")

    def log_session_summary(self) -> None:
        openai_duration = 0.0
        if self.upstream_opened_at is not None:
            openai_duration = time.monotonic() - self.upstream_opened_at

        total_duration = time.monotonic() - self.created_at
        self._write(
            "SESSION_END",
            (
                f"total_elapsed={_format_ms(total_duration)} "
                f"openai_elapsed={_format_ms(openai_duration)} "
                f"audio_chunks={self.audio_chunks_from_fe} audio_bytes={self.audio_bytes_from_fe} "
                f"commits={self.audio_commits_to_openai} partials={self.partial_count} "
                f"finals={self.final_count} wake_word_hits={self.wake_word_hits}"
            ),
        )
