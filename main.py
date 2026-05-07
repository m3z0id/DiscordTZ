#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import discord

from modules import TZBot
from shared import applySandbox

# Logger setup
fileHandler = logging.FileHandler(filename="bot.log", encoding="utf-8", mode="a")
dateFormat = "%d.%m.%Y %H:%M:%S"
formatter = logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", dateFormat, style="{")

fileHandler.setFormatter(formatter)
discord.utils.setup_logging(level=logging.INFO, root=True)
logging.getLogger().addHandler(fileHandler)

log = logging.getLogger(__name__)


async def main() -> None:
    applySandbox()

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-only", action="store_true", help="Run in API-only mode.")
    parser.add_argument("--no-pidfile", action="store_true", help="Do not patch the PID file.")

    args = parser.parse_args()

    client = TZBot(Path(__file__).parent, command_prefix="tz!", help_command=None, intents=discord.Intents.all())

    stopEvent = asyncio.Event()
    def exitHandler() -> None:
        log.info("Received signal, stopping!")
        stopEvent.set()

    def restartHandler() -> None:
        log.info("Received SIGUSR1, restarting!")
        os.execvp(sys.executable, [sys.executable] + sys.argv)

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, exitHandler)
    loop.add_signal_handler(signal.SIGTERM, exitHandler)
    loop.add_signal_handler(signal.SIGUSR1, restartHandler)

    asyncio.create_task(client.startRunning(apiOnly=args.api_only, pidFile=not args.no_pidfile))
    try:
        await stopEvent.wait()
    finally:
        exit(0)

asyncio.run(main())
