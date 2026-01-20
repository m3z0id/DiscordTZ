import asyncio
import datetime
import functools
import inspect
import json
from pathlib import Path
from typing import Final

import discord

from database.stats.StatsData import StatsData
from shared.Helpers import Helpers
from shell.Logger import Logger


from typing import ParamSpec, TypeVar, Callable, Coroutine, Any

P = ParamSpec("P")
R = TypeVar("R")

def collectCommandStats(func: Callable[P, Coroutine[Any, Any, bool]]) -> Callable[P, Coroutine[Any, Any, bool]]:
    if not callable(func) or not inspect.iscoroutinefunction(func):
        raise RuntimeError(f"{func.__name__} is not compatible!")

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        boundArgs = inspect.signature(func).bind(*args, **kwargs)
        boundArgs.apply_defaults()
        ctx: discord.ApplicationContext = boundArgs.arguments.get("ctx")

        qualifiedName = ctx.command.qualified_name
        statsDbInstance: "StatsDatabase" = Helpers.tzBot.statsDb

        Logger.log(f"Executing command \"{qualifiedName}\"...")
        await statsDbInstance.addRanCommandName(qualifiedName)
        result: R = await func(*args, **kwargs)
        if result:
            await statsDbInstance.addSuccessfulCommandExecution()
            Logger.success(f"Execution of \"{qualifiedName}\" was successful!")
        else:
            await statsDbInstance.addFailedCommandExecution()
            Logger.error(f"Execution of \"{qualifiedName}\" failed!")
        return result

    return wrapper

class StatsDatabase:
    STATS_DIR: Final[Path] = Path("stats/")

    def __init__(this) -> None:
        this.STATS_DIR.mkdir(parents=True, exist_ok=True)
        asyncio.create_task(this.rotateCurrentDateFile())

    async def getCurrentDateFile(this) -> None:
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
        this.currentStatsData, this.currentHourFile, _ = await StatsData.loadStatsAtDate(now)

    async def dumpCurrent(this) -> None:
        with this.currentHourFile.open("w") as file:
            file.write(json.dumps(this.currentStatsData.__dict__))

    async def rotateCurrentDateFile(this) -> None:
        while True:
            try:
                now = datetime.datetime.now()
                nextHour = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)

                secondsDelta = (nextHour - now).total_seconds()

                await this.getCurrentDateFile()
                await asyncio.sleep(secondsDelta + 10)

            except Exception as e:
                Logger.error(f"Error thrown while rotating current date file: {e!s}")
                await this.dumpCurrent()

    async def addSuccessfulRequest(this) -> None:
        this.currentStatsData.successfulRequestCount += 1
        await this.dumpCurrent()

    async def addFailedRequest(this) -> None:
        this.currentStatsData.failedRequestCount += 1
        await this.dumpCurrent()

    async def addRequestCountry(this, country: str) -> None:
        this.currentStatsData.requestCountries[country] = this.currentStatsData.requestCountries.get(country, 0) + 1
        await this.dumpCurrent()

    async def addEstablishedKnownRequestType(this, requestType: str) -> None:
        this.currentStatsData.establishedKnownRequestTypes[requestType] = this.currentStatsData.establishedKnownRequestTypes.get(requestType, 0) + 1
        await this.dumpCurrent()

    async def addProtocol(this, protocol: str) -> None:
        if protocol not in {"TCP", "UDP"}:
            return

        this.currentStatsData.protocols[protocol] = this.currentStatsData.protocols.get(protocol, 0) + 1
        await this.dumpCurrent()

    async def addReceivedDataBandwidth(this, bytesDataSize: int) -> None:
        this.currentStatsData.receivedDataBandwidth += bytesDataSize
        await this.dumpCurrent()

    async def addSentDataBandwidth(this, bytesDataSize: int) -> None:
        this.currentStatsData.sentDataBandwidth += bytesDataSize
        await this.dumpCurrent()

    async def addSuccessfulCommandExecution(this) -> None:
        this.currentStatsData.successfulCommandExecutionCount += 1
        await this.dumpCurrent()

    async def addFailedCommandExecution(this) -> None:
        this.currentStatsData.failedCommandExecutionCount += 1
        await this.dumpCurrent()

    async def addRanCommandName(this, commandName: str) -> None:
        this.currentStatsData.ranCommandNames[commandName] = this.currentStatsData.ranCommandNames.get(commandName, 0) + 1
        await this.dumpCurrent()