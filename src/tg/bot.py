from __future__ import annotations

from telegram.ext import Application

from bridge import MessengerTelegramBridge
from config import AppConfig
from store import BridgeStore
from tg.handlers import TelegramHandlers


def build_application(
    config: AppConfig,
    bridge: MessengerTelegramBridge,
    store: BridgeStore,
) -> Application:
    async def post_init(application: Application) -> None:
        await bridge.start(application)

    async def post_shutdown(application: Application) -> None:
        await bridge.shutdown(application)

    application = (
        Application.builder()
        .token(config.telegram_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    TelegramHandlers(config, bridge, store).register(application)
    return application