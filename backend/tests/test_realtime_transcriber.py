import unittest
import json
from unittest.mock import patch

from app.services.speech.realtime.session_transport import create_transcription_client_secret
from app.services.speech.realtime.text_processing import (
    clarification_prompt_for_text,
    compute_transcript_confidence,
    sanitize_realtime_transcript_text,
    should_request_clarification,
)


class RealtimeTranscriberTests(unittest.TestCase):
    def test_sanitize_realtime_transcript_strips_foreign_prefix_before_latin_text(self) -> None:
        result = sanitize_realtime_transcript_text(
            "지금 지금 make a meeting danko tomorrow Tomorrow at two pm"
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.cleaned_text, "make a meeting danko tomorrow Tomorrow at two pm")

    def test_sanitize_realtime_transcript_keeps_latin_only_text(self) -> None:
        result = sanitize_realtime_transcript_text("make a meeting danko tomorrow at two pm")

        self.assertFalse(result.applied)
        self.assertEqual(result.cleaned_text, "make a meeting danko tomorrow at two pm")

    def test_sanitize_realtime_transcript_keeps_non_latin_only_text(self) -> None:
        result = sanitize_realtime_transcript_text("지금 지금")

        self.assertFalse(result.applied)
        self.assertEqual(result.cleaned_text, "지금 지금")

    def test_confidence_gate_rejects_short_low_confidence_text(self) -> None:
        confidence = compute_transcript_confidence(
            text="yes",
            event=None,
            sanitization_applied=False,
        )

        self.assertTrue(should_request_clarification(confidence))

    def test_confidence_gate_allows_direct_high_confidence_event(self) -> None:
        confidence = compute_transcript_confidence(
            text="make a meeting with Danko tomorrow at two pm",
            event={"confidence": 0.92},
            sanitization_applied=False,
        )

        self.assertFalse(should_request_clarification(confidence))

    def test_confidence_gate_allows_short_control_command_cancel(self) -> None:
        confidence = compute_transcript_confidence(
            text="Cancel.",
            event=None,
            sanitization_applied=False,
        )

        self.assertFalse(should_request_clarification(confidence))

    def test_confidence_gate_allows_short_control_command_dismiss(self) -> None:
        confidence = compute_transcript_confidence(
            text="Dismiss.",
            event=None,
            sanitization_applied=False,
        )

        self.assertFalse(should_request_clarification(confidence))

    def test_confidence_gate_allows_short_control_command_dismissed_variant(self) -> None:
        confidence = compute_transcript_confidence(
            text="Dismissed.",
            event=None,
            sanitization_applied=False,
        )

        self.assertFalse(should_request_clarification(confidence))

    def test_clarification_prompt_avoids_empty_quoted_text(self) -> None:
        message = clarification_prompt_for_text("")

        self.assertEqual(
            message,
            "I couldn't hear that clearly. Please repeat in one short sentence.",
        )

    def test_clarification_prompt_keeps_non_empty_transcript(self) -> None:
        message = clarification_prompt_for_text("Send it")

        self.assertEqual(
            message,
            'I heard "Send it" but not clearly enough. Please repeat in one short sentence.',
        )

    def test_create_transcription_client_secret_requests_language_and_delay_for_realtime_whisper(self) -> None:
        response_payload = json.dumps({"value": "secret-token"}).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return response_payload

        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=30):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch("app.services.speech.realtime.session_transport.urlopen", new=fake_urlopen):
            secret = create_transcription_client_secret(
                base_url="https://api.openai.com/v1",
                api_key="api-key",
                model="gpt-realtime-whisper",
                error_cls=RuntimeError,
            )

        self.assertEqual(secret, "secret-token")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/realtime/client_secrets")
        transcription = captured["body"]["session"]["audio"]["input"]["transcription"]
        self.assertEqual(transcription["model"], "gpt-realtime-whisper")
        self.assertEqual(transcription["language"], "en")
        self.assertEqual(transcription["delay"], "high")

    def test_create_transcription_client_secret_omits_delay_for_models_without_delay_support(self) -> None:
        response_payload = json.dumps({"value": "secret-token"}).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return response_payload

        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=30):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        models = [
            "gpt-4o-transcribe",
            "gpt-4o-mini-transcribe",
            "whisper-1",
        ]

        for model in models:
            with self.subTest(model=model):
                captured.clear()
                with patch("app.services.speech.realtime.session_transport.urlopen", new=fake_urlopen):
                    secret = create_transcription_client_secret(
                        base_url="https://api.openai.com/v1",
                        api_key="api-key",
                        model=model,
                        error_cls=RuntimeError,
                    )

                self.assertEqual(secret, "secret-token")
                self.assertEqual(captured["url"], "https://api.openai.com/v1/realtime/client_secrets")
                transcription = captured["body"]["session"]["audio"]["input"]["transcription"]
                self.assertEqual(transcription["model"], model)
                self.assertEqual(transcription["language"], "en")
                self.assertNotIn("delay", transcription)


if __name__ == "__main__":
    unittest.main()