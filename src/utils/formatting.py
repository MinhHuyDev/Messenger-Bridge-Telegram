from __future__ import annotations

from html import escape
from typing import Any

from models import IncomingMessengerActivity, IncomingMessengerMessage, MessengerAttachment


def truncate(text: str, max_len: int = 4096) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


def escape_html(text: str) -> str:
    return escape(text, quote=False)


def topic_name(display_name: str, transport: str) -> str:
    prefix = "[E2EE]" if transport == "e2ee" else "[MSG]"
    compact = " ".join((display_name or "Messenger").split())
    return truncate(f"{prefix} {compact}", 128)


def _attachment_lines(attachments: list[MessengerAttachment]) -> list[str]:
    lines: list[str] = []
    for index, attachment in enumerate(attachments, start=1):
        label = attachment.type or "attachment"
        name = f" {attachment.file_name}" if attachment.file_name else ""
        url = attachment.best_url
        if url:
            lines.append(f"[{index}] {label}{name}: {url}")
        else:
            lines.append(f"[{index}] {label}{name}")
    return lines


def format_messenger_message(message: IncomingMessengerMessage) -> str:
    sender = escape_html(truncate(message.sender_name or message.sender_id or "Messenger", 80))
    badge = " <code>E2EE</code>" if message.transport == "e2ee" else ""
    parts = [f"<b>{sender}</b>{badge}"]

    if message.text:
        parts.append(escape_html(message.text))

    for line in _attachment_lines(message.attachments):
        parts.append(escape_html(line))

    if len(parts) == 1:
        parts.append("<i>Unsupported Messenger event</i>")

    return truncate("\n".join(parts), 4096)


def format_messenger_activity(activity: IncomingMessengerActivity) -> str:
    actor = escape_html(truncate(activity.actor_name or activity.actor_id or "Messenger", 80))
    badge = " <code>E2EE</code>" if activity.transport == "e2ee" else ""
    parts = [f"<b>{actor}</b>{badge}"]

    if activity.kind == "reaction":
        if activity.reaction:
            parts.append(f"reacted with {escape_html(activity.reaction)}")
        else:
            parts.append("removed a reaction")
    elif activity.kind == "message_edit":
        parts.append("edited a message")
        if activity.text:
            parts.append(escape_html(activity.text))
    elif activity.kind == "message_unsend":
        parts.append("unsent a message")
    elif activity.kind == "typing":
        parts.append("is typing..." if activity.is_typing else "stopped typing")
    elif activity.kind == "read_receipt":
        parts.append("read messages in this conversation")
    elif activity.kind == "e2ee_receipt":
        count = len(activity.target_message_ids)
        suffix = f" for {count} message(s)" if count else ""
        receipt_type = activity.receipt_type or "receipt"
        parts.append(f"E2EE {escape_html(receipt_type)}{suffix}")
    elif activity.kind == "presence":
        parts.append(activity.text or "presence changed")
    else:
        parts.append("Messenger activity")

    return truncate("\n".join(parts), 4096)


def format_topic_intro(message: IncomingMessengerMessage) -> str:
    return (
        "<b>Messenger conversation linked</b>\n"
        f"transport: <code>{escape_html(message.transport)}</code>\n"
        f"thread_id: <code>{escape_html(message.thread_id or '-')}</code>\n"
        f"chat_jid: <code>{escape_html(message.chat_jid or '-')}</code>"
    )


def telegram_message_to_text(message: Any) -> str:
    text = (message.text or message.caption or "").strip()
    markers: list[str] = []

    if getattr(message, "photo", None):
        markers.append("[Telegram photo]")
    if getattr(message, "video", None):
        markers.append("[Telegram video]")
    if getattr(message, "voice", None):
        markers.append("[Telegram voice]")
    if getattr(message, "audio", None):
        markers.append("[Telegram audio]")
    if getattr(message, "sticker", None):
        markers.append("[Telegram sticker]")
    if getattr(message, "animation", None):
        markers.append("[Telegram animation]")
    if getattr(message, "document", None):
        document = message.document
        filename = getattr(document, "file_name", None)
        markers.append(f"[Telegram file: {filename}]" if filename else "[Telegram file]")

    if text and markers:
        return f"{text}\n{' '.join(markers)}"
    if text:
        return text
    return " ".join(markers)