import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

from app.services.email import contacts as email_contacts
from app.services.email.commands import handle_email_command_from_transcript
from app.services.email.draft_commands import handle_email_draft_command_from_transcript
from app.services.email.parser import ParsedEmailAction, parse_email_user_action
from app.services.calendar import commands as calendar_commands
from app.services.email import draft_runtime
from app.services.followups import commands as followup_commands
from app.services.followups import lifecycle as followups_lifecycle
from app.integrations.gmail import oauth as gmail_oauth
from app.services.shared.notification_content import (
    build_follow_up_notification_details,
    build_new_email_notification_details,
)
from app.services.shared import notifications as notification_service
from app.services.shared import preferences


class ServiceQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_followup_by_id_returns_none_when_missing(self) -> None:
        db = AsyncMock()
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute.return_value = execute_result

        item = await followups_lifecycle.get_followup_by_id(db, follow_up_id="missing")

        self.assertIsNone(item)
        db.execute.assert_awaited_once()

    async def test_get_draft_by_id_returns_none_when_missing(self) -> None:
        db = AsyncMock()
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute.return_value = execute_result

        draft = await draft_runtime.get_draft_by_id(db, "missing")

        self.assertIsNone(draft)
        db.execute.assert_awaited_once()

    async def test_update_settings_stores_gmail_secret_outside_settings_payload(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {}
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        with patch("app.services.shared.preferences.set_secret") as set_secret_mock:
            updated = await preferences.update_settings(
                db,
                enable_transcription_trace=False,
                enable_text_input_mode=False,
                email_sync_interval_minutes=5,
                app_api_base_url="http://127.0.0.1:8000",
                app_ws_url="ws://127.0.0.1:8000/ws",
                email_provider="gmail",
                m365_client_id="",
                m365_tenant_id="",
                m365_redirect_url="http://localhost:8000/api/oauth/callback",
                gmail_client_id="gmail-client-id",
                gmail_client_secret="super-secret-value",
                gmail_redirect_url="http://localhost:8000/api/oauth/google/callback",
                speech_provider="openai",
                speech_model="",
                speech_base_url="https://api.openai.com/v1",
                speech_api_key=None,
                llm_provider="openai",
                llm_model="",
                llm_base_url="https://api.openai.com/v1",
                llm_api_key=None,
            )

        self.assertNotIn("gmail_client_secret", record.value)
        self.assertNotIn("gmail_client_secret", updated)
        self.assertTrue(updated["gmail_client_secret_configured"])
        set_secret_mock.assert_called_once_with("gmail_client_secret", "super-secret-value")

    async def test_update_settings_defaults_empty_speech_model_to_whisper(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {}
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        updated = await preferences.update_settings(
            db,
            enable_transcription_trace=False,
            enable_text_input_mode=False,
            email_sync_interval_minutes=5,
            app_api_base_url="http://127.0.0.1:8000",
            app_ws_url="ws://127.0.0.1:8000/ws",
            email_provider="gmail",
            m365_client_id="",
            m365_tenant_id="",
            m365_redirect_url="http://localhost:8000/api/oauth/callback",
            gmail_client_id="gmail-client-id",
            gmail_client_secret=None,
            gmail_redirect_url="http://localhost:8000/api/oauth/google/callback",
            speech_provider="openai",
            speech_model="",
            speech_base_url="https://api.openai.com/v1",
            speech_api_key=None,
            llm_provider="openai",
            llm_model="",
            llm_base_url="https://api.openai.com/v1",
            llm_api_key=None,
        )

        self.assertEqual(record.value["speech_model"], "whisper-1")
        self.assertEqual(updated["speech_model"], "whisper-1")

    async def test_get_settings_defaults_empty_persisted_speech_model_to_whisper(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {
            "speech_provider": "openai",
            "speech_model": "   ",
            "speech_base_url": "https://api.openai.com/v1",
        }
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        settings = await preferences.get_settings(db)

        self.assertEqual(settings["speech_model"], "whisper-1")

    async def test_get_settings_hides_legacy_gmail_secret_and_marks_configured(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {
            "gmail_client_id": "gmail-client-id",
            "gmail_client_secret": "legacy-secret",
            "gmail_redirect_url": "http://localhost:8000/api/oauth/google/callback",
        }
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        with patch("app.services.shared.preferences.set_secret") as set_secret_mock:
            settings = await preferences.get_settings(db)

        self.assertNotIn("gmail_client_secret", settings)
        self.assertTrue(settings["gmail_client_secret_configured"])
        set_secret_mock.assert_called_once_with("gmail_client_secret", "legacy-secret")

    async def test_get_settings_does_not_trust_persisted_gmail_secret_flag_without_secret(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {
            "gmail_client_id": "gmail-client-id",
            "gmail_redirect_url": "http://localhost:8000/api/oauth/google/callback",
            "gmail_client_secret_configured": True,
        }
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        with patch("app.services.shared.preferences.get_secret", return_value=None):
            settings = await preferences.get_settings(db)

        self.assertFalse(settings["gmail_client_secret_configured"])

    async def test_gmail_token_persistence_reports_session_for_in_memory_secret(self) -> None:
        with patch("app.integrations.gmail.oauth.get_secret_persistence", return_value="session"):
            self.assertEqual(gmail_oauth.get_token_persistence(), "session")

    def test_gmail_pending_auth_flows_prunes_expired_entries(self) -> None:
        gmail_oauth._pending_auth_flows.clear()
        flow = gmail_oauth._PendingAuthFlow(code_verifier="verifier", redirect_uri="http://localhost/callback")
        gmail_oauth._pending_auth_flows["expired"] = (flow, 100.0)

        with patch("app.integrations.gmail.oauth.time.monotonic", return_value=100.0 + gmail_oauth._PENDING_AUTH_FLOW_TTL_SECONDS + 1):
            gmail_oauth._prune_pending_auth_flows()

        self.assertNotIn("expired", gmail_oauth._pending_auth_flows)

    def test_gmail_pending_auth_flows_prunes_oldest_when_over_capacity(self) -> None:
        gmail_oauth._pending_auth_flows.clear()
        max_flows = gmail_oauth._MAX_PENDING_AUTH_FLOWS
        flow = gmail_oauth._PendingAuthFlow(code_verifier="verifier", redirect_uri="http://localhost/callback")
        for idx in range(max_flows + 3):
            gmail_oauth._pending_auth_flows[f"state-{idx}"] = (flow, float(idx))

        with patch("app.integrations.gmail.oauth.time.monotonic", return_value=0.0):
            gmail_oauth._prune_pending_auth_flows()

        self.assertEqual(len(gmail_oauth._pending_auth_flows), max_flows)
        self.assertNotIn("state-0", gmail_oauth._pending_auth_flows)
        self.assertNotIn("state-1", gmail_oauth._pending_auth_flows)
        self.assertNotIn("state-2", gmail_oauth._pending_auth_flows)

    async def test_get_settings_does_not_trust_persisted_ai_secret_flags_without_secrets(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {
            "speech_provider": "openai",
            "llm_provider": "openai",
            "speech_api_key_configured": True,
            "llm_api_key_configured": True,
        }
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        with patch("app.services.shared.preferences.get_secret", return_value=None), patch(
            "app.services.shared.preferences._default_api_key",
            return_value="",
        ):
            settings = await preferences.get_settings(db)

        self.assertFalse(settings["speech_api_key_configured"])
        self.assertFalse(settings["llm_api_key_configured"])
        self.assertNotIn("speech_api_key_configured", record.value)
        self.assertNotIn("llm_api_key_configured", record.value)

    async def test_clear_ai_secrets_returns_decorated_settings_without_crashing(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {
            "speech_provider": "openai",
            "llm_provider": "openai",
        }
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        with patch("app.services.shared.preferences.get_secret", return_value=None), patch(
            "app.services.shared.preferences._default_api_key",
            return_value="",
        ):
            settings = await preferences.clear_ai_secrets(db)

        self.assertFalse(settings["speech_api_key_configured"])
        self.assertFalse(settings["llm_api_key_configured"])

    async def test_update_settings_rejects_insecure_remote_api_base_url(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {}
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        with self.assertRaisesRegex(ValueError, "https://"):
            await preferences.update_settings(
                db,
                enable_transcription_trace=False,
                enable_text_input_mode=False,
                email_sync_interval_minutes=5,
                app_api_base_url="http://example.com",
                app_ws_url="",
                email_provider="m365",
                m365_client_id="",
                m365_tenant_id="",
                m365_redirect_url="http://localhost:8000/api/oauth/callback",
                gmail_client_id="",
                gmail_client_secret=None,
                gmail_redirect_url="http://localhost:8000/api/oauth/google/callback",
                speech_provider="openai",
                speech_model="",
                speech_base_url="https://api.openai.com/v1",
                speech_api_key=None,
                llm_provider="openai",
                llm_model="",
                llm_base_url="https://api.openai.com/v1",
                llm_api_key=None,
            )

    async def test_update_settings_allows_dns_resolved_loopback_api_host(self) -> None:
        db = AsyncMock()
        record = Mock()
        record.value = {}
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = record
        db.execute.return_value = execute_result

        loopback_lookup = (
            (None, None, None, None, ("127.0.0.1", 0)),
        )

        with patch("app.core.url_validation.socket.getaddrinfo", return_value=loopback_lookup):
            updated = await preferences.update_settings(
                db,
                enable_transcription_trace=False,
                enable_text_input_mode=False,
                email_sync_interval_minutes=5,
                app_api_base_url="http://dev.local:8000",
                app_ws_url="",
                email_provider="m365",
                m365_client_id="",
                m365_tenant_id="",
                m365_redirect_url="http://localhost:8000/api/oauth/callback",
                gmail_client_id="",
                gmail_client_secret=None,
                gmail_redirect_url="http://localhost:8000/api/oauth/google/callback",
                speech_provider="openai",
                speech_model="",
                speech_base_url="https://api.openai.com/v1",
                speech_api_key=None,
                llm_provider="openai",
                llm_model="",
                llm_base_url="https://api.openai.com/v1",
                llm_api_key=None,
            )

        self.assertEqual(updated["app_api_base_url"], "http://dev.local:8000")
        self.assertEqual(updated["app_ws_url"], "ws://dev.local:8000/ws")

    async def test_follow_up_parse_failure_returns_noop_feedback(self) -> None:
        db = AsyncMock()

        with (
            patch("app.services.followups.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.followups.commands.parse_follow_up_user_action", new=AsyncMock(side_effect=ValueError("bad parse"))),
        ):
            outcome = await followup_commands.handle_follow_up_command_from_transcript(
                db,
                notification_id="notif-1",
                transcript_text="remind me maybe later",
                correlation_id="corr-1",
            )

        self.assertIsNone(outcome.result)
        self.assertEqual(outcome.display_text, "I couldn't understand that follow-up command. Please try again.")
        self.assertIsNone(outcome.interaction.dismiss_notification_id)
        self.assertFalse(outcome.interaction.close_window)

    async def test_new_email_name_recipient_keeps_contact_suggestions(self) -> None:
        db = AsyncMock()

        parsed = ParsedEmailAction(
            action="new_email",
            recipient="Danko",
            subject_hint=None,
            message_instructions="Send an email to Danko",
            reasoning="test",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Quick update", body="Hello", usage=None)
        created_draft = SimpleNamespace(
            id="draft-1",
            recipient_email=None,
            suggestions=[
                SimpleNamespace(email="danko@example.com"),
                SimpleNamespace(email="danko.work@example.com"),
            ],
        )
        created_notification = SimpleNamespace(id="notif-1")
        candidates = [
            SimpleNamespace(email="danko@example.com", label="Danko", confidence=0.82, source="graph"),
            SimpleNamespace(email="danko.work@example.com", label="Danko Work", confidence=0.79, source="local"),
        ]

        with (
            patch("app.services.email.commands._resolve_context", new=AsyncMock(return_value=None)),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed)),
            patch("app.services.email.commands.resolve_contact_candidates", new=AsyncMock(return_value=candidates)) as resolve_candidates_mock,
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)) as create_draft_mock,
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)) as create_notification_mock,
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="send an email to Danko",
                correlation_id="corr-1",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        resolve_candidates_mock.assert_awaited_once_with(db, raw_query="Danko")
        create_draft_mock.assert_awaited_once()
        self.assertIsNone(create_draft_mock.await_args.kwargs["recipient_email"])
        self.assertEqual(
            create_draft_mock.await_args.kwargs["suggestions"],
            [
                {
                    "email": "danko@example.com",
                    "label": "Danko",
                    "confidence": 0.82,
                    "source": "graph",
                },
                {
                    "email": "danko.work@example.com",
                    "label": "Danko Work",
                    "confidence": 0.79,
                    "source": "local",
                },
            ],
        )
        create_notification_mock.assert_awaited_once()
        self.assertEqual(
            create_notification_mock.await_args.kwargs["message"],
            "Email draft for (recipient required) [draft:draft-1]",
        )
        self.assertEqual(
            create_notification_mock.await_args.kwargs["details"],
            {
                "kind": "email_draft",
                "variant": "default",
                "headline": "Email draft needs a recipient",
                "instruction": "Review the draft, then say 'send it' or 'cancel draft'.",
            },
        )

    async def test_meeting_reply_accept_prepares_email_and_calendar(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-1",
            conversation_id="conv-1",
            from_address="alex@example.com",
            from_name="Alex",
            subject="Meeting tomorrow at 10",
            body_preview="Can you do tomorrow at 10am for 30 minutes?",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Meeting tomorrow at 10", body="Sure, works for me.", usage=None)
        created_draft = SimpleNamespace(id="draft-accept-1", recipient_email="alex@example.com")
        created_notification = SimpleNamespace(id="notif-draft-accept-1")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-1",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-1",
                transcript_text="sure",
                correlation_id="corr-meeting-accept-1",
            )

        self.assertEqual(outcome.result, "email_and_calendar_ready")
        self.assertIn("meeting proposal", (outcome.display_text or "").lower())
        calendar_mock.assert_awaited_once()

    async def test_email_draft_cancel_falls_back_to_draft_notification(self) -> None:
        db = AsyncMock()
        draft = SimpleNamespace(
            id="draft-cancel-1",
            status="pending",
            send_notification_id="notif-draft-cancel-1",
            source_notification_id="notif-source-1",
            recipient_email="alex@example.com",
        )

        with (
            patch("app.services.email.draft_commands.classify_control_intent", return_value=("cancel_control", "cancel")),
            patch("app.services.email.draft_commands.draft_runtime.cancel_draft", new=AsyncMock(return_value=draft)) as cancel_mock,
        ):
            outcome = await handle_email_draft_command_from_transcript(
                db,
                draft_id="draft-cancel-1",
                transcript_text="cancel",
                notification_id=None,
            )

        self.assertEqual(outcome.result, "email_draft_canceled")
        self.assertEqual(outcome.interaction.dismiss_notification_id, "notif-draft-cancel-1")
        cancel_mock.assert_awaited_once_with(db, draft_id="draft-cancel-1")

    async def test_meeting_reply_decline_prepares_email_only_without_calendar(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-2",
            conversation_id="conv-2",
            from_address="alex@example.com",
            from_name="Alex",
            subject="Meeting tomorrow at 10",
            body_preview="Can you do tomorrow at 10am?",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Meeting tomorrow at 10", body="Sorry, I can't make that time.", usage=None)
        created_draft = SimpleNamespace(id="draft-decline-1", recipient_email="alex@example.com")
        created_notification = SimpleNamespace(id="notif-draft-decline-1")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-2",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-2",
                transcript_text="no",
                correlation_id="corr-meeting-decline-1",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        calendar_mock.assert_not_awaited()

    async def test_meeting_reply_counter_offer_prepares_email_and_calendar(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-3",
            conversation_id="conv-3",
            from_address="alex@example.com",
            from_name="Alex",
            subject="Meeting tomorrow at 10",
            body_preview="Can you do tomorrow at 10am?",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Meeting tomorrow at 10", body="Can't at 10, day after at 3 works.", usage=None)
        created_draft = SimpleNamespace(id="draft-counter-1", recipient_email="alex@example.com")
        created_notification = SimpleNamespace(id="notif-draft-counter-1")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-3",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-3",
                transcript_text="can't at 10, but the day after at 3 is fine",
                correlation_id="corr-meeting-counter-1",
            )

        self.assertEqual(outcome.result, "email_and_calendar_ready")
        calendar_mock.assert_awaited_once()
        calendar_call_text = calendar_mock.await_args.kwargs["transcript_text"]
        self.assertIn("alex@example.com", calendar_call_text)

    async def test_meeting_reply_send_me_invite_prepares_email_only(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-4",
            conversation_id="conv-4",
            from_address="alex@example.com",
            from_name="Alex",
            subject="Meeting tomorrow at 10",
            body_preview="Can you do tomorrow at 10am for 30 minutes?",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Meeting tomorrow at 10", body="Sure, send me an invite.", usage=None)
        created_draft = SimpleNamespace(id="draft-delegate-1", recipient_email="alex@example.com")
        created_notification = SimpleNamespace(id="notif-draft-delegate-1")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-4",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-4",
                transcript_text="sure, send me an invite",
                correlation_id="corr-meeting-delegate-1",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        calendar_mock.assert_not_awaited()

    async def test_meeting_reply_counter_offer_with_filler_words_prepares_email_and_calendar(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-5",
            conversation_id="conv-5",
            from_address="danko.mihalic@gmail.com",
            from_name="Danko",
            subject="Friday at 10:30",
            body_preview="Reply to confirm whether Friday at 10:30 works.",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Friday at 10:30", body="No, let's make it eleven.", usage=None)
        created_draft = SimpleNamespace(id="draft-counter-2", recipient_email="danko.mihalic@gmail.com")
        created_notification = SimpleNamespace(id="notif-draft-counter-2")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-5",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-5",
                transcript_text="Um no let's Let's make it eleven",
                correlation_id="corr-meeting-counter-2",
            )

        self.assertEqual(outcome.result, "email_and_calendar_ready")
        calendar_mock.assert_awaited_once()

    async def test_meeting_reply_counter_offer_with_spoken_half_hour_prepares_email_and_calendar(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-6",
            conversation_id="conv-6",
            from_address="danko.mihalic@gmail.com",
            from_name="Danko",
            subject="Friday at 10:30",
            body_preview="Reply to confirm whether Friday at 10:30 works.",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Friday at 10:30", body="No, let's make it eleven thirty.", usage=None)
        created_draft = SimpleNamespace(id="draft-counter-3", recipient_email="danko.mihalic@gmail.com")
        created_notification = SimpleNamespace(id="notif-draft-counter-3")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-6",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-6",
                transcript_text="Um no let's make it eleven thirty",
                correlation_id="corr-meeting-counter-3",
            )

        self.assertEqual(outcome.result, "email_and_calendar_ready")
        calendar_mock.assert_awaited_once()

    async def test_meeting_reply_counter_offer_with_asr_i_think_its_phrase_prepares_email_and_calendar(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-7",
            conversation_id="conv-7",
            from_address="danko.mihalic@gmail.com",
            from_name="Danko",
            subject="Friday at 10:30",
            body_preview="Reply to confirm whether Friday at 10:30 works.",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: Friday at 10:30", body="Let's make it three.", usage=None)
        created_draft = SimpleNamespace(id="draft-counter-4", recipient_email="danko.mihalic@gmail.com")
        created_notification = SimpleNamespace(id="notif-draft-counter-4")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-7",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-7",
                transcript_text="Let's make I think it's three.",
                correlation_id="corr-meeting-counter-4",
            )

        self.assertEqual(outcome.result, "email_and_calendar_ready")
        calendar_mock.assert_awaited_once()

    async def test_meeting_reply_counter_offer_with_unusable_asr_garble_does_not_create_calendar_for_original_slot(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-8",
            conversation_id="conv-8",
            from_address="danko.mihalic@gmail.com",
            from_name="Danko Mihalic",
            subject="third time's the charm",
            body_preview="let's meet friday 1pm?",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: third time's the charm", body="Let's make it Den r.", usage=None)
        created_draft = SimpleNamespace(id="draft-counter-5", recipient_email="danko.mihalic@gmail.com")
        created_notification = SimpleNamespace(id="notif-draft-counter-5")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-8",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-8",
                transcript_text="Let's make it Den r",
                correlation_id="corr-meeting-counter-5",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        calendar_mock.assert_not_awaited()

    async def test_meeting_reply_counter_offer_recovers_den_ar_as_ten_and_adds_sender_email(self) -> None:
        db = AsyncMock()
        context_email = SimpleNamespace(
            id="email-9",
            conversation_id="conv-9",
            from_address="danko.mihalic@gmail.com",
            from_name="Danko Mihalic",
            subject="third time's the charm",
            body_preview="let's meet friday 1pm?",
        )

        parsed_none = ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="llm:none",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Re: third time's the charm", body="Let's make it ten.", usage=None)
        created_draft = SimpleNamespace(id="draft-counter-6", recipient_email="danko.mihalic@gmail.com")
        created_notification = SimpleNamespace(id="notif-draft-counter-6")

        with (
            patch(
                "app.services.email.commands._resolve_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        resolved_notification_id="notif-ctx-9",
                        follow_up_id=None,
                        email_item=context_email,
                    )
                ),
            ),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed_none)),
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)),
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
            patch(
                "app.services.calendar.commands.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id="notif-ctx-9",
                transcript_text="Let's make it Den är",
                correlation_id="corr-meeting-counter-6",
            )

        self.assertEqual(outcome.result, "email_and_calendar_ready")
        calendar_mock.assert_awaited_once()
        calendar_call_text = calendar_mock.await_args.kwargs["transcript_text"]
        self.assertIn("danko.mihalic@gmail.com", calendar_call_text)
        self.assertIn("ten am", calendar_call_text.lower())
        self.assertIn("requested new time", calendar_call_text.lower())

    async def test_calendar_command_extracted_email_from_utterance_is_used_for_attendees(self) -> None:
        db = AsyncMock()
        fake_provider = SimpleNamespace()
        parsed = calendar_commands.ParsedCalendarAction(
            action="create_event",
            title="Meeting with Danko",
            attendee_queries=["Danko Mihalic"],
            desired_start_at=datetime.now().astimezone() + timedelta(days=1),
            duration_minutes=30,
            reasoning="llm:test",
            usage=None,
        )

        with (
            patch(
                "app.services.calendar.commands.get_llm_config",
                new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini")),
            ),
            patch(
                "app.services.calendar.commands.parse_calendar_user_action",
                new=AsyncMock(return_value=parsed),
            ),
            patch("app.services.calendar.commands._get_calendar_provider", new=AsyncMock(return_value=fake_provider)),
            patch(
                "app.services.calendar.commands._resolve_attendee_emails",
                new=AsyncMock(return_value=calendar_commands.CalendarAttendeeResolution(emails=["danko@example.com"], suggestions=[])),
            ) as resolve_mock,
            patch(
                "app.services.calendar.commands.planner.plan_calendar_proposal",
                new=AsyncMock(return_value=SimpleNamespace(proposal=SimpleNamespace(id="proposal-email-merge"))),
            ),
        ):
            outcome = await calendar_commands.handle_calendar_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="Schedule a meeting with Danko Mihalic <danko.mihalic@gmail.com> tomorrow at 10 am",
                correlation_id="corr-cal-email-merge",
            )

        self.assertEqual(outcome.result, "calendar_proposal_ready")
        resolve_mock.assert_awaited_once()
        self.assertIn("danko.mihalic@gmail.com", resolve_mock.await_args.args[1])

    def test_new_email_notification_details_use_default_instruction_without_followup(self) -> None:
        details = build_new_email_notification_details(
            from_email="ceo@example.com",
            subject="Quarterly update",
            body_preview="Please review the attached quarterly numbers.",
        )

        self.assertEqual(details["variant"], "default")
        self.assertEqual(details["headline"], "New email from ceo@example.com")
        self.assertEqual(details["instruction"], "Say 'summarize this' or 'reply'.")
        self.assertEqual(details["body_preview"], "Please review the attached quarterly numbers.")
        self.assertEqual(details["original_email_text"], "Please review the attached quarterly numbers.")

    def test_new_email_notification_details_use_followup_variant_when_detected(self) -> None:
        details = build_new_email_notification_details(
            from_email="ceo@example.com",
            subject="Need an answer by Friday",
            followup_id="fu-1",
            followup_summary="Confirm delivery date by Friday.",
        )

        self.assertEqual(details["variant"], "followup_detected")
        self.assertEqual(
            details["instruction"],
            "Follow-up may be needed. Say 'summarize this' or 'reply'.",
        )

    def test_follow_up_notification_details_include_summary_context(self) -> None:
        details = build_follow_up_notification_details(summary="Confirm delivery date by Friday.")

        self.assertEqual(details["kind"], "follow_up_reminder")
        self.assertEqual(details["headline"], "Follow-up reminder")
        self.assertEqual(details["context_line"], "Confirm delivery date by Friday.")
        self.assertEqual(
            details["instruction"],
            "Say 'complete', 'dismiss', or 'remind me tomorrow'.",
        )

    def test_notification_usage_aggregation_includes_source_email_only_rows(self) -> None:
        usage = notification_service._aggregate_usage_for_notification(
            [
                ("usage-email", None, "email-1", 11, 7, 18),
            ],
            notification_ids=["notif-1"],
            source_email_id="email-1",
        )

        self.assertEqual(usage["prompt_tokens"], 11)
        self.assertEqual(usage["completion_tokens"], 7)
        self.assertEqual(usage["total_tokens"], 18)

    def test_notification_usage_aggregation_excludes_other_notification_rows_sharing_email(self) -> None:
        usage = notification_service._aggregate_usage_for_notification(
            [
                ("usage-linked", "notif-2", "email-1", 20, 10, 30),
                ("usage-email-only", None, "email-1", 3, 2, 5),
            ],
            notification_ids=["notif-1"],
            source_email_id="email-1",
        )

        self.assertEqual(usage["prompt_tokens"], 3)
        self.assertEqual(usage["completion_tokens"], 2)
        self.assertEqual(usage["total_tokens"], 5)

    async def test_new_email_heuristic_extracts_name_before_message_clause(self) -> None:
        db = AsyncMock()

        drafted = SimpleNamespace(subject="Quick update", body="Hello", usage=None)
        created_draft = SimpleNamespace(
            id="draft-1",
            recipient_email=None,
            suggestions=[
                SimpleNamespace(email="danko@example.com"),
                SimpleNamespace(email="danko.work@example.com"),
            ],
        )
        created_notification = SimpleNamespace(id="notif-1")
        candidates = [
            SimpleNamespace(email="danko@example.com", label="Danko", confidence=0.82, source="graph"),
            SimpleNamespace(email="danko.work@example.com", label="Danko Work", confidence=0.79, source="local"),
        ]

        with (
            patch("app.services.email.commands._resolve_context", new=AsyncMock(return_value=None)),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch(
                "app.services.email.commands.parse_email_user_action",
                new=AsyncMock(
                    return_value=ParsedEmailAction(
                        action="new_email",
                        recipient="Danko",
                        subject_hint=None,
                        message_instructions="send an email to Danko that I accept the offer",
                        reasoning="heuristic:new_email_keyword",
                        usage=None,
                    )
                ),
            ),
            patch("app.services.email.commands.resolve_contact_candidates", new=AsyncMock(return_value=candidates)) as resolve_candidates_mock,
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)) as create_draft_mock,
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="send an email to Danko that I accept the offer",
                correlation_id="corr-2",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        resolve_candidates_mock.assert_awaited_once_with(db, raw_query="Danko")
        self.assertIsNone(create_draft_mock.await_args.kwargs["recipient_email"])

    async def test_parse_email_user_action_ignores_obvious_calendar_request(self) -> None:
        db = AsyncMock()
        fake_config = SimpleNamespace(provider="openai", model="gpt-5.4-mini", base_url="https://api.openai.com/v1", api_key="x")

        with (
            patch("app.services.email.parser.get_llm_config", new=AsyncMock(return_value=fake_config)),
            patch("app.services.email.parser._llm_parse", new=AsyncMock(side_effect=TimeoutError("timeout"))),
        ):
            parsed = await parse_email_user_action(
                db,
                utterance="make a meeting with Danko tomorrow at two pm",
                context=SimpleNamespace(),
            )

        self.assertEqual(parsed.action, "none")
        self.assertEqual(parsed.reasoning, "heuristic:calendar_intent_not_email")

    async def test_calendar_command_from_transcript_creates_proposal(self) -> None:
        db = AsyncMock()
        fake_provider = SimpleNamespace()

        with (
            patch(
                "app.services.calendar.commands.get_llm_config",
                new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini")),
            ),
            patch(
                "app.services.calendar.commands.parse_calendar_user_action",
                new=AsyncMock(
                    return_value=calendar_commands.ParsedCalendarAction(
                        action="create_event",
                        title="Meeting with Danko",
                        attendee_queries=["Danko"],
                        desired_start_at=datetime.now().astimezone() + timedelta(days=1),
                        duration_minutes=60,
                        reasoning="llm:test",
                        usage=None,
                    )
                ),
            ),
            patch("app.services.calendar.commands._get_calendar_provider", new=AsyncMock(return_value=fake_provider)),
            patch(
                "app.services.calendar.commands._resolve_attendee_emails",
                new=AsyncMock(
                    return_value=calendar_commands.CalendarAttendeeResolution(
                        emails=["danko@example.com"],
                        suggestions=[],
                    )
                ),
            ),
            patch(
                "app.services.calendar.commands.planner.plan_calendar_proposal",
                new=AsyncMock(return_value=SimpleNamespace(proposal=SimpleNamespace(id="proposal-1"))),
            ) as plan_mock,
        ):
            outcome = await calendar_commands.handle_calendar_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="Make a meeting with Danko tomorrow at 2 PM",
                correlation_id="corr-cal-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_ready")
        self.assertIn("Meeting plan prepared", outcome.display_text)
        payload = plan_mock.await_args.kwargs["payload"]
        self.assertEqual(payload.action, "create_event")
        self.assertEqual(payload.title, "Meeting with Danko")
        self.assertEqual(payload.attendees, ["danko@example.com"])
        self.assertFalse(payload.auto_shift_conflict_free_for_flexible_time)
        self.assertEqual(plan_mock.await_args.kwargs["attendee_suggestions"], [])

    async def test_calendar_command_from_transcript_marks_flexible_time_for_auto_shift(self) -> None:
        db = AsyncMock()
        fake_provider = SimpleNamespace()

        with (
            patch(
                "app.services.calendar.commands.get_llm_config",
                new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini")),
            ),
            patch(
                "app.services.calendar.commands.parse_calendar_user_action",
                new=AsyncMock(
                    return_value=calendar_commands.ParsedCalendarAction(
                        action="create_event",
                        title="Meeting with Dan",
                        attendee_queries=["Dan"],
                        desired_start_at=datetime.now().astimezone() + timedelta(days=1),
                        duration_minutes=60,
                        reasoning="llm:test",
                        usage=None,
                    )
                ),
            ),
            patch("app.services.calendar.commands._get_calendar_provider", new=AsyncMock(return_value=fake_provider)),
            patch(
                "app.services.calendar.commands._resolve_attendee_emails",
                new=AsyncMock(
                    return_value=calendar_commands.CalendarAttendeeResolution(
                        emails=["dan@example.com"],
                        suggestions=[],
                    )
                ),
            ),
            patch(
                "app.services.calendar.commands.planner.plan_calendar_proposal",
                new=AsyncMock(return_value=SimpleNamespace(proposal=SimpleNamespace(id="proposal-2"))),
            ) as plan_mock,
        ):
            outcome = await calendar_commands.handle_calendar_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="Make a meeting with Dan tomorrow morning",
                correlation_id="corr-cal-flex-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_ready")
        payload = plan_mock.await_args.kwargs["payload"]
        self.assertTrue(payload.auto_shift_conflict_free_for_flexible_time)

    def test_command_from_parsed_action_defaults_duration_to_30_minutes(self) -> None:
        parsed = calendar_commands.ParsedCalendarAction(
            action="create_event",
            title="Meeting",
            attendee_queries=[],
            desired_start_at=datetime.now().astimezone(),
            duration_minutes=None,
            reasoning="llm:test",
            usage=None,
        )

        command = calendar_commands._command_from_parsed_action(parsed)

        self.assertIsNotNone(command)
        self.assertEqual(command.duration_minutes, 30)

    async def test_calendar_command_from_transcript_returns_noop_for_non_calendar_request(self) -> None:
        db = AsyncMock()

        with (
            patch(
                "app.services.calendar.commands.get_llm_config",
                new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini")),
            ),
            patch(
                "app.services.calendar.commands.parse_calendar_user_action",
                new=AsyncMock(
                    return_value=calendar_commands.ParsedCalendarAction(
                        action="none",
                        title="",
                        attendee_queries=[],
                        desired_start_at=None,
                        duration_minutes=None,
                        reasoning="llm:none",
                        usage=None,
                    )
                ),
            ),
        ):
            outcome = await calendar_commands.handle_calendar_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="reply that I am available",
                correlation_id="corr-cal-2",
            )

        self.assertIsNone(outcome.result)

    async def test_calendar_command_from_transcript_records_parse_usage(self) -> None:
        db = AsyncMock()
        fake_provider = SimpleNamespace()
        fake_usage = SimpleNamespace(prompt_tokens=12, completion_tokens=8, total_tokens=20)

        with (
            patch(
                "app.services.calendar.commands.get_llm_config",
                new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini")),
            ),
            patch(
                "app.services.calendar.commands.parse_calendar_user_action",
                new=AsyncMock(
                    return_value=calendar_commands.ParsedCalendarAction(
                        action="create_event",
                        title="Meeting with Danko",
                        attendee_queries=["Danko"],
                        desired_start_at=datetime.now().astimezone() + timedelta(days=1),
                        duration_minutes=60,
                        reasoning="llm:test",
                        usage=fake_usage,
                    )
                ),
            ),
            patch("app.services.calendar.commands.record_llm_usage", new=AsyncMock()) as record_usage_mock,
            patch("app.services.calendar.commands._get_calendar_provider", new=AsyncMock(return_value=fake_provider)),
            patch(
                "app.services.calendar.commands._resolve_attendee_emails",
                new=AsyncMock(
                    return_value=calendar_commands.CalendarAttendeeResolution(
                        emails=["danko@example.com"],
                        suggestions=[],
                    )
                ),
            ),
            patch(
                "app.services.calendar.commands.planner.plan_calendar_proposal",
                new=AsyncMock(return_value=SimpleNamespace(proposal=SimpleNamespace(id="proposal-1"))),
            ),
        ):
            outcome = await calendar_commands.handle_calendar_command_from_transcript(
                db,
                notification_id="notif-1",
                transcript_text="Make a meeting with Danko tomorrow at 2 PM",
                correlation_id="corr-cal-usage",
            )

        self.assertEqual(outcome.result, "calendar_proposal_ready")
        record_usage_mock.assert_awaited_once()
        self.assertEqual(record_usage_mock.await_args.kwargs["interaction_kind"], "calendar_command_parse")
        self.assertEqual(record_usage_mock.await_args.kwargs["notification_id"], "notif-1")

    async def test_resolve_contact_candidates_preserves_provider_name_query(self) -> None:
        db = AsyncMock()

        with (
            patch("app.services.email.contacts._local_candidates", new=AsyncMock(return_value=[])) as local_mock,
            patch("app.services.email.contacts._graph_candidates", new=AsyncMock(return_value=[])) as graph_mock,
        ):
            await email_contacts.resolve_contact_candidates(db, raw_query="Kristýna")

        local_mock.assert_awaited_once_with(db, "kristyna")
        graph_mock.assert_awaited_once_with(db, "Kristýna")

    async def test_local_contact_candidates_match_sender_display_name(self) -> None:
        db = AsyncMock()
        execute_result = Mock()
        execute_result.all.return_value = [
            ("person@email.com", "Danko Founder"),
            ("other@email.com", "Someone Else"),
        ]
        db.execute.return_value = execute_result

        candidates = await email_contacts._local_candidates(db, "danko")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].email, "person@email.com")
        self.assertEqual(candidates[0].label, "Danko Founder")

    async def test_calendar_attendee_resolution_recovers_from_noisy_phrase(self) -> None:
        db = AsyncMock()
        noisy_candidates: list = []
        token_candidates = [
            email_contacts.ContactCandidate(
                email="danko@example.com",
                label="Danko",
                confidence=0.86,
                source="graph",
            )
        ]

        with patch(
            "app.services.calendar.commands.resolve_contact_candidates",
            new=AsyncMock(side_effect=[noisy_candidates, token_candidates]),
        ) as resolve_mock:
            resolved = await calendar_commands._resolve_attendee_emails(db, ["Dus danko fort"])

        self.assertEqual(resolved.emails, ["danko@example.com"])
        self.assertEqual(resolved.suggestions, [])
        self.assertEqual(resolve_mock.await_count, 2)
        self.assertEqual(resolve_mock.await_args_list[0].kwargs["raw_query"], "Dus danko fort")
        self.assertEqual(resolve_mock.await_args_list[1].kwargs["raw_query"], "danko")

    async def test_calendar_attendee_resolution_keeps_suggestions_when_ambiguous(self) -> None:
        db = AsyncMock()
        ambiguous_candidates = [
            email_contacts.ContactCandidate(
                email="danko@example.com",
                label="Danko",
                confidence=0.82,
                source="graph",
            ),
            email_contacts.ContactCandidate(
                email="danko.work@example.com",
                label="Danko Work",
                confidence=0.79,
                source="local",
            ),
        ]

        with patch(
            "app.services.calendar.commands.resolve_contact_candidates",
            new=AsyncMock(return_value=ambiguous_candidates),
        ):
            resolved = await calendar_commands._resolve_attendee_emails(db, ["Danko"])

        self.assertEqual(resolved.emails, [])
        self.assertEqual(len(resolved.suggestions), 2)
        self.assertEqual(resolved.suggestions[0]["email"], "danko@example.com")

    async def test_new_email_recovers_suggestions_from_draft_greeting(self) -> None:
        db = AsyncMock()

        parsed = ParsedEmailAction(
            action="new_email",
            recipient=None,
            subject_hint=None,
            message_instructions="send an email tudanko tell him accept the offer",
            reasoning="test",
            usage=None,
        )
        drafted = SimpleNamespace(subject="Quick update", body="Hi Danko,\n\nCould you accept the offer?", usage=None)
        created_draft = SimpleNamespace(
            id="draft-1",
            recipient_email=None,
            suggestions=[
                SimpleNamespace(email="danko@example.com"),
                SimpleNamespace(email="danko.work@example.com"),
            ],
        )
        created_notification = SimpleNamespace(id="notif-1")
        candidates = [
            SimpleNamespace(email="danko@example.com", label="Danko", confidence=0.82, source="graph"),
            SimpleNamespace(email="danko.work@example.com", label="Danko Work", confidence=0.79, source="local"),
        ]

        with (
            patch("app.services.email.commands._resolve_context", new=AsyncMock(return_value=None)),
            patch("app.services.email.commands.get_llm_config", new=AsyncMock(return_value=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))),
            patch("app.services.email.commands.parse_email_user_action", new=AsyncMock(return_value=parsed)),
            patch("app.services.email.commands.resolve_contact_candidates", new=AsyncMock(side_effect=[[], candidates])) as resolve_candidates_mock,
            patch("app.services.email.commands.draft_email", new=AsyncMock(return_value=drafted)),
            patch("app.services.email.commands.draft_runtime.create_draft", new=AsyncMock(return_value=created_draft)) as create_draft_mock,
            patch("app.services.email.commands.create_notification", new=AsyncMock(return_value=created_notification)),
            patch("app.services.email.commands.draft_runtime.attach_send_notification", new=AsyncMock()),
            patch("app.services.email.commands.push_notification", new=AsyncMock()),
        ):
            outcome = await handle_email_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="Send an email tudanko tell him accept the offer",
                correlation_id="corr-3",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        self.assertEqual(resolve_candidates_mock.await_count, 2)
        self.assertEqual(resolve_candidates_mock.await_args_list[1].kwargs["raw_query"], "Danko")
        self.assertIsNone(create_draft_mock.await_args.kwargs["recipient_email"])


if __name__ == "__main__":
    unittest.main()
