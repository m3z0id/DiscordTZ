import asyncio
import copy
import json
import logging
from json import JSONDecodeError
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from dtypes import Profile, PresenceType, ActivityType
from modules import TZBot
from shared import PROFILE_FILE, ACTIVITY_TYPES, PRESENCE_TYPES, isOwner


log = logging.getLogger(__name__)

class BotProfile(commands.GroupCog, group_name="profile", description="[Bot Owner] Bot's profile related stuff"):
    currentProfile: Profile
    permanentProfile: Profile

    def __init__(this, client: TZBot) -> None:
        if not PROFILE_FILE.exists():
            log.warning(f"{PROFILE_FILE.name} doesn't exist! Falling back to defaults...")

            this.currentProfile = Profile()
            asyncio.create_task(this.saveStatus())
        else:
            with PROFILE_FILE.open("r") as f:
                try:
                    this.currentProfile = Profile.schema().loads(f.read())
                except JSONDecodeError as e:
                    log.warning(f"Failed to decode {PROFILE_FILE.name}: {e!s}")
                    log.warning("Falling back to defaults...")
                    this.currentProfile = Profile()

        this.permanentProfile = copy.deepcopy(this.currentProfile)
        this.client = client

    async def asyncInit(this) -> None:
        await this.reloadPresence()

    async def saveStatus(this) -> None:
        log.info("Saving permanent status...")
        with PROFILE_FILE.open("w") as f:
            f.write(json.dumps(this.permanentProfile.__dict__))

    async def reloadPresence(this) -> None:
        await this.client.change_presence(status=discord.Status(this.currentProfile.presence), activity=discord.Activity(type=discord.ActivityType(this.currentProfile.activityType), name=this.currentProfile.activityName))

    @app_commands.command(name="presence", description="[Bot Owner] Change the bot's presence!")
    @app_commands.choices(presence=[app_commands.Choice(name=choice, value=choice) for choice in PRESENCE_TYPES])
    @app_commands.describe(
        presence="Presence to set for the bot",
        persistent="If the status stays after restart/cog reload"
    )
    @app_commands.check(isOwner)
    async def changePresence(this, ctx: discord.Interaction, presence: PresenceType, persistent: bool = False) -> None:
        if persistent:
            this.permanentProfile.presence = presence

        this.currentProfile.presence = presence
        await this.saveStatus()

        await this.reloadPresence()
        await ctx.response.send_message(f"Presence set to {presence}!", ephemeral=True)
        return

    @app_commands.command(name="activity", description="[Bot Owner] Change the bot's activity!")
    @app_commands.choices(activitytype=[app_commands.Choice(name=choice, value=choice) for choice in ACTIVITY_TYPES])
    @app_commands.describe(
        activitytype="Activity type for the bot",
        title="The activity body",
        persistent="If the status stays after restart/cog reload"
    )
    @app_commands.check(isOwner)
    async def changeActivity(this, ctx: discord.Interaction, activitytype: Optional[ActivityType], title: Optional[str], persistent: bool = False) -> None:
        if not (activitytype or title):
            await ctx.response.send_message("Either the activity type or the activity title has to be set!")
            return

        if activitytype:
            if persistent:
                this.permanentProfile.activityType = ACTIVITY_TYPES.index(activitytype) - 1
            this.currentProfile.activityType = ACTIVITY_TYPES.index(activitytype) - 1

        if title:
            if persistent:
                this.permanentProfile.activityName = title
            this.currentProfile.activityName = title

        await this.saveStatus()
        await this.reloadPresence()
        await ctx.response.send_message(f"Activity set!", ephemeral=True)

async def setup(bot: TZBot) -> None:
    c = BotProfile(bot)
    await c.asyncInit()
    await c.saveStatus()
    await bot.add_cog(c)