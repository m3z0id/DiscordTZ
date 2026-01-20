#!/usr/bin/env python3
import asyncio

import discord

from modules.modChroma import Chroma
from modules.TZBot import TZBot
from shared.Helpers import Helpers
from shell.Logger import Logger
from shell.Shell import Shell


async def main() -> None:
    # Dependency Check
    if not Helpers.BMPGEN_EXEC_FILE.is_file():
        Logger.warning(f"BMPGen executable not found at {Helpers.BMPGEN_EXEC_FILE}")
    if not Helpers.MAGICK_EXEC_FILE.is_file():
        Logger.warning(f"ImageMagick executable not found at {Helpers.MAGICK_EXEC_FILE}")
    if not Chroma.CHROMA_EXEC.is_file():
        Logger.warning(f"Chroma executable not found at {Chroma.CHROMA_EXEC}")

    shellTask = asyncio.create_task(Shell().run_async())
    client = TZBot(command_prefix="tz!", help_command=None, intents=discord.Intents.all())
    botTask = asyncio.create_task(client.startRunning())

    tasks = [shellTask, botTask]
    try:
        await asyncio.gather(*tasks)
    except Exception as e:  # noqa: BLE001
        Logger.error(f"Unhandled exception: {e}")


asyncio.run(main())
