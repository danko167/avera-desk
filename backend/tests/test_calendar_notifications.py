import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas import CalendarPlanningRequest, CalendarProposalDto
from app.services.calendar import planner, proposals


def _proposal_dto(*, proposal_id: str, source_notification_id: str | None = None) -> CalendarProposalDto:
    now = datetime.now(timezone.utc).isoformat()
    return CalendarProposalDto(
        id=proposal_id,
        provider="m365",
        action="create_event",
        status="awaiting_user_decision",
        title="Meeting with John",
        start_at=now,
        end_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        timezone_name="UTC",
        attendees=["john@doe.com"],
        target_event_id=None,
        source_email_id="email-1",
        source_followup_id=None,
        source_notification_id=source_notification_id,
        conflicts=[],
        options=[],
        notes=None,
        created_at=now,
        updated_at=now,
        approved_at=None,
        rejected_at=None,
    )


class CalendarNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_calendar_proposal_emits_tagged_notification(self) -> None:
        db = AsyncMock()
        provider = SimpleNamespace(
            get_upcoming_events=AsyncMock(return_value=[]),
            get_availability=AsyncMock(return_value=[]),
        )
        payload = CalendarPlanningRequest(
            action="create_event",
            title="Meeting with John",
            desired_start_at="2026-05-22T15:00:00Z",
            duration_minutes=60,
            attendees=["john@doe.com"],
            source_email_id="email-1",
        )

        created_dto = _proposal_dto(proposal_id="proposal-123")
        attached_dto = _proposal_dto(proposal_id="proposal-123", source_notification_id="notif-123")
        fake_notification = SimpleNamespace(id="notif-123")

        with (
            patch.object(proposals, "create_proposal", AsyncMock(return_value=created_dto)) as create_mock,
            patch.object(proposals, "attach_source_notification", AsyncMock(return_value=attached_dto)) as attach_mock,
            patch.object(planner.notifications, "create_notification", AsyncMock(return_value=fake_notification)) as notify_create_mock,
            patch.object(planner.notifications, "push_notification", AsyncMock()) as notify_push_mock,
        ):
            result = await planner.plan_calendar_proposal(db, provider=provider, payload=payload)

        self.assertEqual(result.proposal.id, "proposal-123")
        self.assertEqual(result.proposal.source_notification_id, "notif-123")

        create_mock.assert_awaited_once()
        notify_create_mock.assert_awaited_once()
        notify_push_mock.assert_awaited_once_with(fake_notification)
        attach_mock.assert_awaited_once_with(
            db,
            proposal_id="proposal-123",
            notification_id="notif-123",
        )

        message_arg = notify_create_mock.await_args.args[1]
        self.assertIn("[cal:proposal-123]", message_arg)
        self.assertEqual(
            notify_create_mock.await_args.kwargs["details"],
            {
                "kind": "calendar_proposal",
                "variant": "ready",
                "headline": "Meeting with John",
                "context_line": "create event | 3 options",
                "instruction": "Review the plan, then approve, reject, or edit it.",
            },
        )

    async def test_approve_proposal_updates_existing_notification_message(self) -> None:
        db = AsyncMock()
        now = datetime.now(timezone.utc)
        record = SimpleNamespace(
            id="proposal-approve-1",
            provider="m365",
            action="reschedule_event",
            status="awaiting_user_decision",
            title="Team sync",
            start_at=now,
            end_at=now + timedelta(hours=1),
            timezone_name="UTC",
            attendees_json={"items": ["john@doe.com"]},
            target_event_id="event-1",
            source_email_id=None,
            source_followup_id=None,
            source_notification_id="notif-5",
            conflicts_json={"items": []},
            options_json={"items": []},
            notes=None,
            metadata_json={"execution": "manual_only"},
            created_at=now,
            updated_at=now,
            approved_at=None,
            rejected_at=None,
        )
        updated_notification = SimpleNamespace(id="notif-5")

        with (
            patch.object(proposals, "_get_record", AsyncMock(return_value=record)),
            patch.object(proposals.notifications, "update_notification_message", AsyncMock(return_value=updated_notification)) as update_mock,
            patch.object(proposals.notifications, "push_notification", AsyncMock()) as push_mock,
        ):
            dto = await proposals.approve_proposal(db, proposal_id="proposal-approve-1")

        self.assertIsNotNone(dto)
        self.assertEqual(dto.status, "approved")
        self.assertEqual(dto.id, "proposal-approve-1")

        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(record)
        update_mock.assert_awaited_once()
        push_mock.assert_awaited_once_with(updated_notification)

        message_arg = update_mock.await_args.args[2]
        self.assertIn("[cal:proposal-approve-1]", message_arg)
        self.assertIn("approved", message_arg.lower())
        self.assertEqual(
            update_mock.await_args.kwargs["details"],
            {
                "kind": "calendar_proposal",
                "variant": "approved",
                "headline": "Team sync",
                "context_line": "reschedule event",
                "instruction": "Approved. Reopen the calendar panel to review it.",
            },
        )

    async def test_approve_create_event_proposal_creates_calendar_event(self) -> None:
        db = AsyncMock()
        now = datetime.now(timezone.utc)
        record = SimpleNamespace(
            id="proposal-create-1",
            provider="m365",
            action="create_event",
            status="awaiting_user_decision",
            title="Project kickoff",
            start_at=now,
            end_at=now + timedelta(hours=1),
            timezone_name="UTC",
            attendees_json={"items": ["alice@example.com", "bob@example.com"]},
            target_event_id=None,
            source_email_id=None,
            source_followup_id=None,
            source_notification_id="notif-6",
            conflicts_json={"items": []},
            options_json={"items": []},
            notes="Agenda review",
            metadata_json={"execution": "manual_only"},
            created_at=now,
            updated_at=now,
            approved_at=None,
            rejected_at=None,
        )
        created_event = {"id": "event-123", "subject": "Project kickoff"}
        updated_notification = SimpleNamespace(id="notif-6")
        provider = SimpleNamespace(create_calendar_event=AsyncMock(return_value=created_event))

        with (
            patch.object(proposals, "_get_record", AsyncMock(return_value=record)),
            patch.object(proposals.preferences, "get_settings", AsyncMock(return_value={"email_provider": "m365"})),
            patch.object(proposals, "get_email_api_provider", return_value=provider),
            patch.object(proposals.notifications, "update_notification_message", AsyncMock(return_value=updated_notification)) as update_mock,
            patch.object(proposals.notifications, "push_notification", AsyncMock()) as push_mock,
        ):
            dto = await proposals.approve_proposal(db, proposal_id="proposal-create-1")

        self.assertIsNotNone(dto)
        self.assertEqual(dto.status, "approved")
        self.assertEqual(dto.target_event_id, "event-123")

        provider.create_calendar_event.assert_awaited_once()
        create_kwargs = provider.create_calendar_event.await_args.kwargs
        self.assertEqual(create_kwargs["subject"], "Project kickoff")
        self.assertEqual(create_kwargs["timezone_name"], "UTC")
        self.assertEqual(create_kwargs["attendees"], ["alice@example.com", "bob@example.com"])
        self.assertEqual(create_kwargs["body_text"], "Agenda review")

        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(record)
        update_mock.assert_awaited_once()
        push_mock.assert_awaited_once_with(updated_notification)

        self.assertEqual(record.target_event_id, "event-123")
        self.assertEqual(record.metadata_json["execution"], "calendar_event_created")
        self.assertFalse(record.metadata_json["approved_without_auto_execution"])

    async def test_plan_calendar_proposal_auto_shifts_flexible_time_when_requested_slot_conflicts(self) -> None:
        db = AsyncMock()
        desired_start = datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc)
        desired_end = desired_start + timedelta(hours=1)
        shifted_start = desired_start + timedelta(hours=1)
        shifted_end = shifted_start + timedelta(hours=1)

        provider = SimpleNamespace(
            get_upcoming_events=AsyncMock(
                return_value=[
                    {
                        "id": "busy-1",
                        "subject": "Existing meeting",
                        "start_at": desired_start.isoformat(),
                        "end_at": desired_end.isoformat(),
                    }
                ]
            ),
            get_availability=AsyncMock(return_value=[]),
        )
        payload = CalendarPlanningRequest(
            action="create_event",
            title="Flexible morning meeting",
            desired_start_at=desired_start.isoformat(),
            duration_minutes=60,
            attendees=[],
            auto_shift_conflict_free_for_flexible_time=True,
        )

        created_dto = _proposal_dto(proposal_id="proposal-auto-shift")
        attached_dto = _proposal_dto(proposal_id="proposal-auto-shift", source_notification_id="notif-auto-shift")
        fake_notification = SimpleNamespace(id="notif-auto-shift")

        with (
            patch.object(proposals, "create_proposal", AsyncMock(return_value=created_dto)) as create_mock,
            patch.object(proposals, "attach_source_notification", AsyncMock(return_value=attached_dto)),
            patch.object(planner.notifications, "create_notification", AsyncMock(return_value=fake_notification)),
            patch.object(planner.notifications, "push_notification", AsyncMock()),
        ):
            result = await planner.plan_calendar_proposal(db, provider=provider, payload=payload)

        self.assertEqual(result.conflicts, [])
        self.assertEqual(result.options[0].start_at, shifted_start.isoformat())
        self.assertIn("nearest conflict-free slot", result.reasoning.lower())

        create_kwargs = create_mock.await_args.kwargs
        self.assertEqual(create_kwargs["start_at"], shifted_start.isoformat())
        self.assertEqual(create_kwargs["end_at"], shifted_end.isoformat())
        self.assertEqual(create_kwargs["conflicts"], [])


if __name__ == "__main__":
    unittest.main()
