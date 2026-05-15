from __future__ import annotations

from typing import Any, Optional

from models import IncomingMessengerActivity, IncomingMessengerMessage, MessengerAttachment, Transport


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_int(*values: Any) -> int:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _jid_user(value: Any) -> str:
    text = _first_text(value)
    if "@" not in text:
        return text
    return text.split("@", 1)[0]


def _parse_attachment(raw: dict[str, Any]) -> MessengerAttachment:
    return MessengerAttachment(
        type=_first_text(raw.get("type"), "attachment"),
        url=raw.get("url"),
        preview_url=raw.get("previewUrl") or raw.get("preview_url"),
        file_name=raw.get("fileName") or raw.get("filename"),
        mime_type=raw.get("mimeType") or raw.get("mime_type"),
        file_size=raw.get("fileSize") or raw.get("file_size"),
    )


def parse_messenger_event(event: dict[str, Any]) -> Optional[IncomingMessengerMessage]:
    event_type = event.get("type")
    if event_type not in {"message", "e2eeMessage"}:
        return None

    data = event.get("data") or {}
    transport: Transport = "e2ee" if event_type == "e2eeMessage" else "regular"
    thread_id = _first_text(data.get("threadId"), data.get("thread_id"))
    chat_jid = _first_text(data.get("chatJid"), data.get("chat_jid")) or None
    messenger_id = chat_jid if transport == "e2ee" and chat_jid else thread_id
    if not messenger_id:
        return None

    sender_id = _first_text(data.get("senderId"), data.get("sender_id"))
    sender_jid = _first_text(data.get("senderJid"), data.get("sender_jid")) or None
    sender_name = _first_text(
        data.get("senderName"),
        data.get("sender_name"),
        data.get("authorName"),
        data.get("fromName"),
        sender_id,
    )

    reply = data.get("replyTo") or data.get("reply_to") or {}
    attachments = [
        _parse_attachment(item)
        for item in (data.get("attachments") or [])
        if isinstance(item, dict)
    ]

    return IncomingMessengerMessage(
        transport=transport,
        messenger_id=messenger_id,
        thread_id=thread_id,
        chat_jid=chat_jid,
        sender_id=sender_id,
        sender_jid=sender_jid,
        sender_name=sender_name or messenger_id,
        text=_first_text(data.get("text"), data.get("body")),
        message_id=_first_text(data.get("id"), data.get("messageId"), data.get("message_id")),
        timestamp_ms=int(data.get("timestampMs") or data.get("timestamp") or 0),
        attachments=attachments,
        reply_to_message_id=_first_text(reply.get("messageId"), reply.get("message_id")) or None,
        reply_to_sender_id=_first_text(reply.get("senderId"), reply.get("sender_id")) or None,
        reply_to_sender_jid=_first_text(reply.get("senderJid"), reply.get("sender_jid")) or None,
        raw_event_type=str(event_type),
        raw=event,
    )


def parse_messenger_activity(event: dict[str, Any]) -> Optional[IncomingMessengerActivity]:
    event_type = str(event.get("type") or "")
    data = event.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    timestamp_ms = _first_int(data.get("timestampMs"), data.get("timestamp"), event.get("timestamp"))

    if event_type == "reaction":
        thread_id = _first_text(data.get("threadId"), data.get("thread_id"))
        actor_id = _first_text(data.get("actorId"), data.get("actor_id"))
        return IncomingMessengerActivity(
            kind="reaction",
            transport="regular",
            messenger_id=thread_id,
            thread_id=thread_id,
            actor_id=actor_id,
            actor_name=actor_id,
            target_message_id=_first_text(data.get("messageId"), data.get("message_id")),
            reaction=_first_text(data.get("reaction")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    if event_type == "e2eeReaction":
        chat_jid = _first_text(data.get("chatJid"), data.get("chat_jid"))
        actor_jid = _first_text(data.get("senderJid"), data.get("sender_jid"))
        actor_id = _first_text(data.get("senderId"), data.get("sender_id"), _jid_user(actor_jid))
        return IncomingMessengerActivity(
            kind="reaction",
            transport="e2ee",
            messenger_id=chat_jid,
            chat_jid=chat_jid or None,
            actor_id=actor_id,
            actor_jid=actor_jid or None,
            actor_name=actor_id,
            target_message_id=_first_text(data.get("messageId"), data.get("message_id")),
            reaction=_first_text(data.get("reaction")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    if event_type == "messageEdit":
        thread_id = _first_text(data.get("threadId"), data.get("thread_id"))
        if thread_id == "0":
            thread_id = ""
        chat_jid = _first_text(data.get("chatJid"), data.get("chat_jid"))
        is_e2ee = bool(data.get("isE2EE") or data.get("is_e2ee") or chat_jid or "@" in thread_id)
        transport: Transport = "e2ee" if is_e2ee else "regular"
        messenger_id = chat_jid if transport == "e2ee" else thread_id
        return IncomingMessengerActivity(
            kind="message_edit",
            transport=transport,
            messenger_id=messenger_id,
            thread_id="" if transport == "e2ee" else thread_id,
            chat_jid=(chat_jid or thread_id) if transport == "e2ee" else None,
            target_message_id=_first_text(data.get("messageId"), data.get("message_id")),
            text=_first_text(data.get("newText"), data.get("new_text"), data.get("text")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    if event_type == "messageUnsend":
        thread_id = _first_text(data.get("threadId"), data.get("thread_id"))
        chat_jid = _first_text(data.get("chatJid"), data.get("chat_jid"))
        is_e2ee = bool(data.get("isE2EE") or data.get("is_e2ee") or chat_jid or "@" in thread_id)
        transport = "e2ee" if is_e2ee else "regular"
        messenger_id = (chat_jid or thread_id) if transport == "e2ee" else thread_id
        return IncomingMessengerActivity(
            kind="message_unsend",
            transport=transport,
            messenger_id=messenger_id,
            thread_id="" if transport == "e2ee" else thread_id,
            chat_jid=(chat_jid or thread_id) if transport == "e2ee" else None,
            target_message_id=_first_text(data.get("messageId"), data.get("message_id")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    if event_type == "typing":
        thread_id = _first_text(data.get("threadId"), data.get("thread_id"))
        actor_id = _first_text(data.get("senderId"), data.get("sender_id"))
        return IncomingMessengerActivity(
            kind="typing",
            transport="regular",
            messenger_id=thread_id,
            thread_id=thread_id,
            actor_id=actor_id,
            actor_name=actor_id,
            is_typing=bool(data.get("isTyping") or data.get("is_typing")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    if event_type == "readReceipt":
        thread_id = _first_text(data.get("threadId"), data.get("thread_id"))
        actor_id = _first_text(data.get("readerId"), data.get("reader_id"))
        return IncomingMessengerActivity(
            kind="read_receipt",
            transport="regular",
            messenger_id=thread_id,
            thread_id=thread_id,
            actor_id=actor_id,
            actor_name=actor_id,
            text=_first_text(data.get("readWatermarkTimestampMs"), data.get("read_watermark_timestamp_ms")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    if event_type == "e2eeReceipt":
        chat_jid = _first_text(data.get("chat"), data.get("chatJid"), data.get("chat_jid"))
        actor_jid = _first_text(data.get("sender"), data.get("senderJid"), data.get("sender_jid"))
        actor_id = _jid_user(actor_jid)
        message_ids = [str(item) for item in (data.get("messageIds") or data.get("message_ids") or []) if item]
        return IncomingMessengerActivity(
            kind="e2ee_receipt",
            transport="e2ee",
            messenger_id=chat_jid,
            chat_jid=chat_jid or None,
            actor_id=actor_id,
            actor_jid=actor_jid or None,
            actor_name=actor_id,
            target_message_id=message_ids[0] if message_ids else "",
            target_message_ids=message_ids,
            receipt_type=_first_text(data.get("type")),
            timestamp_ms=timestamp_ms,
            raw_event_type=event_type,
            raw=event,
        )

    return None