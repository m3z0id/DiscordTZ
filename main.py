import discord
from database import Database
from discord import app_commands
from discord.ext import commands
from logger import Logger
from server import Server
import datetime
import asyncio
import json
import os

config: dict[str] = json.loads(open("config.json", "r").read())
client: commands.Bot = commands.Bot("tz!", help_command=None, intents=discord.Intents.all())

db: dict = config.get("mariadbDetails")
database: Database = Database(db)

success: discord.Embed = discord.Embed(
    title="**Success!**",
    description="The operation was successful!",
    color=discord.Color.green()
)

fail: discord.Embed = discord.Embed(
    title="**Something went wrong.**",
    description="There was an error in the operation.",
    color=discord.Color.red()
)

def fetchTimezones() -> list[dict[str: str]]:
    parentDir: str = "/usr/share/zoneinfo/"
    files: list[dict[str: str]] = []
    for root, dirs, filenames in os.walk(parentDir):
        if("posix" in root or "right" in root):
            continue
        for filename in filenames:
            relativePath = os.path.relpath(os.path.join(root, filename), parentDir)
            if("/" in relativePath):
                files.append({"area": relativePath.split("/")[0], "city": relativePath.split("/")[-1].replace("_", " ")})
    return files

timezones: list[dict[str: str]] = fetchTimezones()
checkList: list[str] = [tz['area'] + "/" + tz["city"] for tz in timezones]
mytimezone = app_commands.Group(name="mytimezone", description="Timezone related stuff")

@client.event
async def on_ready() -> None:
    try:
        client.tree.add_command(mytimezone)
        synced = await client.tree.sync()
        Logger.success(f"Synced {len(synced)} commands!")
    except Exception as e:
        Logger.error(e)
        os._exit(1)

async def getTimezones(ctx: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    result: list[app_commands.Choice[str]] = []

    cityMatches = [
        app_commands.Choice(name=f"{tz['area']}/{tz['city']}", value=f"{tz['area']}/{tz['city']}")
        for tz in timezones
        if str(tz.get("city", "")).lower().startswith(current.lower())
    ]

    areaMatches = [
        app_commands.Choice(name=f"{tz['area']}/{tz['city']}", value=f"{tz['area']}/{tz['city']}")
        for tz in timezones
        if str(tz.get("area", "")).lower().startswith(current.lower())
    ]

    for choice in cityMatches[:25]:
        result.append(choice)

    if len(result) < 25:
        for choice in areaMatches:
            if len(result) == 25:
                break
            result.append(choice)

    return result

@mytimezone.command(name="set", description="Sets your timezone to the correct one.")
@app_commands.describe(timezone="The timezone you are in.")
@app_commands.autocomplete(timezone=getTimezones)
async def set(ctx: discord.Interaction, timezone: str) -> None:

    if(timezone not in checkList):
        Logger.error(f"{ctx.user} tried to set their timezone to {timezone}.")
        failCpy = fail
        failCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        failCpy.timestamp = datetime.datetime.now()

        await ctx.response.send_message(embed=failCpy, ephemeral=True)
        return

    if(database.set(ctx.user.id, timezone)):
        successCpy = success
        successCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        successCpy.timestamp = datetime.datetime.now()
        Logger.success(f"{ctx.user} set their timezone to {timezone}!")
        await ctx.response.send_message(embed=successCpy, ephemeral=True)
    else:
        failCpy = fail
        failCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        failCpy.timestamp = datetime.datetime.now()

        await ctx.response.send_message(embed=failCpy, ephemeral=True)
    
@mytimezone.command(name="get", description="Shows you timezone you set.")
async def get(ctx: discord.Interaction) -> None:
    res: str | bool = database.get(ctx.user.id)

    if(isinstance(res, bool)):
        failCpy = fail
        failCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        failCpy.timestamp = datetime.datetime.now()

        await ctx.response.send_message(embed=failCpy, ephemeral=True)

    else:
        await ctx.response.send_message(f"Your timezone is {res.replace("_", " ")}", ephemeral=True) 


async def main():
    serverStarter = asyncio.create_task(Server(database).start())
    async with client:
        await client.start(config["token"])

    await serverStarter

asyncio.run(main())