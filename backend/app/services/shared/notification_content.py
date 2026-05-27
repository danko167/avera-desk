from __future__ import annotations


_NOTIFICATION_COPY = {
    "email_draft": {
        "default": {
            "instruction": "Review the draft, then say 'send it' or 'cancel draft'.",
        },
    },
    "email_message": {
        "default": {
            "instruction": "Say 'summarize this' or 'reply'.",
        },
        "followup_detected": {
            "instruction": "Follow-up may be needed. Say 'summarize this' or 'reply'.",
        },
    },
    "follow_up_reminder": {
        "default": {
            "instruction": "Say 'complete', 'dismiss', or 'remind me tomorrow'.",
        },
    },
    "calendar_proposal": {
        "ready": {
            "instruction": "Review the plan, then approve, reject, or edit it.",
        },
        "ready_with_conflicts": {
            "instruction": "Conflicts found. Review the options, then approve, reject, or edit it.",
        },
        "approved": {
            "instruction": "Approved. Reopen the calendar panel to review it.",
        },
        "rejected": {
            "instruction": "Rejected. Create a new proposal if needed.",
        },
        "canceled": {
            "instruction": "Canceled. Create a new proposal when you're ready.",
        },
    },
}


def _copy(kind: str, variant: str = "default") -> dict[str, str]:
    return _NOTIFICATION_COPY[kind][variant]


def build_email_draft_notification_message(*, draft_id: str, recipient_email: str | None) -> str:
    preview_recipient = (recipient_email or "").strip() or "(recipient required)"
    return f"Email draft for {preview_recipient} [draft:{draft_id}]"


def build_email_draft_notification_details(
    *,
    recipient_email: str | None,
    source_notification_id: str | None = None,
) -> dict:
    preview_recipient = (recipient_email or "").strip()
    headline = (
        f"Email draft for {preview_recipient}"
        if preview_recipient
        else "Email draft needs a recipient"
    )
    details = {
        "kind": "email_draft",
        "variant": "default",
        "headline": headline,
        "instruction": _copy("email_draft")["instruction"],
    }
    cleaned_source_notification_id = (source_notification_id or "").strip()
    if cleaned_source_notification_id:
        details["source_notification_id"] = cleaned_source_notification_id
    return details


def build_new_email_notification_message(*, from_email: str | None) -> str:
    sender = (from_email or "").strip() or "unknown sender"
    return f"New email from {sender}"


def build_new_email_notification_details(
    *,
    from_email: str | None,
    subject: str | None,
    body_preview: str | None = None,
    followup_id: str | None = None,
    followup_summary: str | None = None,
) -> dict:
    variant = "followup_detected" if followup_id and (followup_summary or "").strip() else "default"
    clean_body_preview = (body_preview or "").strip() or None
    return {
        "kind": "email_message",
        "variant": variant,
        "headline": build_new_email_notification_message(from_email=from_email),
        "instruction": _copy("email_message", variant)["instruction"],
        "context_line": (followup_summary or "").strip() or None,
        "from_email": (from_email or "").strip() or None,
        "subject": (subject or "").strip() or None,
        "body_preview": clean_body_preview,
        "original_email_text": clean_body_preview,
        "followup_id": followup_id,
        "followup_summary": followup_summary,
    }


def build_follow_up_notification_message(*, follow_up_id: str, summary: str, prefix: str = "Follow-up reminder") -> str:
    clean_summary = (summary or "").strip()
    return f"{prefix} [fu:{follow_up_id}] {clean_summary}".strip()


def build_follow_up_notification_details(*, summary: str) -> dict:
    clean_summary = (summary or "").strip()
    return {
        "kind": "follow_up_reminder",
        "variant": "default",
        "headline": "Follow-up reminder",
        "context_line": clean_summary or None,
        "instruction": _copy("follow_up_reminder")["instruction"],
    }


def build_calendar_proposal_notification_message(
    *,
    proposal_id: str,
    title: str | None,
    action: str | None,
    status: str | None,
) -> str:
    clean_title = (title or "").strip() or "Untitled meeting"
    action_label = (action or "").strip().replace("_", " ") or "calendar update"
    normalized_status = (status or "").strip().lower()

    if normalized_status == "approved":
        prefix = "Calendar proposal approved"
    elif normalized_status == "rejected":
        prefix = "Calendar proposal rejected"
    elif normalized_status == "canceled":
        prefix = "Calendar proposal canceled"
    else:
        prefix = "Calendar proposal ready"

    return f"{prefix} [cal:{proposal_id}] {clean_title} ({action_label})."


def build_calendar_proposal_notification_details(
    *,
    title: str | None,
    action: str | None,
    status: str | None,
    conflict_count: int,
    option_count: int,
    source_notification_id: str | None = None,
) -> dict:
    clean_title = (title or "").strip() or "Untitled meeting"
    action_label = (action or "").strip().replace("_", " ") or "calendar update"
    normalized_status = (status or "").strip().lower()

    if normalized_status == "approved":
        variant = "approved"
    elif normalized_status == "rejected":
        variant = "rejected"
    elif normalized_status == "canceled":
        variant = "canceled"
    elif conflict_count > 0:
        variant = "ready_with_conflicts"
    else:
        variant = "ready"

    context_parts = [action_label]
    if conflict_count > 0:
        context_parts.append(f"{conflict_count} conflict{'s' if conflict_count != 1 else ''}")
    if option_count > 0:
        context_parts.append(f"{option_count} option{'s' if option_count != 1 else ''}")

    details = {
        "kind": "calendar_proposal",
        "variant": variant,
        "headline": clean_title,
        "context_line": " | ".join(context_parts),
        "instruction": _copy("calendar_proposal", variant)["instruction"],
    }
    cleaned_source_notification_id = (source_notification_id or "").strip()
    if cleaned_source_notification_id:
        details["source_notification_id"] = cleaned_source_notification_id
    return details