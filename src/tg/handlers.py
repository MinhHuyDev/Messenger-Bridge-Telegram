from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, MessageReactionHandler, filters

from bridge import MessengerTelegramBridge
from config import AppConfig
from store import BridgeStore


logger = logging.getLogger(__name__)


class TelegramHandlers:
    def __init__(self, config: AppConfig, bridge: MessengerTelegramBridge, store: BridgeStore) -> None:
        self.config = config
        self.bridge = bridge
        self.store = store

    def register(self, application: Application) -> None:
        application.add_handler(CommandHandler(["start", "help"], self.help_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("checktopics", self.check_topics_command))
        application.add_handler(CommandHandler("topic", self.topic_command))
        application.add_handler(MessageReactionHandler(self.reaction_handler))
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self.message_handler))

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        logger.info("Telegram command /help: chat_id=%s message_id=%s", message.chat_id, message.message_id)
        await message.reply_text(
            "Messenger <-> Telegram bridge\n"
            "/status - show listener status\n"
            "/checktopics - check topic creation permissions\n"
            "/topic list - list mapped topics\n"
            "/topic info - show current topic mapping\n"
            "/topic delete - delete current topic mapping\n\n"
            "Send messages or Telegram stickers inside a mapped forum topic to forward them to Messenger. "
            "React to bridged Telegram messages to update the reaction on Messenger.",
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.chat_id != self.config.telegram_group_id:
            return
        logger.info("Telegram command /status: topic_id=%s message_id=%s", message.message_thread_id or "-", message.message_id)
        await message.reply_text(self.bridge.status_html(), parse_mode=ParseMode.HTML)

    async def check_topics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.chat_id != self.config.telegram_group_id:
            return
        logger.info("Telegram command /checktopics: topic_id=%s message_id=%s", message.message_thread_id or "-", message.message_id)
        await message.reply_text(
            await self.bridge.topic_permissions_html(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    async def topic_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.chat_id != self.config.telegram_group_id:
            return

        arg = (context.args[0].lower() if context.args else "list")
        topic_id = message.message_thread_id
        logger.info("Telegram command /topic %s: topic_id=%s message_id=%s", arg, topic_id or "-", message.message_id)

        if arg == "list":
            await message.reply_text(
                self.bridge.topic_list_html(),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        if arg == "info":
            if not topic_id:
                await message.reply_text("Use /topic info inside a forum topic.")
                return
            await message.reply_text(
                self.bridge.topic_info_html(topic_id),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        if arg == "delete":
            if not topic_id:
                await message.reply_text("Use /topic delete inside a forum topic.")
                return
            await message.reply_text(
                self.bridge.delete_topic_mapping_html(topic_id),
                parse_mode=ParseMode.HTML,
            )
            return

        await message.reply_text("Usage: /topic list | /topic info | /topic delete")

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.chat_id != self.config.telegram_group_id:
            return
        logger.debug(
            "Telegram update received: chat_id=%s topic_id=%s message_id=%s from_bot=%s",
            message.chat_id,
            message.message_thread_id or "-",
            message.message_id,
            bool(message.from_user and message.from_user.is_bot),
        )
        result = await self.bridge.forward_telegram_message(message)
        if not result.ok and result.message:
            logger.info("Telegram message replied with bridge error: message_id=%s error=%s", message.message_id, result.message)
            await message.reply_text(result.message)

    async def reaction_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reaction = update.message_reaction
        if reaction is None:
            return
        logger.debug(
            "Telegram reaction update received: chat_id=%s message_id=%s old=%s new=%s",
            getattr(getattr(reaction, "chat", None), "id", "-"),
            reaction.message_id,
            reaction.old_reaction,
            reaction.new_reaction,
        )
        result = await self.bridge.forward_telegram_reaction(reaction)
        if not result.ok and result.message:
            logger.info("Telegram reaction bridge error: message_id=%s error=%s", reaction.message_id, result.message)