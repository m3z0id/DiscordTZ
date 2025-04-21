import discord
from discord import app_commands
from discord.ext import commands
import datetime
import mariadb
import json
import os

config: dict[str] = json.loads(open("config.json", "r").read())
client: commands.Bot = commands.Bot("tz!", help_command=None, intents=discord.Intents.all())

db: dict = config.get("mariadbDetails")

conn: mariadb.Connection = mariadb.connect(
    database=db.get("database"),
    user=db.get("user"),
    password=db.get("password"),
    host=db.get("host"),
    port=int(db.get("port")),
    autocommit=bool(db.get("autocommit"))
)

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
        print(f"Synced {len(synced)} commands!")
    except Exception as e:
        print(f"Exception occured: {e}")
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
    nowtime: str = datetime.datetime.now().strftime("%d.%m.%y %H:%M:%S")
    if(timezone not in checkList):
        print(f"[{nowtime}] ERROR: {ctx.user} tried to set their timezone to {timezone}.")
        failCpy = fail
        failCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        failCpy.timestamp = datetime.datetime.now()

        await ctx.response.send_message(embed=failCpy, ephemeral=True)
        return

    cursor: mariadb.Cursor = conn.cursor(prepared=True)
    query: str = f"INSERT into {db.get("tableName")} (user, timezone) VALUES (%s, %s) ON DUPLICATE KEY UPDATE timezone = %s"

    data: tuple[int, str, str] = (ctx.user.id, timezone.replace(" ", "_"), timezone.replace(" ", "_"))

    try:
        cursor.execute(query, data)
        conn.commit()
        print(f"[{nowtime}] SUCCESS: {ctx.user} set their timezone to {timezone}!")
        successCpy = success
        successCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        successCpy.timestamp = datetime.datetime.now()

        await ctx.response.send_message(embed=successCpy, ephemeral=True)
        return

    except mariadb.Error as e: 
        print(f"[{nowtime}] ERROR: {e}")
        failCpy = fail
        failCpy.set_footer(text=ctx.user.name, icon_url=ctx.user.avatar.url)
        failCpy.timestamp = datetime.datetime.now()

        await ctx.response.send_message(embed=failCpy, ephemeral=True)
        return
    
@mytimezone.command(name="get", description="Shows you timezone you set.")
async def get(ctx: discord.Interaction) -> None:
    nowtime: str = datetime.datetime.now().strftime("%d.%m.%y %H:%M:%S")

    cursor: mariadb.Cursor = conn.cursor(prepared=True)
    query: str = f"SELECT timezone from {db.get("tableName")} WHERE user = %s"
    data: list[int] = [ctx.user.id]

    try:
        cursor.execute(query, data)
        conn.commit()

        result = cursor.fetchone()

        if(result):
            tz: str = str(result[0])
        else:
            temp: list[str] = os.readlink("/etc/localtime").split("/")
            tz: str = f"{temp[-2]}/{temp[-1]}"

        await ctx.response.send_message(f"Your timezone is {tz.replace("_", " ")}", ephemeral=True)

    except mariadb.Error as e:
        print(f"[{nowtime}] ERROR: {e}")


client.run(config["token"])