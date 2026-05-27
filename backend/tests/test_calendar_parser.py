import unittest
from unittest.mock import AsyncMock, patch

from app.services.calendar.parser import parse_calendar_user_action


class CalendarParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_calendar_user_action_returns_none_for_non_calendar_request(self) -> None:
        db = AsyncMock()
        fake_config = type("Cfg", (), {"model": "gpt-5.4-mini", "base_url": "https://api.openai.com/v1", "api_key": "x", "provider": "openai"})()

        with (
            patch("app.services.calendar.parser.get_llm_config", new=AsyncMock(return_value=fake_config)),
            patch("app.services.calendar.parser._llm_parse_calendar_user_action", new=AsyncMock(side_effect=TimeoutError("timeout"))),
        ):
            parsed = await parse_calendar_user_action(db, "reply that I can make it")

        self.assertEqual(parsed.action, "none")
        self.assertIn("fallback:not_calendar_candidate", parsed.reasoning)

    async def test_parse_calendar_user_action_uses_llm_for_calendar_candidate(self) -> None:
        db = AsyncMock()
        fake_config = type("Cfg", (), {"model": "gpt-5.4-mini", "base_url": "https://api.openai.com/v1", "api_key": "x", "provider": "openai"})()
        fake_parsed = type(
            "Parsed",
            (),
            {
                "action": "create_event",
                "title": "Meeting with Danko",
                "attendee_queries": ["Danko"],
                "desired_start_at": None,
                "duration_minutes": 60,
                "reasoning": "llm:test",
                "usage": None,
            },
        )()

        with (
            patch("app.services.calendar.parser.get_llm_config", new=AsyncMock(return_value=fake_config)),
            patch("app.services.calendar.parser._llm_parse_calendar_user_action", new=AsyncMock(return_value=fake_parsed)) as llm_mock,
        ):
            parsed = await parse_calendar_user_action(db, "set up a meeting with Danko tomorrow at 2 pm")

        self.assertEqual(parsed.action, "create_event")
        llm_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()