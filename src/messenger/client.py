from __future__ import annotations

import base64
import inspect
import sys
import json
import logging
import threading
import traceback
from importlib import import_module
from typing import Callable, Optional

from config import AppConfig
from models import IncomingMessengerMessage, QuoteData, TopicEntry


MessengerEventCallback = Callable[[dict], None]
logger = logging.getLogger(__name__)


class MessengerClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.data_fb: Optional[dict] = None
        self.self_id = ""
        self.listener = None
        self.e2ee_sender = None
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[BaseException] = None
        self._event_callback: Optional[MessengerEventCallback] = None
        self._user_name_cache: dict[str, str] = {}
        self._thread_name_cache: dict[str, str] = {}

    @property
    def last_error(self) -> Optional[BaseException]:
        return self._last_error

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _prepare_fbchat_import(self) -> None:
        if self.config.fbchat_v2_src_path is None:
            logger.debug("FBCHAT_V2_SRC_PATH is not set; relying on installed fbchat-v2/Python import path")
            return
        if not self.config.fbchat_v2_src_path.exists():
            raise RuntimeError(f"FBCHAT_V2_SRC_PATH does not exist: {self.config.fbchat_v2_src_path}")
        core_file = self.config.fbchat_v2_src_path / "_core" / "_session.py"
        e2ee_file = self.config.fbchat_v2_src_path / "_messaging" / "_listening_e2ee.py"
        if not core_file.exists() or not e2ee_file.exists():
            raise RuntimeError(
                "FBCHAT_V2_SRC_PATH must point to the fbchat-v2/src folder "
                f"that contains _core and _messaging, got: {self.config.fbchat_v2_src_path}"
            )
        path = str(self.config.fbchat_v2_src_path)
        if path not in sys.path:
            sys.path.insert(0, path)
        logger.debug("Prepared fbchat-v2 import path: %s", path)

    @staticmethod
    def _import_fbchat_module(module_name: str):
        root_name = module_name.split(".", 1)[0]
        try:
            return import_module(module_name)
        except ModuleNotFoundError as top_level_exc:
            if top_level_exc.name not in {root_name, module_name}:
                raise
            try:
                return import_module(f"fbchat_v2.{module_name}")
            except ModuleNotFoundError as namespaced_exc:
                namespaced_root = f"fbchat_v2.{root_name}"
                namespaced_name = f"fbchat_v2.{module_name}"
                if namespaced_exc.name in {"fbchat_v2", namespaced_root, namespaced_name}:
                    raise top_level_exc from namespaced_exc
                raise

    def login(self) -> None:
        self._prepare_fbchat_import()
        logger.info("Logging in to Messenger with fbchat-v2")

        try:
            data_get_home = self._import_fbchat_module("_core._session").dataGetHome
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Could not import fbchat-v2 internal modules. Install fbchat-v2 from PyPI "
                "or set FBCHAT_V2_SRC_PATH to the fbchat-v2/src folder. "
                "For PyPI mode, set FBCHAT_V2_USE_PYPI=1 after installing requirements."
            ) from exc

        data_fb = data_get_home(self.config.facebook_cookie)
        facebook_id = str(data_fb.get("FacebookID") or "")
        if not facebook_id or "Unable to retrieve" in facebook_id:
            raise RuntimeError("Could not read FacebookID from cookie. Refresh FACEBOOK_COOKIE.")

        self.data_fb = data_fb
        self.self_id = facebook_id
        logger.info("Messenger login complete: facebook_id=%s", self.self_id)

    def start(self, event_callback: MessengerEventCallback) -> None:
        if self.data_fb is None:
            self.login()

        listening_e2ee_event = self._import_fbchat_module("_messaging._listening_e2ee").listeningE2EEEvent
        e2ee_sender = self._import_fbchat_module("_messaging._send_e2ee").api

        self._event_callback = event_callback
        self.listener = listening_e2ee_event(
            self.data_fb,
            log_level=self.config.fbchat_e2ee_log_level,
            device_path=self.config.fbchat_e2ee_device_path,
            e2ee_memory_only=self.config.fbchat_e2ee_memory_only,
            enable_e2ee=self.config.fbchat_enable_e2ee,
            binary_path=self.config.fbchat_e2ee_bin,
        )
        self.listener.on_message(event_callback)
        self.e2ee_sender = e2ee_sender(listener=self.listener)
        logger.info(
            "Messenger listener configured: e2ee_enabled=%s memory_only=%s binary=%s",
            self.config.fbchat_enable_e2ee,
            self.config.fbchat_e2ee_memory_only,
            self.config.fbchat_e2ee_bin or "auto/default",
        )

        self._thread = threading.Thread(
            target=self._run_listener,
            name="messenger-e2ee-listener",
            daemon=True,
        )
        self._thread.start()

    def _run_listener(self) -> None:
        try:
            logger.info("Messenger listener connecting MQTT")
            self.listener.connect_mqtt()
        except BaseException as exc:  # noqa: BLE001 - surface listener thread failures
            self._last_error = exc
            logger.exception("Messenger listener stopped with error")
            traceback.print_exc()
            if self._event_callback:
                self._event_callback({
                    "type": "error",
                    "data": {"message": str(exc), "source": "listener"},
                })

    def stop(self) -> None:
        if self.listener is not None:
            try:
                logger.info("Stopping Messenger listener")
                self.listener.stop()
            except Exception:  # noqa: BLE001
                pass

    def resolve_user_name(self, user_id: str) -> Optional[str]:
        clean_id = str(user_id or "").strip()
        if not clean_id or self.data_fb is None:
            return None
        if clean_id in self._user_name_cache:
            return self._user_name_cache[clean_id]

        info = self._request_user_info(clean_id)
        if info is None:
            return None
        name = str(info.get("nameUser") or info.get("firstName") or "").strip()
        if name:
            self._user_name_cache[clean_id] = name
            return name
        return None

    def _request_user_info(self, user_id: str) -> Optional[dict]:
        if self.data_fb is None:
            return None

        try:
            requests = import_module("requests")
            utils = self._import_fbchat_module("_core._utils")
            data_form = utils.formAll(self.data_fb, requireGraphql=False)
            data_form["ids[0]"] = user_id

            response = requests.post(
                "https://www.facebook.com/chat/user_info/",
                headers=utils.Headers(data_form),
                timeout=5,
                data=data_form,
                cookies=utils.parse_cookie_string(self.data_fb["cookieFacebook"]),
                verify=True,
            )
            raw = response.text.split("for (;;);", 1)[-1]
            profile = json.loads(raw)["payload"]["profiles"][str(user_id)]
            return {
                "idUser": profile.get("id"),
                "nameUser": profile.get("name"),
                "firstName": profile.get("firstName"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not resolve Messenger user name for %s: %s", user_id, exc)
            return None

    def resolve_thread_name(self, thread_id: str) -> Optional[str]:
        clean_id = str(thread_id or "").strip()
        if not clean_id or self.data_fb is None:
            return None
        if clean_id in self._thread_name_cache:
            return self._thread_name_cache[clean_id]

        try:
            fbt = getattr(self.listener, "fbt", None)
            if not isinstance(fbt, dict) or not fbt:
                return None
            all_threads = (fbt.get("dataAllThread") or {}) if isinstance(fbt, dict) else {}
            ids = [str(item) for item in (all_threads.get("threadIDList") or [])]
            names = [str(item).strip() for item in (all_threads.get("threadNameList") or [])]
            for index, candidate_id in enumerate(ids):
                if candidate_id == clean_id and index < len(names) and names[index]:
                    self._thread_name_cache[clean_id] = names[index]
                    return names[index]

            data_get = fbt.get("dataGet") if isinstance(fbt, dict) else None
            if data_get:
                snapshot_name = self._resolve_name_from_thread_snapshot(data_get, clean_id)
                if snapshot_name:
                    self._thread_name_cache[clean_id] = snapshot_name
                    return snapshot_name
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not resolve Messenger thread name for %s: %s", clean_id, exc)
        return None

    def _resolve_name_from_thread_snapshot(self, data_get: str, lookup_id: str) -> Optional[str]:
        try:
            nodes = json.loads(data_get)["o0"]["data"]["viewer"]["message_threads"]["nodes"]
        except (KeyError, TypeError, json.JSONDecodeError):
            return None

        for node in nodes:
            if not isinstance(node, dict):
                continue
            thread_key = node.get("thread_key") or {}
            key_values = {
                str(thread_key.get("thread_fbid") or ""),
                str(thread_key.get("other_user_id") or ""),
                str(thread_key.get("other_user_fbid") or ""),
                str(node.get("id") or ""),
            }
            if lookup_id not in key_values:
                continue

            thread_name = str(node.get("name") or "").strip()
            if thread_name:
                return thread_name

            participant_name = self._participant_name_from_thread_node(node)
            if participant_name:
                return participant_name
        return None

    def _participant_name_from_thread_node(self, node: dict) -> Optional[str]:
        edges = (((node.get("all_participants") or {}).get("edges")) or [])
        fallback_name = None
        for edge in edges:
            actor = ((edge or {}).get("node") or {}).get("messaging_actor") or {}
            actor_id = str(actor.get("id") or "").strip()
            actor_name = str(actor.get("name") or "").strip()
            if not actor_name:
                continue
            if not fallback_name:
                fallback_name = actor_name
            if actor_id and actor_id != self.self_id:
                return actor_name
        return fallback_name

    def resolve_topic_display_name(self, message: IncomingMessengerMessage) -> Optional[str]:
        event_thread_name = str(message.thread_name or "").strip()
        if event_thread_name:
            self._thread_name_cache[message.thread_id] = event_thread_name
            return event_thread_name

        thread_name = self.resolve_thread_name(message.thread_id)
        if thread_name:
            return thread_name

        if self._is_regular_group_message(message):
            return self._group_fallback_name(message.thread_id or message.messenger_id)

        for candidate_id in self._candidate_profile_ids(message):
            user_name = self.resolve_user_name(candidate_id)
            if user_name:
                return user_name
        return None

    @staticmethod
    def _is_regular_group_message(message: IncomingMessengerMessage) -> bool:
        if message.transport != "regular":
            return False
        thread_id = str(message.thread_id or message.messenger_id or "").strip()
        sender_id = str(message.sender_id or "").strip()
        if not thread_id:
            return False
        if sender_id and thread_id != sender_id:
            return True
        return message.thread_type not in {0, 1}

    @staticmethod
    def _group_fallback_name(thread_id: str) -> str:
        clean_id = str(thread_id or "").strip()
        return f"Messenger group {clean_id}" if clean_id else "Messenger group"

    def _candidate_profile_ids(self, message: IncomingMessengerMessage) -> list[str]:
        candidates = [
            message.sender_id,
            message.thread_id,
            self._jid_user(message.sender_jid),
            self._jid_user(message.chat_jid),
            self._jid_user(message.messenger_id),
            message.messenger_id,
        ]

        seen: set[str] = set()
        result: list[str] = []
        for candidate in candidates:
            clean = str(candidate or "").strip()
            if not clean or clean == self.self_id or clean in seen:
                continue
            if not clean.isdigit():
                continue
            seen.add(clean)
            result.append(clean)
        return result

    @staticmethod
    def _jid_user(value: Optional[str]) -> str:
        text = str(value or "").strip()
        if "@" not in text:
            return text
        return text.split("@", 1)[0]

    def send_text(self, entry: TopicEntry, text: str, quote: Optional[QuoteData] = None) -> dict:
        if self.listener is None:
            raise RuntimeError("Messenger listener is not connected")

        content = text.strip()
        if not content:
            raise ValueError("Cannot send an empty Messenger message")

        if entry.transport == "e2ee":
            if self.e2ee_sender is None:
                raise RuntimeError("E2EE sender is not ready")
            reply_id, reply_sender = self._e2ee_reply_parts(quote)
            logger.info(
                "Sending E2EE Messenger text: chat_jid=%s reply_id=%s timeout=%s text_len=%s",
                entry.chat_jid or entry.messenger_id,
                reply_id or "-",
                self.config.fbchat_e2ee_send_timeout,
                len(content),
            )
            return self._send_e2ee_text(
                chat_jid=entry.chat_jid or entry.messenger_id,
                content=content,
                reply_id=reply_id,
                reply_sender=reply_sender,
            )

        reply_id = quote.message_id if quote and quote.transport == "regular" else ""
        logger.info(
            "Sending regular Messenger text: thread_id=%s reply_id=%s text_len=%s",
            entry.thread_id or entry.messenger_id,
            reply_id or "-",
            len(content),
        )
        data = self.listener.send_message(
            int(entry.thread_id or entry.messenger_id),
            content,
            reply_to_id=reply_id,
        )
        return {
            "success": 1,
            "payload": {
                "messageID": data.get("messageId") or data.get("id"),
                "timestamp": data.get("timestampMs") or data.get("timestamp") or 0,
            },
        }

    def _send_e2ee_text(self, chat_jid: str, content: str, reply_id: str = "", reply_sender: str = "") -> dict:
        if self.e2ee_sender is None:
            raise RuntimeError("E2EE sender is not ready")

        kwargs = {
            "chat_jid": chat_jid,
            "contentSend": content,
            "replyMessage": reply_id,
            "replySenderJid": reply_sender,
        }
        timeout = self.config.fbchat_e2ee_send_timeout
        try:
            parameters = inspect.signature(self.e2ee_sender.send).parameters
        except (TypeError, ValueError):
            parameters = {}

        if "timeout" in parameters:
            kwargs["timeout"] = timeout
        else:
            logger.debug("fbchat-v2 E2EE send() has no timeout parameter; calling without timeout")

        try:
            return self.e2ee_sender.send(**kwargs)
        except TypeError as exc:
            if "timeout" not in kwargs or "unexpected keyword argument 'timeout'" not in str(exc):
                raise
            kwargs.pop("timeout", None)
            logger.warning("fbchat-v2 E2EE send() rejected timeout; retrying without timeout")
            return self.e2ee_sender.send(**kwargs)

    def send_telegram_sticker(
        self,
        entry: TopicEntry,
        file_data: bytes,
        filename: str,
        mime_type: str,
        width: int = 0,
        height: int = 0,
        quote: Optional[QuoteData] = None,
    ) -> dict:
        if self.listener is None:
            raise RuntimeError("Messenger listener is not connected")
        if not file_data:
            raise ValueError("Telegram sticker file is empty")

        encoded = base64.b64encode(file_data).decode("ascii")
        clean_mime = (mime_type or "application/octet-stream").lower()
        clean_filename = filename or "telegram-sticker.bin"

        if entry.transport == "e2ee":
            reply_id, reply_sender = self._e2ee_reply_parts(quote)
            chat_jid = entry.chat_jid or entry.messenger_id
            logger.info(
                "Sending E2EE Messenger sticker/media: chat_jid=%s filename=%s mime=%s bytes=%s reply_id=%s",
                chat_jid,
                clean_filename,
                clean_mime,
                len(file_data),
                reply_id or "-",
            )
            if clean_mime == "image/webp" or clean_filename.lower().endswith(".webp"):
                return self._call_bridge_send("sendE2EESticker", {
                    "chatJid": chat_jid,
                    "data": encoded,
                    "mimeType": clean_mime or "image/webp",
                    "width": width,
                    "height": height,
                    "replyToId": reply_id,
                    "replyToSenderJid": reply_sender,
                })
            if clean_mime.startswith("video/"):
                return self._call_bridge_send("sendE2EEVideo", {
                    "chatJid": chat_jid,
                    "data": encoded,
                    "mimeType": clean_mime,
                    "caption": "",
                    "width": width,
                    "height": height,
                    "replyToId": reply_id,
                    "replyToSenderJid": reply_sender,
                })
            return self._call_bridge_send("sendE2EEDocument", {
                "chatJid": chat_jid,
                "data": encoded,
                "filename": clean_filename,
                "mimeType": clean_mime,
                "replyToId": reply_id,
                "replyToSenderJid": reply_sender,
            })

        thread_id = int(entry.thread_id or entry.messenger_id)
        reply_id = quote.message_id if quote and quote.transport == "regular" else ""
        logger.info(
            "Sending regular Messenger sticker/media: thread_id=%s filename=%s mime=%s bytes=%s reply_id=%s",
            thread_id,
            clean_filename,
            clean_mime,
            len(file_data),
            reply_id or "-",
        )
        if clean_mime.startswith("image/"):
            return self._call_bridge_send("sendImage", {
                "threadId": thread_id,
                "data": encoded,
                "filename": clean_filename,
                "caption": "",
                "replyToId": reply_id,
            })
        return self._call_bridge_send("sendFile", {
            "threadId": thread_id,
            "data": encoded,
            "filename": clean_filename,
            "mimeType": clean_mime,
            "caption": "Telegram sticker",
            "replyToId": reply_id,
        })

    def send_reaction(self, quote: QuoteData, emoji: str) -> dict:
        if self.listener is None:
            raise RuntimeError("Messenger listener is not connected")
        if not quote.message_id:
            raise ValueError("Cannot react without a Messenger message ID")

        clean_emoji = str(emoji or "")
        if quote.transport == "e2ee":
            message_id, sender_jid = self._e2ee_reply_parts(quote)
            if not message_id or not sender_jid:
                raise RuntimeError("Cannot send E2EE reaction without quote sender JID")
            chat_jid = quote.chat_jid or quote.messenger_id
            if not chat_jid:
                raise RuntimeError("Cannot send E2EE reaction without chat JID")
            logger.info(
                "Sending E2EE Messenger reaction: chat_jid=%s message_id=%s sender_jid=%s emoji=%s",
                chat_jid,
                message_id,
                sender_jid,
                clean_emoji or "<remove>",
            )
            return self._call_bridge_send("sendE2EEReaction", {
                "chatJid": chat_jid,
                "messageId": message_id,
                "senderJid": sender_jid,
                "emoji": clean_emoji,
            })

        thread_id = int(quote.thread_id or quote.messenger_id)
        logger.info(
            "Sending regular Messenger reaction: thread_id=%s message_id=%s emoji=%s",
            thread_id,
            quote.message_id,
            clean_emoji or "<remove>",
        )
        return self._call_bridge_send("sendReaction", {
            "threadId": thread_id,
            "messageId": quote.message_id,
            "emoji": clean_emoji,
        })

    def _call_bridge_send(self, method: str, params: dict) -> dict:
        bridge = getattr(self.listener, "_bridge", None)
        if bridge is None:
            raise RuntimeError("Messenger bridge RPC is not connected")
        timeout = self.config.fbchat_e2ee_send_timeout if method.startswith("sendE2EE") else 60.0
        logger.debug("Calling Messenger bridge RPC: method=%s timeout=%s", method, timeout)
        data = bridge.call(method, params, timeout=timeout)
        return self._normalize_send_result(data)

    def _e2ee_reply_parts(self, quote: Optional[QuoteData]) -> tuple[str, str]:
        if quote is None or quote.transport != "e2ee" or not quote.message_id:
            return "", ""

        sender_jid = (quote.sender_jid or "").strip()
        if not sender_jid and quote.sender_id == self.self_id:
            sender_jid = self._self_e2ee_jid()
        if not sender_jid:
            logger.warning("E2EE reply metadata skipped for %s: missing sender JID", quote.message_id)
            return "", ""
        return quote.message_id, sender_jid

    def _self_e2ee_jid(self) -> str:
        return f"{self.self_id}@s.whatsapp.net" if self.self_id else ""

    def self_sender_jid(self, transport: str) -> str:
        return self._self_e2ee_jid() if transport == "e2ee" else ""

    @staticmethod
    def _normalize_send_result(data: dict) -> dict:
        payload = data or {}
        return {
            "success": 1,
            "payload": {
                "messageID": payload.get("messageId") or payload.get("messageID") or payload.get("id"),
                "timestamp": payload.get("timestampMs") or payload.get("timestamp") or 0,
            },
        }