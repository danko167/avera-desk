from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from fastapi import WebSocket
import websockets
from websockets.exceptions import WebSocketException

from ....core.runtime_config import AiConfig
from ....core.transcription_trace import TranscriptionTrace
from .session_transport import build_realtime_url, create_transcription_client_secret
from .text_processing import (
    clarification_prompt_for_text,
    compute_transcript_confidence,
    is_prompt_text,
    join_transcript_parts,
    sanitize_realtime_transcript_text,
    should_request_clarification,
)

logger = logging.getLogger(__name__)

class RealtimeTranscriptionError(RuntimeError):
    pass


LIVE_COMMIT_INTERVAL_SECONDS = 0.60
LIVE_COMMIT_MIN_BYTES = 7200
FINAL_TRANSCRIPT_DEDUP_WINDOW_SECONDS = 3.0
FINAL_TRANSCRIPT_DISPATCH_DEBOUNCE_SECONDS = 0.85
FINAL_TRANSCRIPT_DISPATCH_ON_STOP_ONLY = True
FinalTranscriptHook = Callable[[str, str, str | None], Awaitable[None]]


@dataclass
class RealtimeTranscriber:
    client_ws: WebSocket
    trace: TranscriptionTrace | None = None
    on_final_transcript: FinalTranscriptHook | None = None
    upstream: Any | None = None
    recv_task: asyncio.Task[None] | None = None
    _closed: bool = field(default=False, init=False)
    _final_text: str = field(default="", init=False)
    _live_text: str = field(default="", init=False)
    _transcript_done: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _upstream_failed: bool = field(default=False, init=False)
    _commit_in_flight: bool = field(default=False, init=False)
    _pending_audio_bytes: int = field(default=0, init=False)
    _last_commit_at: float = field(default_factory=time.monotonic, init=False)
    _latest_meaningful_text: str = field(default="", init=False)
    _last_persisted_text: str = field(default="", init=False)
    _last_emitted_final_text_norm: str = field(default="", init=False)
    _last_emitted_final_at: float = field(default=0.0, init=False)
    _callback_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)
    _pending_final_dispatch_task: asyncio.Task[None] | None = field(default=None, init=False)
    _pending_final_text: str = field(default="", init=False)
    _pending_final_mode: str = field(default="push-to-talk", init=False)
    _pending_final_session_id: str | None = field(default=None, init=False)
    _last_clarification_text_norm: str = field(default="", init=False)
    _last_clarification_at: float = field(default=0.0, init=False)

    def _normalize_final_text(self, text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def _is_duplicate_final(self, text: str) -> bool:
        normalized = self._normalize_final_text(text)
        if not normalized:
            return False

        now = time.monotonic()
        if (
            normalized == self._last_emitted_final_text_norm
            and (now - self._last_emitted_final_at) <= FINAL_TRANSCRIPT_DEDUP_WINDOW_SECONDS
        ):
            return True

        self._last_emitted_final_text_norm = normalized
        self._last_emitted_final_at = now
        return False

    async def start(self, config: AiConfig) -> None:
        if not config.model:
            raise RealtimeTranscriptionError("Missing speech model in settings or backend/.env")

        client_secret_started_at = time.monotonic()
        client_secret = await asyncio.to_thread(
            create_transcription_client_secret,
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            error_cls=RealtimeTranscriptionError,
        )
        if self.trace is not None:
            self.trace.log_client_secret_created(
                elapsed_seconds=time.monotonic() - client_secret_started_at
            )
        realtime_url = build_realtime_url(config.base_url)
        headers = {
            "Authorization": f"Bearer {client_secret}",
        }

        try:
            connect_started_at = time.monotonic()
            if self.trace is not None:
                self.trace.log_upstream_connecting(url=realtime_url)
            self.upstream = await websockets.connect(
                realtime_url,
                additional_headers=headers,
                max_size=2**22,
            )
            if self.trace is not None:
                self.trace.log_upstream_connected(
                    elapsed_seconds=time.monotonic() - connect_started_at
                )
        except (OSError, WebSocketException) as exc:
            if self.trace is not None:
                self.trace.log_upstream_connect_failed(error=str(exc))
            raise RealtimeTranscriptionError(
                f"Failed to connect realtime transcription upstream: {exc}"
            ) from exc

        await self.upstream.send(json.dumps({"type": "input_audio_buffer.clear"}))

        self.recv_task = asyncio.create_task(self._recv_loop())

    async def append_audio(self, audio_b64: str, byte_count: int) -> None:
        if self._closed or self._upstream_failed or not self.upstream:
            return
        try:
            await self.upstream.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": audio_b64,
                    }
                )
            )
            self._pending_audio_bytes += max(byte_count, 0)
            if self.trace is not None:
                self.trace.log_audio_append(
                    byte_count=byte_count,
                    pending_bytes=self._pending_audio_bytes,
                )
        except (OSError, RuntimeError, WebSocketException) as exc:
            await self._mark_upstream_failed(f"Transcription stream interrupted: {exc}")

    async def commit(self) -> None:
        await self._commit_buffer(wait_for_result=True)

    async def maybe_commit_live(self) -> None:
        if self._closed or self._upstream_failed:
            return
        if self._commit_in_flight:
            return
        if self._pending_audio_bytes < LIVE_COMMIT_MIN_BYTES:
            return
        if (time.monotonic() - self._last_commit_at) < LIVE_COMMIT_INTERVAL_SECONDS:
            return

        await self._commit_buffer(wait_for_result=False)

    async def _commit_buffer(self, *, wait_for_result: bool) -> None:
        if self._closed or self._upstream_failed or not self.upstream:
            return

        if self._commit_in_flight:
            if wait_for_result:
                try:
                    await asyncio.wait_for(self._transcript_done.wait(), timeout=2.5)
                except asyncio.TimeoutError:
                    pass
            return

        if self._pending_audio_bytes <= 0:
            return

        # OpenAI rejects commits smaller than ~100ms of audio. During stop,
        # the final partial chunk can be shorter, so skip this commit safely.
        if self._pending_audio_bytes < LIVE_COMMIT_MIN_BYTES:
            return

        pending_before_commit = self._pending_audio_bytes
        self._transcript_done.clear()
        self._commit_in_flight = True
        self._pending_audio_bytes = 0
        self._last_commit_at = time.monotonic()
        try:
            if self.trace is not None:
                self.trace.log_audio_commit(
                    wait_for_result=wait_for_result,
                    pending_before_commit=pending_before_commit,
                )
            await self.upstream.send(json.dumps({"type": "input_audio_buffer.commit"}))
        except (OSError, RuntimeError, WebSocketException) as exc:
            self._commit_in_flight = False
            await self._mark_upstream_failed(f"Transcription stream interrupted: {exc}")
            return

        if wait_for_result:
            try:
                await asyncio.wait_for(self._transcript_done.wait(), timeout=2.5)
            except asyncio.TimeoutError:
                pass

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self.recv_task is not None:
            self.recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await self.recv_task

        if self.upstream is not None:
            with contextlib.suppress(OSError, RuntimeError, WebSocketException):
                await self.upstream.close()
            self.upstream = None

        if self._pending_final_dispatch_task is not None:
            self._pending_final_dispatch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await self._pending_final_dispatch_task
            self._pending_final_dispatch_task = None

        if self.trace is not None:
            self.trace.log_session_summary()

    async def flush_pending_final_dispatch(self) -> None:
        if self.on_final_transcript is None:
            return

        task = self._pending_final_dispatch_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._pending_final_dispatch_task = None

        text = self._sanitize_transcript_text(self._pending_final_text, source="flush")
        if not text:
            return

        confidence = compute_transcript_confidence(text=text, event=None, sanitization_applied=False)
        if should_request_clarification(confidence):
            await self._emit_clarification(text=text, confidence=confidence, source="flush")
            self._pending_final_text = ""
            return

        await self._emit_final_callback(
            text,
            self._pending_final_mode,
            self._pending_final_session_id,
        )
        self._pending_final_text = ""

    async def _recv_loop(self) -> None:
        assert self.upstream is not None

        try:
            async for raw in self.upstream:
                event = json.loads(raw)
                event_type = str(event.get("type", ""))
                logger.debug("realtime_upstream_event type=%s", event_type)
                if self.trace is not None:
                    self.trace.log_upstream_event(event_type=event_type)

                if event_type == "conversation.item.input_audio_transcription.delta":
                    delta = str(event.get("delta", ""))
                    if delta:
                        partial_text = join_transcript_parts(self._final_text, f"{self._live_text}{delta}")
                        self._live_text = f"{self._live_text}{delta}"

                        if self.trace is not None:
                            self.trace.log_partial_transcript(text=partial_text, source="delta")
                        await self.client_ws.send_json(
                            {
                                "type": "transcript_partial",
                                "text": partial_text,
                            }
                        )
                        normalized_partial = self._sanitize_transcript_text(partial_text, source="delta")
                        if normalized_partial and not is_prompt_text(normalized_partial):
                            self._latest_meaningful_text = normalized_partial
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    sanitized = sanitize_realtime_transcript_text(str(event.get("transcript", "")))
                    transcript = self._sanitize_transcript_text(sanitized.cleaned_text, source="completed")
                    candidate_text = transcript or self._live_text or self._latest_meaningful_text
                    candidate_text = self._sanitize_transcript_text(candidate_text, source="completed-candidate")
                    self._live_text = ""
                    self._commit_in_flight = False

                    if transcript:
                        self._final_text = join_transcript_parts(self._final_text, transcript)
                    elif candidate_text:
                        self._final_text = join_transcript_parts(self._final_text, candidate_text)
                    if self.trace is not None:
                        self.trace.log_final_transcript(
                            text=self._final_text,
                            source="completed",
                        )
                    if self._is_duplicate_final(self._final_text):
                        if self.trace is not None:
                            self.trace.log_partial_transcript(
                                text=self._final_text,
                                source="duplicate-final-ignored",
                            )
                        self._transcript_done.set()
                        continue

                    confidence = compute_transcript_confidence(
                        text=self._final_text,
                        event=event,
                        sanitization_applied=sanitized.applied,
                    )
                    if should_request_clarification(confidence):
                        await self._emit_clarification(
                            text=self._final_text,
                            confidence=confidence,
                            source="completed",
                        )
                        self._transcript_done.set()
                        continue

                    await self.client_ws.send_json(
                        {
                            "type": "transcript_final",
                            "text": self._final_text,
                        }
                    )
                    if self.on_final_transcript is not None:
                        self._queue_final_callback(
                            self._final_text,
                            "push-to-talk",
                            self.trace.session_id if self.trace is not None else None,
                        )
                    self._transcript_done.set()
                elif event_type == "conversation.item.input_audio_transcription.failed":
                    self._commit_in_flight = False
                    self._live_text = ""
                    self._transcript_done.set()
                elif event_type == "error":
                    self._commit_in_flight = False
                    self._transcript_done.set()
                    error_payload = event.get("error")
                    if isinstance(error_payload, dict):
                        message = str(error_payload.get("message") or "Realtime transcription error")
                    else:
                        message = str(event.get("message") or error_payload or "Realtime transcription error")
                    await self._mark_upstream_failed(f"Transcription error: {message}")
        except asyncio.CancelledError:
            pass
        except (OSError, RuntimeError, WebSocketException, json.JSONDecodeError) as exc:
            await self._mark_upstream_failed(f"Transcription stream interrupted: {exc}")

    async def _mark_upstream_failed(self, message: str) -> None:
        self._upstream_failed = True
        self._commit_in_flight = False
        self._transcript_done.set()
        if self.trace is not None:
            self.trace.log_error(source="upstream", message=message)
        with contextlib.suppress(RuntimeError):
            await self.client_ws.send_json(
                {
                    "type": "transcript_partial",
                    "text": message,
                }
            )

    async def persist_fallback_transcript_if_needed(self) -> None:
        if self.on_final_transcript is None:
            return
        candidate = self._sanitize_transcript_text(self._latest_meaningful_text, source="fallback")
        if not candidate:
            return
        confidence = compute_transcript_confidence(text=candidate, event=None, sanitization_applied=False)
        if should_request_clarification(confidence):
            await self._emit_clarification(text=candidate, confidence=confidence, source="fallback")
            return
        if self._normalize_final_text(candidate) == self._normalize_final_text(self._last_persisted_text):
            return
        if self._is_duplicate_final(candidate):
            return
        if is_prompt_text(candidate):
            return
        self._queue_final_callback(
            candidate,
            "push-to-talk",
            self.trace.session_id if self.trace is not None else None,
        )

    def _queue_final_callback(self, text: str, mode: str, session_id: str | None) -> None:
        cleaned_text = self._sanitize_transcript_text(text, source="queue")
        normalized = self._normalize_final_text(cleaned_text)
        if not normalized:
            return

        self._pending_final_text = cleaned_text
        self._pending_final_mode = mode
        self._pending_final_session_id = session_id

        if self._pending_final_dispatch_task is not None:
            self._pending_final_dispatch_task.cancel()

        if FINAL_TRANSCRIPT_DISPATCH_ON_STOP_ONLY:
            return

        task = asyncio.create_task(self._dispatch_final_callback_after_delay())
        self._pending_final_dispatch_task = task
        self._callback_tasks.add(task)
        task.add_done_callback(self._callback_tasks.discard)

    async def _dispatch_final_callback_after_delay(self) -> None:
        try:
            await asyncio.sleep(FINAL_TRANSCRIPT_DISPATCH_DEBOUNCE_SECONDS)
            text = self._sanitize_transcript_text(self._pending_final_text, source="dispatch")
            mode = self._pending_final_mode
            session_id = self._pending_final_session_id
            if not text:
                return

            confidence = compute_transcript_confidence(text=text, event=None, sanitization_applied=False)
            if should_request_clarification(confidence):
                await self._emit_clarification(text=text, confidence=confidence, source="dispatch")
                return

            await self._emit_final_callback(text, mode, session_id)
        except asyncio.CancelledError:
            pass
        finally:
            current = asyncio.current_task()
            if current is self._pending_final_dispatch_task:
                self._pending_final_dispatch_task = None

    async def _emit_final_callback(self, text: str, mode: str, session_id: str | None) -> None:
        if self.on_final_transcript is None:
            return
        await self.on_final_transcript(text, mode, session_id)
        self._last_persisted_text = text

    def _sanitize_transcript_text(self, text: str, *, source: str) -> str:
        result = sanitize_realtime_transcript_text(text)
        if result.applied and self.trace is not None:
            self.trace.log_partial_transcript(
                text=f"source={source} prefix={result.prefix!r} cleaned={result.cleaned_text!r}",
                source="sanitize-applied",
            )
        return result.cleaned_text

    async def _emit_clarification(self, *, text: str, confidence: float, source: str) -> None:
        normalized = self._normalize_final_text(text)
        now = time.monotonic()
        if (
            normalized
            and normalized == self._last_clarification_text_norm
            and (now - self._last_clarification_at) <= FINAL_TRANSCRIPT_DEDUP_WINDOW_SECONDS
        ):
            return

        self._last_clarification_text_norm = normalized
        self._last_clarification_at = now

        if self.trace is not None:
            self.trace.log_partial_transcript(
                text=f"source={source} confidence={confidence:.2f} text={text!r}",
                source="clarification-requested",
            )

        await self.client_ws.send_json(
            {
                "type": "transcript_partial",
                "text": clarification_prompt_for_text(text),
            }
        )
