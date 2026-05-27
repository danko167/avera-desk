import unittest

from app.core.control_intent import classify_control_intent, normalize_control_utterance, trim_stt_noise_prefix


class ControlIntentTests(unittest.TestCase):
    def test_normalize_control_utterance(self) -> None:
        self.assertEqual(normalize_control_utterance("  Say, End it!!  "), "say end it")

    def test_classify_send_variants(self) -> None:
        for utterance in ("send it", "S And it", "Say End it", "sand it"):
            kind, _ = classify_control_intent(utterance)
            self.assertEqual(kind, "send_control")

    def test_classify_cancel(self) -> None:
        kind, normalized = classify_control_intent("Do not send")
        self.assertEqual(kind, "cancel_control")
        self.assertEqual(normalized, "do not send")

    def test_classify_dismiss(self) -> None:
        kind, normalized = classify_control_intent("Dismiss this")
        self.assertEqual(kind, "dismiss_control")
        self.assertEqual(normalized, "dismiss this")

    def test_classify_dismissed_variant(self) -> None:
        kind, normalized = classify_control_intent("Dismissed.")
        self.assertEqual(kind, "dismiss_control")
        self.assertEqual(normalized, "dismissed")

    def test_classify_affirmative(self) -> None:
        kind, _ = classify_control_intent("Sure, we can do that.")
        self.assertEqual(kind, "affirmative_short")

    def test_trim_stt_noise_prefix_removes_short_prefix_before_send(self) -> None:
        trimmed = trim_stt_noise_prefix("The end Send an email to Danko")
        self.assertEqual(trimmed, "Send an email to Danko")

    def test_trim_stt_noise_prefix_removes_short_prefix_before_cancel(self) -> None:
        trimmed = trim_stt_noise_prefix("for you Cancel.")
        self.assertEqual(trimmed, "Cancel.")

    def test_trim_stt_noise_prefix_removes_hey_prefix_before_send(self) -> None:
        trimmed = trim_stt_noise_prefix("\"Hey, Send an email to Danko")
        self.assertEqual(trimmed, "Send an email to Danko")

    def test_trim_stt_noise_prefix_keeps_regular_sentence(self) -> None:
        trimmed = trim_stt_noise_prefix("Please send an email to Danko")
        self.assertEqual(trimmed, "Please send an email to Danko")


if __name__ == "__main__":
    unittest.main()
