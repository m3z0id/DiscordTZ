import datetime
import logging
from typing import Optional, ClassVar, cast

import discord
import pytz
from discord import app_commands
from discord.ext import commands

from dtypes.Types import UInt64
from modules import TZBot
from shared import MAX_SHOWABLE_RESULTS, TIMEZONES, TIMEZONE_CHECK_SET, MAX_TIMESTAMP, isOwner

log = logging.getLogger(__name__)

class TzCommands(commands.Cog):
    TIMEZONE_GROUP: ClassVar[app_commands.Group] = app_commands.Group(name="timezone", description="Timezone related stuff")
    UNIX_GROUP: ClassVar[app_commands.Group] = app_commands.Group(name="unix", description="Unix timestamp related stuff")
    DATETIME_STR_FORMAT: ClassVar[str] = "%Y-%m-%d %H:%M:%S"

    def __init__(this, client: TZBot) -> None:
        this.client = client

    async def getTimezones(this, ctx: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        result = []

        cityMatches = cast(list[app_commands.Choice[str]], [app_commands.Choice(name=tz.stringify(), value=tz.stringify()) for tz in TIMEZONES if
                       tz.city.lower().startswith(current.lower())])
        areaMatches = cast(list[app_commands.Choice[str]], [app_commands.Choice(name=tz.stringify(), value=tz.stringify()) for tz in TIMEZONES if
                       tz.area.lower().startswith(current.lower())])

        if len(cityMatches) > MAX_SHOWABLE_RESULTS:
            return cityMatches[:MAX_SHOWABLE_RESULTS]

        result.extend(cityMatches)
        result.extend(areaMatches[:MAX_SHOWABLE_RESULTS - len(cityMatches)])

        return result

    @TIMEZONE_GROUP.command(name="set", description="Sets your timezone to the correct one.")
    @app_commands.describe(timezone="The timezone you are in.")
    @app_commands.autocomplete(timezone=getTimezones)
    async def tzSet(this, ctx: discord.Interaction, timezone: str) -> None:
        if timezone not in TIMEZONE_CHECK_SET:
            log.error(f"{ctx.user.name} tried to set their timezone to {timezone}.")
            embed = await this.client.getFail(description="Invalid timezone. Use [this table](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)

        elif result := await this.client.db.setTimezone(UInt64(ctx.user.id), timezone):
            embed = await this.client.getSuccess(user=ctx.user)
            log.info(f"{ctx.user.name} set their timezone to {timezone}! Result: {result}")
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            log.error(f"Failed to set timezone for user {ctx.user.name} to {timezone}! Result: {result}")
            embed = await this.client.getFail(user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)

    @TIMEZONE_GROUP.command(name="show", description="Shows you timezone you set.")
    async def tzGet(this, ctx: discord.Interaction) -> None:
        if not (res := await this.client.db.getTimezoneFromUserId(UInt64(ctx.user.id))):
            log.error(f"Failed to get timezone for user {ctx.user.name} ({ctx.user.id}).")
            embed = await this.client.getFail(user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.response.send_message(f"Your timezone is {res.replace('_', ' ')}", ephemeral=True)

    @app_commands.command(name="now", description="Shows person's time.")
    @app_commands.describe(person="Whose time to display?")
    async def now(this, ctx: discord.Interaction, person: Optional[discord.Member]) -> None:
        if not isinstance(ctx.user, discord.Member):
            embed = await this.client.getFail(description=f"This command is runnable only inside servers!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        if not person: person = ctx.user
        if not person:
            raise ValueError(f"{person=} is null!")

        if not (zoneName := await this.client.db.getTimezoneFromUserId(UInt64(person.id))):
            embed = await this.client.getFail(description=f"{person.mention} hasn't registered with me yet!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        timezone = pytz.timezone(zoneName)
        theirTime = datetime.datetime.now(timezone)

        utcOffset = theirTime.strftime("%z")
        formattedOffset = f"GMT{utcOffset[:3]}:{utcOffset[3:]}"

        embed = discord.Embed(
            title=f"{person.display_name}'s time ({formattedOffset})",
            color=discord.Color.green(),
            description=theirTime.strftime("\n".join([
                f"%A, %d.%m.%Y %H:%M (🇪🇺)",
                f"%A, %m/%d/%Y %I:%M %p (🇺🇸)",
                "",
                f"Your time: <t:{int(theirTime.timestamp())}:F>"
            ]))
        )

        await ctx.response.send_message(embed=embed)

    @app_commands.command(name="tznow", description="Shows the time in a certain timezone.")
    @app_commands.describe(timezone="Timezone to show the current time for.")
    @app_commands.autocomplete(timezone=getTimezones)
    async def nowTz(this, ctx: discord.Interaction, timezone: str) -> None:
        if timezone not in TIMEZONE_CHECK_SET:
            log.error(f"{ctx.user.name} entered invalid timezone: '{timezone}'.")
            fail = this.client.getFail(description="Invalid timezone. Use [this table](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.", user=ctx.user)
            await ctx.response.send_message(embed=fail, ephemeral=True)
            return

        zone = pytz.timezone(timezone.replace(" ", "_"))

        requestedTime = datetime.datetime.now(zone)
        utcOffset = requestedTime.strftime("%z")
        formattedOffset = f"GMT{utcOffset[:3]}:{utcOffset[3:]}"

        embed = discord.Embed(
            title=f"Time in {timezone.split('/')[1].replace('_', ' ')} ({formattedOffset})",
            color=discord.Color.green(),
            description=requestedTime.strftime("\n".join([
                f"%A, %d.%m.%Y %H:%M (🇪🇺)",
                f"%A, %m/%d/%Y %I:%M %p (🇺🇸)",
                "",
                f"Your time: <t:{int(requestedTime.timestamp())}:F>"
            ]))
        )

        await ctx.response.send_message(embed=embed)
        return

    @UNIX_GROUP.command(name="from", description="Convert a unix timestamp to time at timezone")
    @app_commands.autocomplete(timezone=getTimezones)
    @app_commands.describe(
        timestamp="Timestamp you want to convert.",
        timezone="Timezone you want to show the time at. Defaults to UTC."
    )
    async def unixFrom(this, ctx: discord.Interaction, timestamp: app_commands.Range[int, 0, MAX_TIMESTAMP], timezone: Optional[str] = None) -> None:
        if timezone and timezone not in TIMEZONE_CHECK_SET:
            log.error(f"{ctx.user.name} entered invalid timezone: '{timezone}'.")
            fail = this.client.getFail(
                description="Invalid timezone. Use [this table](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.",
                user=ctx.user)
            await ctx.response.send_message(embed=fail, ephemeral=True)
            return

        tz: datetime.tzinfo = pytz.UTC
        if timezone:
            tz: datetime.tzinfo = pytz.timezone(timezone)

        requestedTime = datetime.datetime.fromtimestamp(float(timestamp), tz)
        utcOffset = requestedTime.strftime("%z")
        formattedOffset = f"GMT{utcOffset[:3]}:{utcOffset[3:]}"

        embed = discord.Embed(
            title=f"Unix Timestamp to date conversion (as {formattedOffset})",
            color=discord.Color.green(),
            description=requestedTime.strftime("\n".join([
                f"%A, %d.%m.%Y %H:%M (🇪🇺)",
                f"%A, %m/%d/%Y %I:%M %p (🇺🇸)",
                "",
                f"Your time: <t:{int(timestamp)}:F>"
            ]))
        )

        await ctx.response.send_message(embed=embed)

    @UNIX_GROUP.command(name="to", description="Convert a time at timezone to a unix timestamp")
    @app_commands.autocomplete(timezone=getTimezones)
    @app_commands.describe(
        year="Year of the date you want to convert. Defaults to the current year.",
        month="Month of the date you want to convert. Defaults to the current month.",
        day="Day of the date you want to convert. Defaults to the current day.",
        hour="Hour of the date you want to convert. Defaults to the current hour.",
        minute="Minute of the date you want to convert. Defaults to the current minute.",
        second="Second of the date you want to convert. Defaults to the current second.",
        timezone="Timezone the date is in. Defaults to the user's timezone if found, otherwise UTC."
    )
    async def unixTo(this, ctx: discord.Interaction,
                     year: app_commands.Range[int, 1970, 9999] = datetime.datetime.now().year,
                     month: app_commands.Range[int, 1, 12] = datetime.datetime.now().month,
                     day: app_commands.Range[int, 1, 31] = datetime.datetime.now().day,
                     hour: app_commands.Range[int, 0, 23] = datetime.datetime.now().hour,
                     minute: app_commands.Range[int, 0, 59] = datetime.datetime.now().minute,
                     second: app_commands.Range[int, 0, 59] = datetime.datetime.now().second,
                     timezone: Optional[str] = None) -> None:

        if timezone and timezone not in TIMEZONE_CHECK_SET:
            log.error(f"{ctx.user.name} entered invalid timezone: '{timezone}'.")
            fail = this.client.getFail(
                description="Invalid timezone. Use [this table](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.",
                user=ctx.user)
            await ctx.response.send_message(embed=fail, ephemeral=True)
            return

        timeStr = f"{year}-{month}-{day} {hour}:{minute}:{second}"
        requestedTime = datetime.datetime.strptime(timeStr, this.DATETIME_STR_FORMAT)
        tz: datetime.tzinfo = pytz.UTC
        if timezone:
            tz = pytz.timezone(timezone)
        else:
            if zoneStr := await this.client.db.getTimezoneFromUserId(UInt64(ctx.user.id)):
                tz = pytz.timezone(zoneStr)

        requestedTime = tz.localize(requestedTime, False)
        utcOffset = requestedTime.strftime("%z")
        formattedOffset = f"GMT{utcOffset[:3]}:{utcOffset[3:]}"
        embed = discord.Embed(
            title=f"Date to Unix Timestamp conversion (as {formattedOffset})",
            color=discord.Color.green(),
            description=requestedTime.strftime("\n".join([
                f"Inputted date: <t:{int(requestedTime.finalTimestamp())}:F>",
                f"Result: `{int(requestedTime.finalTimestamp())}`"
            ]))
        )

        await ctx.response.send_message(embed=embed)
        return

    @TIMEZONE_GROUP.command(name="admin-add", description="Admin command to add a person to the database.")
    @app_commands.autocomplete(timezone=getTimezones)
    @app_commands.describe(
        user="User to add to the database.",
        timezone="Timezone to set for the user."
    )
    @app_commands.check(isOwner)
    async def adminAdd(this, ctx: discord.Interaction, user: discord.Member, timezone: str) -> None:
        if timezone not in TIMEZONE_CHECK_SET:
            log.error(f"{ctx.user.name} entered invalid timezone: '{timezone}'.")
            fail = this.client.getFail(description="Invalid timezone. Use [this table](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.", user=ctx.user)
            await ctx.response.send_message(embed=fail, ephemeral=True)
            return

        if await this.client.db.setTimezone(UInt64(user.id), timezone):
            embed = await this.client.getSuccess(user=ctx.user)
            log.info(f"{ctx.user.name} set {user.name}'s timezone to {timezone}!")
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            log.error(f"Failed to set timezone for user {user.name} to {timezone}!")
            embed = await this.client.getFail(user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)


async def setup(client: TZBot) -> None:
    await client.add_cog(TzCommands(client))
