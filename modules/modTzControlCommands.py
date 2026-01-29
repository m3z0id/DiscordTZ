import datetime

import discord
import pytz
from discord.ext import commands

from database.stats.StatsDatabase import collectCommandStats
from modules.TZBot import TZBot
from shared.Constants import MAX_SHOWABLE_RESULTS, TIMEZONES, TIMEZONE_CHECK_LIST
from shell.Logger import Logger


class TzCommands(commands.Cog):
    timezoneGroup = discord.SlashCommandGroup(name="timezone", description="Timezone related stuff")

    def __init__(this, client: TZBot) -> None:
        this.client = client

    async def getTimezones(this, ctx: discord.AutocompleteContext) -> list[str]:
        result: list[str] = []

        cityMatches = [f"{tz['area']}/{tz['city']}" for tz in TIMEZONES if
                       str(tz.get("city", "")).lower().startswith(ctx.value.lower())]
        areaMatches = [f"{tz['area']}/{tz['city']}" for tz in TIMEZONES if
                       str(tz.get("area", "")).lower().startswith(ctx.value.lower())]

        if len(cityMatches) > MAX_SHOWABLE_RESULTS:
            return cityMatches[:MAX_SHOWABLE_RESULTS]

        result.extend(cityMatches)
        result.extend(areaMatches[:MAX_SHOWABLE_RESULTS - len(cityMatches)])

        return result

    @timezoneGroup.command(name="set", description="Sets your timezone to the correct one.")
    @collectCommandStats
    async def tzSet(
        this,
        ctx: discord.ApplicationContext,
        timezone: discord.Option(str, "The timezone you are in.", autocomplete=getTimezones),
        tzalias: discord.Option(str, "Alias with which other people will get your time.", required=False, default=None),
    ) -> bool:
        if tzalias is None:
            tzalias = ctx.user.name

        if timezone not in TIMEZONE_CHECK_LIST:
            Logger.error(f"{ctx.user} tried to set their timezone to {timezone}.")
            await ctx.response.send_message("Invalid timezone. Use [this table](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.", ephemeral=True)
            return False

        if await this.client.db.setTimezone(ctx.user.id, timezone, tzalias):
            embed = await this.client.getSuccess(user=ctx.user)
            Logger.success(f"{ctx.user} set their timezone to {timezone}!")
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return True
        else:
            embed = await this.client.getFail(user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False

    @timezoneGroup.command(name="show", description="Shows you timezone you set.")
    @collectCommandStats
    async def tzGet(this, ctx: discord.ApplicationContext) -> bool:
        res: str | None = await this.client.db.getTimeZone(ctx.user.id)

        if not res:
            embed = await this.client.getFail(user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False
        else:
            await ctx.response.send_message(f"Your timezone is {res.replace('_', ' ')}", ephemeral=True)
            return True

    @discord.slash_command(name="now", description="Shows person's time.")
    @collectCommandStats
    async def now(this, ctx: discord.ApplicationContext, person: discord.Option(discord.Member, "Who's time to display?")) -> bool:
        person: discord.Member
        try:
            zoneName = await this.client.db.getTimeZone(person.id)
            timezone = pytz.timezone(zoneName)
        except pytz.exceptions.UnknownTimeZoneError:
            embed = await this.client.getFail(description=f"{person.mention} hasn't registered with Timezone Bot yet.", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False

        theirTime = datetime.datetime.now(timezone)

        utcOffset = theirTime.strftime("%z")
        formattedOffset = f"GMT{utcOffset[:3]}:{utcOffset[3:]}"
        timeFormatted = theirTime.strftime(" ".join([
                    f"{person.display_name}'s time: %A, %d.%m.%Y %H:%M | %m/%d/%Y %I:%M %p",
                    f"({formattedOffset} | {zoneName.replace('_', ' ')})",
                    f"\nYour time: <t:{int(theirTime.timestamp())}:F>",
                ]))

        await ctx.response.send_message(timeFormatted)
        return True

    @discord.slash_command(name="tznow", description="Shows the time in a certain timezone.")
    @collectCommandStats
    async def nowTz(this, ctx: discord.ApplicationContext, timezone: discord.Option(str, "Timezone to show", autocomplete=getTimezones)) -> bool:
        if timezone not in TIMEZONE_CHECK_LIST:
            await ctx.response.send_message("Invalid timezone. Use [this table] (https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for reference.", ephemeral=True)
            return False

        try:
            zone = pytz.timezone(timezone.replace(" ", "_"))
        except pytz.exceptions.UnknownTimeZoneError:
            embed = await this.client.getFail(description="Timezone not found. Contact <@769924149648424990> for help.", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False

        requestedTime = datetime.datetime.now(zone)
        utcOffset = requestedTime.strftime("%z")
        formattedOffset = f"GMT{utcOffset[:3]}:{utcOffset[3:]}"
        timeFormatted = requestedTime.strftime(" ".join([
                    f"Time in {timezone.split('/')[1].replace('_', ' ')}:",
                    f"%A, %d.%m.%Y %H:%M | %m/%d/%Y %I:%M %p ({formattedOffset})",
                    f"\nYour time: <t:{int(requestedTime.timestamp())}:F>",
                ]))

        await ctx.response.send_message(timeFormatted)
        return True


def setup(client: TZBot) -> None:
    client.add_cog(TzCommands(client))
