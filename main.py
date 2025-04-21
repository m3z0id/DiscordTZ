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
    color=discord.Color.green()
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

async def getTimezones(ctx: discord.Interaction, current: str):
    result: list[app_commands.Choice] = []
    timezonesCopy = timezones
    for timezone in timezones:
        if(len(result) == 25): break
        if(str(timezone.get("city")).startswith(current)): 
            timezonesCopy.remove(timezone)
            result.append(app_commands.Choice(name=f"{timezone.get("area")}/{timezone.get("city")}", value=f"{timezone.get("area")}/{timezone.get("city")}"))
    else:
        for timezone in timezonesCopy:
            if(len(result) == 25): break
            if(str(timezone.get("area")).startswith(current)): result.append(app_commands.Choice(name=f"{timezone.get("area")}/{timezone.get("city")}", value=f"{timezone.get("area")}/{timezone.get("city")}"))

    return result

@mytimezone.command(name="set", description="Sets your timezone to the correct one.")
@mytimezone.describe(timezone="The timezone you are in.")
@mytimezone.choices(timezone=getTimezones)
async def set(ctx: discord.Interaction, timezone: app_commands.Choice[str]) -> None:
    cursor: mariadb.Cursor = conn.cursor(prepared=True)
    query: str = f"INSERT into {db.get("tableName")} (user, timezone) VALUES (%s, %s)"

    data: tuple[int, str] = (ctx.user.id, timezone.value)

    try:
        cursor.execute(query, data)
        conn.commit()
        print(f"Inserted {data} successfully!")
        successCpy = success
        successCpy.set_footer(ctx.user.name, ctx.user.avatar.url)
        successCpy.timestamp = datetime.datetime.now()

        ctx.response.send_message(embed=successCpy, ephemeral=True)

    except mariadb.Error as err: 
        print(f"Error: {err}")
        print(f"Data: {data}")
        failCpy = fail
        failCpy.set_footer(ctx.user.name, ctx.user.avatar.url)
        failCpy.timestamp = datetime.datetime.now()

        ctx.response.send_message(embed=failCpy, ephemeral=True)


client.run(config["token"])