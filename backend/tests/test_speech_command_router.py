import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.speech.command_router import handle_speech_command_from_transcript


class SpeechCommandRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_affirmative_response_approves_pending_calendar_proposal(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="none",
                        action="none",
                        slots={},
                        confidence=0.53,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:none",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-gen-1", attendees=["mark@example.com"])),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_command_from_transcript",
                new=AsyncMock(),
            ) as email_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-gen-1]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "awaiting_user_decision"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-gen-1",
                transcript_text="Oh, sure, we can do that.",
                correlation_id="corr-router-cal-affirm-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_approved")
        approve_calendar_mock.assert_awaited_once_with(db, proposal_id="cal-gen-1")
        email_mock.assert_not_awaited()

    async def test_router_followup_hint_calls_followup_handler_when_stage_a_none(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="none",
                        action="none",
                        slots={},
                        confidence=0.44,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:none",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_follow_up_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="snooze", display_text="Scheduled reminder.")),
            ) as followup_mock,
            patch(
                "app.services.speech.command_router.handle_email_command_from_transcript",
                new=AsyncMock(),
            ) as email_mock,
        ):
            db.execute = AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one_or_none=lambda: SimpleNamespace(message="Follow-up [fu:fu-123]")
                )
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-fu-123",
                transcript_text="Remind me tomorrow",
                correlation_id="corr-router-followup-fallback-1",
            )

        self.assertEqual(outcome.result, "snooze")
        followup_mock.assert_awaited_once()
        email_mock.assert_not_awaited()

    async def test_router_falls_back_to_email_handler_when_stage_a_returns_none(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="none",
                        action="none",
                        slots={},
                        confidence=0.41,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:none",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_email_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_ready", display_text="Draft prepared.")),
            ) as email_mock,
        ):
            db.execute = AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one_or_none=lambda: SimpleNamespace(message="Follow-up may be needed.")
                )
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-affirmative-1",
                transcript_text="Sure, we can do that.",
                correlation_id="corr-router-none-email-fallback-1",
            )

        self.assertEqual(outcome.result, "email_draft_ready")
        email_mock.assert_awaited_once()

    async def test_router_explicit_dismiss_dismisses_active_notification(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="none",
                        action="none",
                        slots={},
                        confidence=0.61,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:none",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_email_command_from_transcript",
                new=AsyncMock(),
            ) as email_mock,
        ):
            db.execute = AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one_or_none=lambda: SimpleNamespace(message="Follow-up may be needed.")
                )
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-dismiss-1",
                transcript_text="Dismiss.",
                correlation_id="corr-router-dismiss-1",
            )

        self.assertEqual(outcome.result, "dismiss")
        self.assertIsNotNone(outcome.interaction)
        self.assertEqual(outcome.interaction.dismiss_notification_id, "notif-dismiss-1")
        self.assertTrue(outcome.interaction.close_window)
        email_mock.assert_not_awaited()

    async def test_router_prefers_calendar_handler_before_email_and_followup(self) -> None:
        db = object()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="calendar",
                        action="create_event",
                        slots={},
                        confidence=0.93,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_calendar_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="calendar_proposal_ready")),
            ) as calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_command_from_transcript",
                new=AsyncMock(),
            ) as email_mock,
        ):
            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="Make a meeting with Danko tomorrow at 2 PM",
                correlation_id="corr-router-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_ready")
        calendar_mock.assert_awaited_once()
        email_mock.assert_not_awaited()

    async def test_router_returns_clarification_when_stage_a_reports_missing_slots(self) -> None:
        db = object()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="calendar",
                        action="create_event",
                        slots={},
                        confidence=0.81,
                        missing_slots=["desired_start_at"],
                        clarification_question="What date and time should I schedule it for?",
                        usage=None,
                        reasoning="llm:missing_date",
                    )
                ),
            ),
            patch("app.services.speech.command_router.handle_calendar_command_from_transcript", new=AsyncMock()) as calendar_mock,
        ):
            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="make a meeting with Danko",
                correlation_id="corr-router-clarify-1",
            )

        self.assertEqual(outcome.result, "intent_clarification_needed")
        self.assertIn("date and time", outcome.display_text.lower())
        calendar_mock.assert_not_awaited()

    async def test_router_routes_email_draft_action_when_active_draft_exists(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="send_draft",
                        slots={},
                        confidence=0.9,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:send_draft",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_sent")),
            ) as draft_mock,
        ):
            execute_result = SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(message="Email draft for x [draft:draft-1]")
            )
            db.execute = AsyncMock(return_value=execute_result)

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-1",
                transcript_text="send it",
                correlation_id="corr-router-draft-1",
            )

        self.assertEqual(outcome.result, "email_draft_sent")
        draft_mock.assert_awaited_once()

    async def test_router_resolves_latest_pending_draft_for_cancel_without_notification(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="cancel_draft",
                        slots={},
                        confidence=0.89,
                        missing_slots=["active_draft"],
                        clarification_question="There is no active draft to cancel.",
                        usage=None,
                        reasoning="heuristic:cancel_draft",
                    )
                ),
            ) as route_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_canceled")),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one_or_none=lambda: "draft-pending-1"
                )
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="cancel",
                correlation_id="corr-router-draft-cancel-1",
            )

        self.assertEqual(outcome.result, "email_draft_canceled")
        route_mock.assert_awaited_once()
        draft_mock.assert_awaited_once()

    async def test_router_resolves_latest_pending_draft_for_send_variant_without_notification(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="none",
                        action="none",
                        slots={},
                        confidence=0.41,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:none",
                    )
                ),
            ) as route_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_sent")),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one_or_none=lambda: "draft-pending-send-1"
                )
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="S And it",
                correlation_id="corr-router-draft-send-variant-1",
            )

        self.assertEqual(outcome.result, "email_draft_sent")
        route_mock.assert_awaited_once()
        draft_mock.assert_awaited_once()

    async def test_router_affirmative_with_active_draft_uses_draft_command(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="none",
                        action="none",
                        slots={},
                        confidence=0.47,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:none",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_sent")),
            ) as draft_mock,
            patch(
                "app.services.speech.command_router.handle_email_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_ready")),
            ) as email_mock,
        ):
            db.execute = AsyncMock(
                return_value=SimpleNamespace(
                    scalar_one_or_none=lambda: SimpleNamespace(message="Review and send [draft:draft-affirm-1]")
                )
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-draft-affirm-1",
                transcript_text="Sure, we can do that.",
                correlation_id="corr-router-draft-affirm-1",
            )

        self.assertEqual(outcome.result, "email_draft_sent")
        draft_mock.assert_awaited_once()
        email_mock.assert_not_awaited()

    async def test_router_cancel_targets_calendar_proposal_when_no_active_draft(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="cancel_draft",
                        slots={},
                        confidence=0.72,
                        missing_slots=["active_draft"],
                        clarification_question="There is no active draft to cancel.",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.cancel_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-1")),
            ) as cancel_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(scalar_one_or_none=lambda: None),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id=None,
                transcript_text="cancel",
                correlation_id="corr-router-cal-cancel-1",
            )

        self.assertEqual(outcome.result, "intent_clarification_needed")
        cancel_calendar_mock.assert_not_awaited()
        draft_mock.assert_not_awaited()

    async def test_router_prefers_calendar_context_over_pending_draft_for_send(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="send_draft",
                        slots={},
                        confidence=0.83,
                        missing_slots=["active_draft"],
                        clarification_question="I don't have an active draft to send. Which draft should I send?",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-ctx-1")),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_sent")),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-ctx-1]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "awaiting_user_decision"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-ctx-1",
                transcript_text="send",
                correlation_id="corr-router-cal-send-context-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_approved")
        approve_calendar_mock.assert_awaited_once_with(db, proposal_id="cal-ctx-1")
        draft_mock.assert_not_awaited()

    async def test_router_prefers_calendar_marker_when_notification_has_both_draft_and_calendar(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="send_draft",
                        slots={},
                        confidence=0.86,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-mixed-1")),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(return_value=SimpleNamespace(result="email_draft_sent")),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(
                            message="Review [draft:draft-xyz] and proposal [cal:cal-mixed-1]"
                        )
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "awaiting_user_decision"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-mixed-1",
                transcript_text="send",
                correlation_id="corr-router-mixed-markers-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_approved")
        approve_calendar_mock.assert_awaited_once_with(db, proposal_id="cal-mixed-1")
        draft_mock.assert_not_awaited()

    async def test_router_cancel_targets_calendar_proposal_and_dismisses_notification(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="cancel_draft",
                        slots={},
                        confidence=0.76,
                        missing_slots=["active_draft"],
                        clarification_question="There is no active draft to cancel.",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.cancel_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-42")),
            ) as cancel_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-42]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "awaiting_user_decision"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-42",
                transcript_text="cancel",
                correlation_id="corr-router-cal-cancel-2",
            )

        self.assertEqual(outcome.result, "calendar_proposal_canceled")
        self.assertIsNotNone(outcome.interaction)
        self.assertEqual(outcome.interaction.dismiss_notification_id, "notif-cal-42")
        self.assertTrue(outcome.interaction.close_window)
        cancel_calendar_mock.assert_awaited_once_with(db, proposal_id="cal-42")
        draft_mock.assert_not_awaited()

    async def test_router_send_targets_calendar_proposal_and_dismisses_notification(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="send_draft",
                        slots={},
                        confidence=0.82,
                        missing_slots=["active_draft"],
                        clarification_question="I don't have an active draft to send. Which draft should I send?",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-88")),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-88]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "awaiting_user_decision"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-88",
                transcript_text="send",
                correlation_id="corr-router-cal-send-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_approved")
        self.assertIsNotNone(outcome.interaction)
        self.assertEqual(outcome.interaction.dismiss_notification_id, "notif-cal-88")
        self.assertTrue(outcome.interaction.close_window)
        approve_calendar_mock.assert_awaited_once_with(db, proposal_id="cal-88")
        draft_mock.assert_not_awaited()

    async def test_router_plain_yes_does_not_auto_approve_calendar_proposal(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="send_draft",
                        slots={},
                        confidence=0.7,
                        missing_slots=["active_draft"],
                        clarification_question="I don't have an active draft to send. Which draft should I send?",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-99]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: None),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-99",
                transcript_text="yes",
                correlation_id="corr-router-cal-send-yes-1",
            )

        self.assertEqual(outcome.result, "intent_clarification_needed")
        approve_calendar_mock.assert_not_awaited()
        draft_mock.assert_not_awaited()

    async def test_router_send_rescues_calendar_even_when_stage_a_returns_calendar_update_event(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="calendar",
                        action="update_event",
                        slots={},
                        confidence=0.61,
                        missing_slots=[],
                        clarification_question=None,
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(return_value=SimpleNamespace(id="cal-101")),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_calendar_command_from_transcript",
                new=AsyncMock(),
            ) as calendar_cmd_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-101]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "awaiting_user_decision"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-101",
                transcript_text="send",
                correlation_id="corr-router-cal-send-update-event-1",
            )

        self.assertEqual(outcome.result, "calendar_proposal_approved")
        approve_calendar_mock.assert_awaited_once_with(db, proposal_id="cal-101")
        calendar_cmd_mock.assert_not_awaited()

    async def test_router_send_returns_calendar_terminal_status_message(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="send_draft",
                        slots={},
                        confidence=0.8,
                        missing_slots=["active_draft"],
                        clarification_question="I don't have an active draft to send. Which draft should I send?",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.calendar_proposals.approve_proposal",
                new=AsyncMock(),
            ) as approve_calendar_mock,
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-202]")
                    ),
                    SimpleNamespace(scalar_one_or_none=lambda: "approved"),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-202",
                transcript_text="send",
                correlation_id="corr-router-cal-send-approved-1",
            )

        self.assertEqual(outcome.result, "intent_clarification_needed")
        self.assertEqual(outcome.display_text, "This calendar proposal is already approved.")
        approve_calendar_mock.assert_not_awaited()
        draft_mock.assert_not_awaited()

    async def test_router_modify_draft_in_calendar_context_does_not_hijack_pending_draft(self) -> None:
        db = SimpleNamespace()

        with (
            patch(
                "app.services.speech.command_router.route_speech_intent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        domain="email",
                        action="modify_draft",
                        slots={},
                        confidence=0.77,
                        missing_slots=["active_draft"],
                        clarification_question="There is no active draft to edit.",
                        usage=None,
                        reasoning="llm:test",
                    )
                ),
            ),
            patch(
                "app.services.speech.command_router.handle_email_draft_command_from_transcript",
                new=AsyncMock(),
            ) as draft_mock,
        ):
            db.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        scalar_one_or_none=lambda: SimpleNamespace(message="Review proposal [cal:cal-303]")
                    ),
                ]
            )

            outcome = await handle_speech_command_from_transcript(
                db,
                notification_id="notif-cal-303",
                transcript_text="edit this",
                correlation_id="corr-router-cal-modify-1",
            )

        self.assertEqual(outcome.result, "intent_clarification_needed")
        self.assertIn("calendar proposal", (outcome.display_text or "").lower())
        draft_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()