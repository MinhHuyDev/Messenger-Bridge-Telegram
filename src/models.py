from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


Transport = Literal["e2ee", "regular"]
ActivityKind = Literal[
    "reaction",
    "message_edit",
    "message_unsend",
    "typing",
    "read_receipt",
    "e2ee_receipt",
    "presence",
]


@dataclass
class MessengerAttachment:
    type: str = "attachment"
    url: Optional[str] = None
    preview_url: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None

    @property
    def best_url(self) -> Optional[str]:
        return self.url or self.preview_url


@dataclass
class IncomingMessengerMessage:
    transport: Transport
    messenger_id: str
    thread_id: str
    chat_jid: Optional[str]
    sender_id: str
    sender_jid: Optional[str]
    sender_name: str
    text: str
    message_id: str
    timestamp_ms: int = 0
    thread_name: str = ""
    thread_type: int = 0
    attachments: list[MessengerAttachment] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    reply_to_sender_id: Optional[str] = None
    reply_to_sender_jid: Optional[str] = None
    raw_event_type: str = "message"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncomingMessengerActivity:
    kind: ActivityKind
    transport: Transport
    messenger_id: str = ""
    thread_id: str = ""
    chat_jid: Optional[str] = None
    actor_id: str = ""
    actor_jid: Optional[str] = None
    actor_name: str = ""
    target_message_id: str = ""
    target_message_ids: list[str] = field(default_factory=list)
    reaction: str = ""
    text: str = ""
    is_typing: Optional[bool] = None
    receipt_type: str = ""
    timestamp_ms: int = 0
    raw_event_type: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TopicEntry:
    topic_id: int
    messenger_id: str
    transport: Transport
    name: str
    thread_id: Optional[str] = None
    chat_jid: Optional[str] = None
    created_at: int = 0
    updated_at: int = 0


@dataclass
class QuoteData:
    message_id: str
    transport: Transport
    messenger_id: str
    sender_id: str = ""
    sender_jid: str = ""
    chat_jid: str = ""
    thread_id: str = ""