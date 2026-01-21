import asyncio
import io
import re
from io import BytesIO
from pathlib import Path
from typing import Final

import discord
from PIL import Image
from discord.ext import commands, bridge

from database.stats.StatsDatabase import collectCommandStats
from modules.TZBot import TZBot
from shell.Logger import Logger


class Chroma(commands.Cog):
    client: TZBot

    CHROMA_EXEC: Final[Path] = Path("./execs/chroma")
    VALID_COLOR_SPACES: Final[set[str]] = {"rgb", "hsl", "oklab", "oklch", "okhsl"}

    EMOJI_PATTERN: Final[re.Pattern[str]] = re.compile("<:[a-zA-Z0-9_-]{2,32}:(\\d{18,20})>")
    URL_REGEX: Final[re.Pattern[str]] = re.compile(
        r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)")

    TEMP_IMAGES_PATH: Final[Path] = Path("temp/")

    COMMAND_LOCK: Final[asyncio.Semaphore] = asyncio.Semaphore(3)

    outputtedImages: set[Path] = set()

    def __init__(this, client: TZBot):
        this.client = client

        if not Chroma.CHROMA_EXEC.is_file():
            Logger.warning(f"Chroma executable not found at {Chroma.CHROMA_EXEC}")

    async def cleanup(this):
        for _ in this.outputtedImages:
            _.unlink()

        this.outputtedImages.clear()
        this.COMMAND_LOCK.release()

    async def runChroma(this, imgPath: Path, colorspace: str, modifications: str) -> BytesIO:
        outputted = Path(this.TEMP_IMAGES_PATH / f"{imgPath.stem}MODIFIED.bmp")
        process = await asyncio.create_subprocess_exec(
            this.CHROMA_EXEC.absolute(), "-f", f"{imgPath.parent}/{imgPath.name}", "-o", f"{outputted.parent}/{outputted.name}",
            f"--{colorspace}", modifications,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            Logger.error(f"{imgPath.name} failed with return code {process.returncode}")
            raise RuntimeError("Bad modifier arguments.")

        this.outputtedImages.add(outputted)

        file = BytesIO()
        img = Image.open(outputted)
        img.convert("RGBA").save(file, format="PNG")
        file.seek(0)

        return file

    async def getImageAttachmentsFromMessage(this, msg: discord.Message) -> set[tuple[str, bytes]]:
        images: set[tuple[str, bytes]] = {(attachment.content_type, await attachment.read()) for attachment in
                                               msg.attachments if attachment.content_type in this.client.IMAGE_CONTENT_TYPES}
        return images

    async def getImagesFromLinks(this, msg: discord.Message) -> set[tuple[str, bytes]]:
        images: set[tuple[str, bytes]] = set()
        for match in re.finditer(this.URL_REGEX, msg.content):
            url = match.group(0)
            response = await this.client.downloadFile(url, this.client.IMAGE_CONTENT_TYPES)
            if response: images.add(response)

        return images

    async def getImagesFromEmbeds(this, msg: discord.Message) -> set[tuple[str, bytes]]:
        images: set[tuple[str, bytes]] = set()
        if len(msg.embeds) > 0:
            for embed in msg.embeds:
                if embed.image:
                    response = await this.client.downloadFile(embed.image.url, this.client.IMAGE_CONTENT_TYPES)
                    if response: images.add(response)

                if embed.thumbnail:
                    response = await this.client.downloadFile(embed.thumbnail.url, this.client.IMAGE_CONTENT_TYPES)
                    if response: images.add(response)

        return images

    async def getCustomEmojisFromMessage(this, msg: discord.Message) -> set[tuple[str, bytes]]:
        images: set[tuple[str, bytes]] = set()

        for match in re.finditer(this.EMOJI_PATTERN, msg.content):
            emojiId = match.group(1)
            emojiUrl = f"https://cdn.discordapp.com/emojis/{emojiId}"
            response = await this.client.downloadFile(emojiUrl, this.client.IMAGE_CONTENT_TYPES)
            if response: images.add(response)

        return images

    @bridge.bridge_command(name="chroma", description="Modify image using \"filters\"!")
    @collectCommandStats
    async def chroma(this, ctx: bridge.BridgeContext, colorspace: bridge.BridgeOption(str, f"Filter's colorspace ({", ".join(VALID_COLOR_SPACES)})", choices=VALID_COLOR_SPACES), modifications: bridge.BridgeOption(str, f"The filter itself (format: <channel>:(modifier)<value|channel>))")) -> bool:
        if not isinstance(ctx, bridge.BridgeExtContext):
            await ctx.respond("Slash version isn't implemented yet. Please, use the prefixed version instead.", ephemeral=True)

        if not Chroma.CHROMA_EXEC.is_file():
            await ctx.respond("This feature is disabled.")

        await ctx.defer()
        if this.COMMAND_LOCK.locked():
            await ctx.respond("Please wait before other command finishes!")
            return False

        if colorspace.lower() not in this.VALID_COLOR_SPACES:
            await ctx.respond(f"Please enter valid color space! [{"|".join(this.VALID_COLOR_SPACES)}]")
            return False

        if not modifications:
            await ctx.respond("Please specify modifications!")
            return False

        await this.COMMAND_LOCK.acquire()
        imagesToProcess: set[tuple[str, bytes]] = set()

        if ctx.message.attachments:
            imagesToProcess.update(await this.getImageAttachmentsFromMessage(ctx.message))
            imagesToProcess.update(await this.getCustomEmojisFromMessage(ctx.message))
            imagesToProcess.update(await this.getImagesFromLinks(ctx.message))
        if ctx.message.reference:
            orig = await ctx.message.channel.fetch_message(ctx.message.reference.message_id)
            imagesToProcess.update(await this.getImageAttachmentsFromMessage(orig))
            imagesToProcess.update(await this.getImagesFromEmbeds(orig))
            imagesToProcess.update(await this.getCustomEmojisFromMessage(orig))
            imagesToProcess.update(await this.getImagesFromLinks(orig))

        if not imagesToProcess:
            this.COMMAND_LOCK.release()
            return False

        # Ran as slash command
        elif isinstance(ctx, bridge.BridgeApplicationContext):
            embed = await this.client.getFail(description="Command is unsupported as slash command. Please use the legacy version.", user=ctx.user)
            await ctx.respond(embed=embed, ephemeral=True)
            this.COMMAND_LOCK.release()
            return False

        tasks = set()
        this.TEMP_IMAGES_PATH.mkdir(parents=True, exist_ok=True)
        for i, image in enumerate(imagesToProcess):
            currentImgPath: Path = this.TEMP_IMAGES_PATH / f"{i}.bmp"
            pic = Image.open(io.BytesIO(image[1]))
            pic.convert("RGBA").save(currentImgPath)
            tasks.add(this.runChroma(currentImgPath, colorspace, modifications))

        results: list[BaseException | BytesIO] = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, BaseException):
                Logger.error(res.args)
                results.remove(res)
                await ctx.respond("There's an error in your modifier filter.")
                await this.cleanup()
                return False

        results: list[BytesIO]

        await ctx.respond(f"**[i]** Images converted!", files=[discord.File(file, filename=f"{idx}.png") for idx, file in enumerate(results)])
        await this.cleanup()
        return True

def setup(client: TZBot):
    client.add_cog(Chroma(client))