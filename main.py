#!/usr/bin/env python3
import asyncio

import discord

from modules.TZBot import TZBot
from shell.Logger import Logger
from shell.Shell import Shell


async def main() -> None:
    shellTask = asyncio.create_task(Shell().run_async())
    client = TZBot(command_prefix="tz!", help_command=None, intents=discord.Intents.all())
    botTask = asyncio.create_task(client.startRunning())

    tasks = [shellTask, botTask]
    try:
        await asyncio.gather(*tasks)
    except Exception as e:  # noqa: BLE001
        Logger.error(f"Unhandled exception: {e}")


asyncio.run(main())
