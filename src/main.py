from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
	sys.path.insert(0, str(HERE))

from bridge import MessengerTelegramBridge
from config import load_config
from messenger.client import MessengerClient
from store import BridgeStore
from tg.bot import build_application


def main() -> None:
	config = load_config()
	store = BridgeStore(
		config.store_path,
		message_cache_limit=config.message_cache_limit,
	)
	messenger = MessengerClient(config)
	bridge = MessengerTelegramBridge(config, store, messenger)
	application = build_application(config, bridge, store)

	print("+----------------------------------------+")
	print("| Messenger <-> Telegram Bridge          |")
	print("| fbchat-v2 E2EE listener/send enabled   |")
	print("+----------------------------------------+")
	application.run_polling(allowed_updates=["message"], close_loop=False)


if __name__ == "__main__":
	main()
