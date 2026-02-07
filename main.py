#!/usr/bin/env python3
import asyncio
import logging
import signal

import discord

from modules import TZBot

# Logger setup
fileHandler = logging.FileHandler(filename="bot.log", encoding="utf-8", mode="a")
dateFormat = "%d.%m.%Y %H:%M:%S"
formatter = logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", dateFormat, style="{")

fileHandler.setFormatter(formatter)
discord.utils.setup_logging(level=logging.INFO, root=True)
logging.getLogger().addHandler(fileHandler)

log = logging.getLogger(__name__)


async def main() -> None:
    client = TZBot(command_prefix="tz!", help_command=None, intents=discord.Intents.all())

    stopEvent = asyncio.Event()
    def exitHandler() -> None:
        log.info("Received signal, stopping!")
        stopEvent.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, exitHandler)
    loop.add_signal_handler(signal.SIGTERM, exitHandler)

    asyncio.create_task(client.startRunning())
    try:
        await stopEvent.wait()
    finally:
        exit(0)



asyncio.run(main())
