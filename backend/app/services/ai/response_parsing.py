from __future__ import annotations


def extract_output_text_from_responses_payload(data: dict, *, missing_message: str = "responses output_text missing") -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text_value = part.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value)
        combined = "\n".join(parts).strip()
        if combined:
            return combined

    raise ValueError(missing_message)


def extract_output_text_from_chat_payload(
    data: dict,
    *,
    missing_choices_message: str = "chat completions response missing choices",
    missing_message_message: str = "chat completions response missing message",
    missing_text_message: str = "chat completions response missing text content",
) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(missing_choices_message)

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError(missing_message_message)

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text_value = part.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    text_parts.append(text_value)
        combined = "\n".join(text_parts).strip()
        if combined:
            return combined

    raise ValueError(missing_text_message)