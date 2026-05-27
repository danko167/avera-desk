import unittest

from app.services.speech.intent_router import (
    ParsedSpeechIntent,
    _heuristic_route_intent,
    _stabilize_calendar_missing_slots,
)


class SpeechIntentRouterTests(unittest.TestCase):
    def test_heuristic_calendar_detects_spoken_number_time(self) -> None:
        parsed = _heuristic_route_intent(
            utterance="make an appointment with Danko tomorrow two pm",
            has_active_draft=False,
        )

        self.assertEqual(parsed.domain, "calendar")
        self.assertEqual(parsed.action, "create_event")
        self.assertEqual(parsed.missing_slots, [])

    def test_stabilizer_clears_false_missing_desired_start_at(self) -> None:
        parsed = ParsedSpeechIntent(
            domain="calendar",
            action="create_event",
            slots={},
            confidence=0.73,
            missing_slots=["desired_start_at"],
            clarification_question="What date and time should I schedule it for?",
            reasoning="llm:test",
            usage=None,
        )

        stabilized = _stabilize_calendar_missing_slots(
            parsed,
            utterance="Make an appointment with tank of or tomorrow two pm",
        )

        self.assertEqual(stabilized.missing_slots, [])
        self.assertIsNone(stabilized.clarification_question)
        self.assertIn("calendar_time_rescue", stabilized.reasoning)


if __name__ == "__main__":
    unittest.main()
