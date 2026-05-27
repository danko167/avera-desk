import unittest

from app.services.ws.handlers import _classify_control_intent, _format_recognized_action_label


class RecognizedActionLabelTests(unittest.TestCase):
    def test_known_calendar_outcome_is_mapped(self) -> None:
        label = _format_recognized_action_label("calendar_proposal_approved")
        self.assertEqual(label, "Calendar proposal approved")

    def test_unknown_outcome_is_humanized(self) -> None:
        label = _format_recognized_action_label("new_future_outcome")
        self.assertEqual(label, "New future outcome recognized")


class ControlIntentClassificationTests(unittest.TestCase):
    def test_send_it_variant_s_and_it_is_send_control(self) -> None:
        kind, normalized = _classify_control_intent("S And it")
        self.assertEqual(kind, "send_control")
        self.assertEqual(normalized, "s and it")

    def test_send_it_variant_say_end_it_is_send_control(self) -> None:
        kind, normalized = _classify_control_intent("Say End it")
        self.assertEqual(kind, "send_control")
        self.assertEqual(normalized, "say end it")

    def test_affirmative_phrase_is_classified(self) -> None:
        kind, _ = _classify_control_intent("Sure, we can do that.")
        self.assertEqual(kind, "affirmative_short")

    def test_cancel_phrase_is_classified(self) -> None:
        kind, normalized = _classify_control_intent("Do not send")
        self.assertEqual(kind, "cancel_control")
        self.assertEqual(normalized, "do not send")


if __name__ == "__main__":
    unittest.main()
