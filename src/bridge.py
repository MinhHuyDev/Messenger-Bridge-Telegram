from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass
from typing import Optional

from telegram import Bot, Message, ReplyParameters
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import Application

from config import AppConfig
from messenger.client import MessengerClient
from messenger.events import parse_messenger_activity, parse_messenger_event
from models import IncomingMessengerActivity, IncomingMessengerMessage, QuoteData, TopicEntry
from store import BridgeStore
from utils.formatting import (
    escape_html,
    format_messenger_activity,
    format_messenger_message,
    format_topic_intro,
    telegram_message_to_text,
    topic_name,
    truncate,
)


@dataclass
class ForwardResult:
    ok: bool
    message: str = ""


class MessengerTelegramBridge:
    def __init__(self, config: AppConfig, store: BridgeStore, messenger: MessengerClient) -> None:
        self.config = config
        self.store = store
        self.messenger = messenger
        self.bot: Optional[Bot] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._topic_locks: dict[str, asyncio.Lock] = {}
        self._activity_dedupe: dict[str, int] = {}

    async def start(self, application: Application) -> None:
        self.bot = application.bot
        self.loop = asyncio.get_running_loop()
        await self.bot.set_my_commands([
            ("status", "Show bridge status"),
            ("checktopics", "Check Telegram topic permissions"),
            ("topic", "Manage Messenger topic mappings"),
            ("help", "Show bridge help"),
        ])

        await asyncio.to_thread(self.messenger.login)
        self.messenger.start(self._on_messenger_event_from_thread)
        await self._notify_general(
            "Messenger bridge started. Waiting for E2EE and regular Messenger events."
        )

    async def shutdown(self, application: Application) -> None:
        self.messenger.stop()

    def _on_messenger_event_from_thread(self, event: dict) -> None:
        if self.loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(self.handle_messenger_event(event), self.loop)
        future.add_done_callback(self._log_future_error)

    @staticmethod
    def _log_future_error(future: asyncio.Future) -> None:
        try:
            future.result()
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    async def handle_messenger_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type in {"error", "disconnected"}:
            data = event.get("data") or {}
            await self._notify_general(f"Messenger {event_type}: {data.get('message') or data}")
            return

        message = parse_messenger_event(event)
        if message is None:
            activity = parse_messenger_activity(event)
            if activity is not None:
                await self.handle_messenger_activity(activity)
            return
        if self.config.ignore_self_messages and message.sender_id == self.messenger.self_id:
            return

        await self._enrich_sender_name(message)

        entry = await self._get_or_create_topic(message)
        reply_to = None
        if message.reply_to_message_id:
            reply_to = self.store.get_tg_message_id(message.transport, message.reply_to_message_id)

        sent = await self._send_inbound_with_topic_recovery(entry, message, reply_to)
        if message.message_id:
            quote = QuoteData(
                message_id=message.message_id,
                transport=message.transport,
                messenger_id=message.messenger_id,
                sender_id=message.sender_id,
                sender_jid=message.sender_jid or "",
                chat_jid=message.chat_jid or "",
                thread_id=message.thread_id,
            )
            self.store.save_message(sent.message_id, [message.message_id], quote)

    async def handle_messenger_activity(self, activity: IncomingMessengerActivity) -> None:
        self._resolve_activity_context(activity)
        if not activity.messenger_id:
            await self._notify_general(
                f"Messenger activity {activity.raw_event_type or activity.kind} could not be mapped to a topic."
            )
            return

        await self._enrich_activity_actor_name(activity)
        if not self._should_forward_activity(activity):
            return

        topic_message = self._activity_topic_message(activity)
        entry = await self._get_or_create_topic(topic_message)
        reply_to = self._activity_reply_to_tg(activity)
        await self._send_activity_with_topic_recovery(entry, activity, reply_to)

    async def _get_or_create_topic(self, message: IncomingMessengerMessage) -> TopicEntry:
        existing = self.store.get_topic_by_messenger(message.transport, message.messenger_id)
        if existing:
            await self._maybe_rename_existing_topic(existing, message)
            return existing

        key = f"{message.transport}:{message.messenger_id}"
        lock = self._topic_locks.setdefault(key, asyncio.Lock())
        async with lock:
            existing = self.store.get_topic_by_messenger(message.transport, message.messenger_id)
            if existing:
                await self._maybe_rename_existing_topic(existing, message)
                return existing

            display_name = await self._resolve_topic_display_name(message)
            name = topic_name(display_name, message.transport)
            topic_id = await self._create_forum_topic(name, message.transport)
            entry = self.store.set_topic(TopicEntry(
                topic_id=topic_id,
                messenger_id=message.messenger_id,
                transport=message.transport,
                name=display_name,
                thread_id=message.thread_id,
                chat_jid=message.chat_jid,
            ))
            await self._send_topic_intro(entry, message)
            return entry

    async def _enrich_sender_name(self, message: IncomingMessengerMessage) -> None:
        if not message.sender_id:
            return
        if message.sender_name and message.sender_name != message.sender_id:
            return
        resolved = await asyncio.to_thread(self.messenger.resolve_user_name, message.sender_id)
        if resolved:
            message.sender_name = resolved

    async def _enrich_activity_actor_name(self, activity: IncomingMessengerActivity) -> None:
        if not activity.actor_id:
            return
        if activity.actor_name and activity.actor_name != activity.actor_id:
            return
        resolved = await asyncio.to_thread(self.messenger.resolve_user_name, activity.actor_id)
        if resolved:
            activity.actor_name = resolved

    def _resolve_activity_context(self, activity: IncomingMessengerActivity) -> None:
        if activity.target_message_id:
            quote = self.store.get_quote_by_messenger(activity.transport, activity.target_message_id)
            if quote is None:
                quote = self.store.find_quote_by_messenger(activity.target_message_id)
            if quote is not None:
                activity.transport = quote.transport
                activity.messenger_id = activity.messenger_id or quote.messenger_id
                activity.thread_id = activity.thread_id or quote.thread_id
                activity.chat_jid = activity.chat_jid or quote.chat_jid or None
                activity.actor_id = activity.actor_id or quote.sender_id
                activity.actor_jid = activity.actor_jid or quote.sender_jid or None
                activity.actor_name = activity.actor_name or activity.actor_id

        if activity.transport == "e2ee":
            activity.messenger_id = activity.messenger_id or activity.chat_jid or ""
            activity.chat_jid = activity.chat_jid or activity.messenger_id or None
        else:
            activity.messenger_id = activity.messenger_id or activity.thread_id
            activity.thread_id = activity.thread_id or activity.messenger_id

    def _activity_topic_message(self, activity: IncomingMessengerActivity) -> IncomingMessengerMessage:
        return IncomingMessengerMessage(
            transport=activity.transport,
            messenger_id=activity.messenger_id,
            thread_id=activity.thread_id,
            chat_jid=activity.chat_jid,
            sender_id=activity.actor_id,
            sender_jid=activity.actor_jid,
            sender_name=activity.actor_name or activity.actor_id or activity.messenger_id,
            text="",
            message_id=activity.target_message_id,
            timestamp_ms=activity.timestamp_ms,
            raw_event_type=activity.raw_event_type,
            raw=activity.raw,
        )

    def _activity_reply_to_tg(self, activity: IncomingMessengerActivity) -> Optional[int]:
        candidates = [activity.target_message_id, *activity.target_message_ids]
        for message_id in candidates:
            if not message_id:
                continue
            tg_message_id = self.store.get_tg_message_id(activity.transport, message_id)
            if tg_message_id:
                return tg_message_id
        return None

    def _should_forward_activity(self, activity: IncomingMessengerActivity) -> bool:
        if activity.kind == "typing":
            return self._dedupe_activity(
                f"typing:{activity.messenger_id}:{activity.actor_id}:{activity.is_typing}",
                5000,
            )
        if activity.kind in {"read_receipt", "e2ee_receipt"}:
            target = activity.target_message_id or activity.text or activity.receipt_type
            return self._dedupe_activity(
                f"receipt:{activity.kind}:{activity.messenger_id}:{activity.actor_id}:{target}",
                15000,
            )
        return True

    def _dedupe_activity(self, key: str, window_ms: int) -> bool:
        now = int(time.time() * 1000)
        last = self._activity_dedupe.get(key, 0)
        if now - last < window_ms:
            return False
        self._activity_dedupe[key] = now
        for old_key, seen_at in list(self._activity_dedupe.items()):
            if now - seen_at > 60000:
                self._activity_dedupe.pop(old_key, None)
        return True

    async def _resolve_topic_display_name(self, message: IncomingMessengerMessage) -> str:
        resolved = await asyncio.to_thread(self.messenger.resolve_topic_display_name, message)
        return resolved or message.sender_name or message.messenger_id

    async def _maybe_rename_existing_topic(self, entry: TopicEntry, message: IncomingMessengerMessage) -> None:
        if entry.topic_id <= 1:
            return
        display_name = await self._resolve_topic_display_name(message)
        if not display_name or display_name == entry.name:
            return
        if not self._should_replace_topic_name(entry.name, display_name, message):
            return

        assert self.bot is not None
        try:
            await self._telegram_call(
                self.bot.edit_forum_topic,
                chat_id=self.config.telegram_group_id,
                message_thread_id=entry.topic_id,
                name=topic_name(display_name, entry.transport),
            )
            self.store.update_topic_name(entry.topic_id, display_name)
            entry.name = display_name
        except TelegramError as exc:
            print(f"[Telegram] Could not rename topic {entry.topic_id}: {exc}")

    @staticmethod
    def _should_replace_topic_name(old_name: str, new_name: str, message: IncomingMessengerMessage) -> bool:
        old = (old_name or "").strip()
        if not old or old == new_name:
            return False
        generic_names = {
            str(message.messenger_id or ""),
            str(message.sender_id or ""),
            str(message.thread_id or ""),
            str(message.chat_jid or ""),
        }
        return old in generic_names or old.isdigit() or "@" in old

    async def _create_forum_topic(self, name: str, transport: str) -> int:
        assert self.bot is not None
        icon_color = 0x6FB9F0 if transport == "e2ee" else 0xFFB86C
        try:
            topic = await self._telegram_call(
                self.bot.create_forum_topic,
                chat_id=self.config.telegram_group_id,
                name=name,
                icon_color=icon_color,
            )
            return topic.message_thread_id
        except TelegramError as exc:
            print(f"[Telegram] Could not create forum topic, using General topic: {exc}")
            await self._notify_general(
                "Could not create Telegram topic. Using General topic instead. "
                "Run /checktopics to verify the group is a forum supergroup and the bot has Manage Topics permission. "
                f"Telegram error: {exc}"
            )
            return 1

    async def _send_topic_intro(self, entry: TopicEntry, message: IncomingMessengerMessage) -> None:
        assert self.bot is not None
        try:
            await self._telegram_call(
                self.bot.send_message,
                chat_id=self.config.telegram_group_id,
                text=format_topic_intro(message),
                message_thread_id=entry.topic_id,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError as exc:
            print(f"[Telegram] Could not send topic intro: {exc}")

    async def _send_inbound_to_telegram(
        self,
        entry: TopicEntry,
        message: IncomingMessengerMessage,
        reply_to_tg_message_id: Optional[int],
        *,
        use_topic: bool = True,
    ) -> Message:
        assert self.bot is not None
        kwargs = {
            "chat_id": self.config.telegram_group_id,
            "text": format_messenger_message(message),
            "parse_mode": ParseMode.HTML,
            "disable_web_page_preview": False,
        }
        if use_topic:
            kwargs["message_thread_id"] = entry.topic_id
        if reply_to_tg_message_id:
            kwargs["reply_parameters"] = ReplyParameters(
                message_id=reply_to_tg_message_id,
                allow_sending_without_reply=True,
            )
        return await self._telegram_call(self.bot.send_message, **kwargs)

    async def _send_inbound_with_topic_recovery(
        self,
        entry: TopicEntry,
        message: IncomingMessengerMessage,
        reply_to_tg_message_id: Optional[int],
    ) -> Message:
        try:
            return await self._send_inbound_to_telegram(entry, message, reply_to_tg_message_id)
        except TelegramError as exc:
            if not self._is_topic_missing_error(exc):
                raise

            self.store.remove_topic(entry.topic_id)
            await self._notify_general(
                f"Telegram topic <code>{entry.topic_id}</code> for <b>{escape_html(entry.name)}</b> no longer exists. "
                "Creating a fresh topic and retrying."
            )

        fresh_entry = await self._get_or_create_topic(message)
        try:
            return await self._send_inbound_to_telegram(fresh_entry, message, reply_to_tg_message_id)
        except TelegramError as exc:
            if not self._is_topic_missing_error(exc):
                raise

            await self._notify_general(
                "Telegram still rejected the new topic with 'message thread not found'. "
                "Sending this Messenger message to the group without a topic. Run /checktopics to verify forum permissions."
            )
            return await self._send_inbound_to_telegram(
                fresh_entry,
                message,
                None,
                use_topic=False,
            )

    async def _send_activity_to_telegram(
        self,
        entry: TopicEntry,
        activity: IncomingMessengerActivity,
        reply_to_tg_message_id: Optional[int],
        *,
        use_topic: bool = True,
    ) -> Message:
        assert self.bot is not None
        kwargs = {
            "chat_id": self.config.telegram_group_id,
            "text": format_messenger_activity(activity),
            "parse_mode": ParseMode.HTML,
            "disable_web_page_preview": True,
        }
        if use_topic:
            kwargs["message_thread_id"] = entry.topic_id
        if reply_to_tg_message_id:
            kwargs["reply_parameters"] = ReplyParameters(
                message_id=reply_to_tg_message_id,
                allow_sending_without_reply=True,
            )
        return await self._telegram_call(self.bot.send_message, **kwargs)

    async def _send_activity_with_topic_recovery(
        self,
        entry: TopicEntry,
        activity: IncomingMessengerActivity,
        reply_to_tg_message_id: Optional[int],
    ) -> Message:
        try:
            return await self._send_activity_to_telegram(entry, activity, reply_to_tg_message_id)
        except TelegramError as exc:
            if not self._is_topic_missing_error(exc):
                raise

            self.store.remove_topic(entry.topic_id)
            await self._notify_general(
                f"Telegram topic <code>{entry.topic_id}</code> for <b>{escape_html(entry.name)}</b> no longer exists. "
                "Creating a fresh topic and retrying."
            )

        fresh_entry = await self._get_or_create_topic(self._activity_topic_message(activity))
        try:
            return await self._send_activity_to_telegram(fresh_entry, activity, reply_to_tg_message_id)
        except TelegramError as exc:
            if not self._is_topic_missing_error(exc):
                raise

            await self._notify_general(
                "Telegram still rejected the new topic with 'message thread not found'. "
                "Sending this Messenger activity to the group without a topic. Run /checktopics to verify forum permissions."
            )
            return await self._send_activity_to_telegram(
                fresh_entry,
                activity,
                None,
                use_topic=False,
            )

    async def forward_telegram_message(self, message: Message) -> ForwardResult:
        if message.chat_id != self.config.telegram_group_id:
            return ForwardResult(False)
        if message.from_user and message.from_user.is_bot:
            return ForwardResult(False)

        topic_id = message.message_thread_id
        if not topic_id:
            return ForwardResult(False, "Send messages inside a mapped forum topic.")

        entry = self.store.get_topic_by_id(topic_id)
        if entry is None:
            return ForwardResult(False, "This topic is not linked to a Messenger conversation.")

        quote = None
        if message.reply_to_message:
            quote = self.store.get_quote_by_tg(message.reply_to_message.message_id)

        if message.sticker:
            return await self._forward_telegram_sticker(message, entry, quote)

        text = telegram_message_to_text(message).strip()
        if not text:
            return ForwardResult(False, "This Telegram message has no bridgeable text content yet.")

        try:
            result = await asyncio.to_thread(self.messenger.send_text, entry, text, quote)
        except Exception as exc:  # noqa: BLE001
            return ForwardResult(False, f"Messenger send failed: {exc}")

        if not isinstance(result, dict) or result.get("error"):
            payload = result.get("payload") if isinstance(result, dict) else result
            return ForwardResult(False, f"Messenger send failed: {payload}")

        payload = result.get("payload") or {}
        messenger_message_id = str(payload.get("messageID") or "")
        if messenger_message_id:
            self.store.save_message(
                message.message_id,
                [messenger_message_id],
                QuoteData(
                    message_id=messenger_message_id,
                    transport=entry.transport,
                    messenger_id=entry.messenger_id,
                    sender_id=self.messenger.self_id,
                    sender_jid="",
                    chat_jid=entry.chat_jid or "",
                    thread_id=entry.thread_id or "",
                ),
            )

        return ForwardResult(True)

    async def _forward_telegram_sticker(
        self,
        message: Message,
        entry: TopicEntry,
        quote: Optional[QuoteData],
    ) -> ForwardResult:
        assert self.bot is not None
        sticker = message.sticker
        if sticker is None:
            return ForwardResult(False)

        filename, mime_type, width, height = self._telegram_sticker_meta(sticker)
        try:
            telegram_file = await self._telegram_call(self.bot.get_file, sticker.file_id)
            file_data = bytes(await telegram_file.download_as_bytearray())
            result = await asyncio.to_thread(
                self.messenger.send_telegram_sticker,
                entry,
                file_data,
                filename,
                mime_type,
                width,
                height,
                quote,
            )
        except Exception as exc:  # noqa: BLE001
            return ForwardResult(False, f"Messenger sticker send failed: {exc}")

        if not isinstance(result, dict) or result.get("error"):
            payload = result.get("payload") if isinstance(result, dict) else result
            return ForwardResult(False, f"Messenger sticker send failed: {payload}")

        payload = result.get("payload") or {}
        messenger_message_id = str(payload.get("messageID") or "")
        if messenger_message_id:
            self.store.save_message(
                message.message_id,
                [messenger_message_id],
                QuoteData(
                    message_id=messenger_message_id,
                    transport=entry.transport,
                    messenger_id=entry.messenger_id,
                    sender_id=self.messenger.self_id,
                    sender_jid="",
                    chat_jid=entry.chat_jid or "",
                    thread_id=entry.thread_id or "",
                ),
            )

        return ForwardResult(True)

    @staticmethod
    def _telegram_sticker_meta(sticker) -> tuple[str, str, int, int]:
        unique_id = str(getattr(sticker, "file_unique_id", "sticker") or "sticker")
        if getattr(sticker, "is_video", False):
            extension = "webm"
            mime_type = "video/webm"
        elif getattr(sticker, "is_animated", False):
            extension = "tgs"
            mime_type = "application/x-tgsticker"
        else:
            extension = "webp"
            mime_type = "image/webp"

        filename = f"telegram-sticker-{unique_id}.{extension}"
        width = int(getattr(sticker, "width", 0) or 0)
        height = int(getattr(sticker, "height", 0) or 0)
        return filename, mime_type, width, height

    def status_html(self) -> str:
        status = "running" if self.messenger.is_running else "stopped"
        err = self.messenger.last_error
        err_line = f"\nlast_error: <code>{escape_html(str(err))}</code>" if err else ""
        return (
            "<b>Messenger bridge status</b>\n"
            f"listener: <code>{status}</code>\n"
            f"facebook_id: <code>{escape_html(self.messenger.self_id or '-')}</code>\n"
            f"topics: <code>{len(self.store.all_topics())}</code>"
            f"{err_line}"
        )

    def topic_list_html(self) -> str:
        topics = self.store.all_topics()
        if not topics:
            return "No Messenger topics have been linked yet."
        lines = ["<b>Messenger topics</b>"]
        for entry in topics:
            lines.append(
                f"- <b>{escape_html(truncate(entry.name, 80))}</b> "
                f"topic=<code>{entry.topic_id}</code> "
                f"transport=<code>{entry.transport}</code> "
                f"id=<code>{escape_html(truncate(entry.messenger_id, 80))}</code>"
            )
        return truncate("\n".join(lines), 4096)

    async def topic_permissions_html(self) -> str:
        assert self.bot is not None
        chat = await self._telegram_call(self.bot.get_chat, self.config.telegram_group_id)
        me = await self._telegram_call(self.bot.get_me)
        member = await self._telegram_call(self.bot.get_chat_member, self.config.telegram_group_id, me.id)

        raw_chat_type = getattr(chat, "type", "")
        chat_type = getattr(raw_chat_type, "value", str(raw_chat_type))
        raw_status = getattr(member, "status", "")
        status = getattr(raw_status, "value", str(raw_status))
        is_forum = bool(getattr(chat, "is_forum", False))
        is_admin = status in {"administrator", "creator", "owner"}
        can_manage_topics = status in {"creator", "owner"} or bool(getattr(member, "can_manage_topics", False))

        lines = [
            "<b>Telegram topic check</b>",
            f"chat_type: <code>{escape_html(chat_type)}</code>",
            f"is_forum: <code>{str(is_forum).lower()}</code>",
            f"bot_status: <code>{escape_html(status)}</code>",
            f"can_manage_topics: <code>{str(can_manage_topics).lower()}</code>",
            "",
        ]

        problems: list[str] = []
        if chat_type != "supergroup":
            problems.append("Group must be a supergroup.")
        if not is_forum:
            problems.append("Enable Topics in Telegram group settings.")
        if not is_admin:
            problems.append("Promote the bot to admin.")
        if is_admin and not can_manage_topics:
            problems.append("Grant the bot the Manage Topics permission.")

        if problems:
            lines.append("<b>Needs fixing</b>")
            lines.extend(f"- {escape_html(problem)}" for problem in problems)
        else:
            lines.append("<b>OK</b>: bot can create forum topics automatically.")

        return "\n".join(lines)

    def topic_info_html(self, topic_id: int) -> str:
        entry = self.store.get_topic_by_id(topic_id)
        if entry is None:
            return "This topic is not linked to a Messenger conversation."
        return (
            f"<b>{escape_html(entry.name)}</b>\n"
            f"topic: <code>{entry.topic_id}</code>\n"
            f"transport: <code>{entry.transport}</code>\n"
            f"messenger_id: <code>{escape_html(entry.messenger_id)}</code>\n"
            f"thread_id: <code>{escape_html(entry.thread_id or '-')}</code>\n"
            f"chat_jid: <code>{escape_html(entry.chat_jid or '-')}</code>"
        )

    def delete_topic_mapping_html(self, topic_id: int) -> str:
        removed = self.store.remove_topic(topic_id)
        if removed is None:
            return "This topic is not linked to a Messenger conversation."
        return f"Deleted mapping for <b>{escape_html(removed.name)}</b>."

    @staticmethod
    def _is_topic_missing_error(exc: TelegramError) -> bool:
        text = str(exc).lower()
        return (
            "message thread not found" in text
            or "thread not found" in text
            or "topic_closed" in text
            or "topic closed" in text
        )

    async def _notify_general(self, text: str) -> None:
        if self.bot is None:
            return
        try:
            await self._telegram_call(
                self.bot.send_message,
                chat_id=self.config.telegram_group_id,
                text=escape_html(text),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError as exc:
            print(f"[Telegram] Notification failed: {exc}")

    @staticmethod
    async def _telegram_call(fn, *args, **kwargs):
        for attempt in range(5):
            try:
                return await fn(*args, **kwargs)
            except RetryAfter as exc:
                if attempt == 4:
                    raise
                await asyncio.sleep(float(exc.retry_after) + 1.0)