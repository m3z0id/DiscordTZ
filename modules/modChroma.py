import asyncio
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Final, Coroutine, Any, Union, cast

import discord
from PIL import Image
from discord import app_commands
from discord.ext import commands

from dtypes import ColorSpace, TypedBytesIO
from modules import TZBot
from shared import IMAGE_CONTENT_TYPES, VALID_COLOR_SPACES, TEMP_IMAGES_DIR, URL_PATTERN, \
    EMOJI_PATTERN, CHROMA_EXEC_FILE

log = logging.getLogger(__name__)

class Chroma(commands.Cog):
    COMMAND_LOCK: Final[asyncio.Semaphore] = asyncio.Semaphore(3)
    outputtedImages: set[Path] = set()

    def __init__(this, client: TZBot) -> None:
        this.client = client

        if not CHROMA_EXEC_FILE:
            log.warning(f"Chroma executable not found in PATH!")

    async def cleanup(this) -> None:
        for _ in this.outputtedImages:
            _.unlink()

        this.outputtedImages.clear()
        this.COMMAND_LOCK.release()

    async def runChroma(this, imgPath: Path, colorspace: ColorSpace, modifications: str) -> BytesIO:
        outputted = Path(TEMP_IMAGES_DIR / f"{imgPath.stem}MODIFIED.bmp")
        process = await asyncio.create_subprocess_exec(
            cast(Path, CHROMA_EXEC_FILE), "-f", f"{imgPath.parent}/{imgPath.name}", "-o", f"{outputted.parent}/{outputted.name}",  # CHROMA_EXEC_FILE can't be null here
            f"--{colorspace}", modifications,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            log.error(f"{imgPath.name} failed with return code {process.returncode}")
            raise RuntimeError("Bad modifier arguments.")

        this.outputtedImages.add(outputted)

        file = BytesIO()
        img = Image.open(outputted)
        img.convert("RGBA").save(file, format="PNG")
        file.seek(0)

        return file

    async def getImageAttachmentsFromMessage(this, msg: discord.Message) -> set[TypedBytesIO]:
        images: set[TypedBytesIO] = set()
        for attachment in msg.attachments:
            if not attachment.content_type or attachment.content_type not in IMAGE_CONTENT_TYPES: continue
            images.add(TypedBytesIO(attachment.content_type, BytesIO(await attachment.read())))

        return images

    async def getImagesFromLinks(this, msg: discord.Message) -> set[TypedBytesIO]:
        images: set[TypedBytesIO] = set()
        for match in re.finditer(URL_PATTERN, msg.content):
            url = match.group(0)
            response = await this.client.netClient.downloadFile(url, mimeTypes=IMAGE_CONTENT_TYPES)
            if response: images.add(response)

        return images

    async def getImagesFromEmbeds(this, msg: discord.Message) -> set[TypedBytesIO]:
        images: set[TypedBytesIO] = set()
        if len(msg.embeds) > 0:
            for embed in msg.embeds:
                if embed.image:
                    response = await this.client.netClient.downloadFile(embed.image.url, mimeTypes=IMAGE_CONTENT_TYPES)
                    if response: images.add(response)
                    else: log.error("No response for embed image!")

                if embed.thumbnail:
                    response = await this.client.netClient.downloadFile(embed.thumbnail.url, mimeTypes=IMAGE_CONTENT_TYPES)
                    if response: images.add(response)
                    else: log.error("No response for embed image!")

        return images

    async def getCustomEmojisFromMessage(this, msg: discord.Message) -> set[TypedBytesIO]:
        images: set[TypedBytesIO] = set()

        for match in re.finditer(EMOJI_PATTERN, msg.content):
            emojiId = match.group(1)
            emojiUrl = f"https://cdn.discordapp.com/emojis/{emojiId}"
            response = await this.client.netClient.downloadFile(emojiUrl, mimeTypes=IMAGE_CONTENT_TYPES)
            if response: images.add(response)
            else: log.error("No response for custom emoji!")

        return images

    @commands.hybrid_command(name="chroma", description="Modify image using \"filters\"!")
    @app_commands.choices(colorspace=[app_commands.Choice(name=choice, value=choice) for choice in VALID_COLOR_SPACES])
    @app_commands.describe(
        colorspace=f"Filter's colorspace ({", ".join(VALID_COLOR_SPACES)})",
        modifications=f"The filter itself (format: <channel>:(modifier)<value|channel>))"
    )
    async def chroma(this, ctx: commands.Context, colorspace: ColorSpace, modifications: str) -> None:
        if ctx.interaction:
            await ctx.interaction.response.send_message("Slash version isn't implemented yet. Please, use the prefixed version instead.", ephemeral=True)

        if not CHROMA_EXEC_FILE:
            await ctx.reply("This feature is disabled.")
            return

        await ctx.defer()
        if this.COMMAND_LOCK.locked():
            await ctx.reply("Please wait before other command finishes!")
            return

        if colorspace.lower() not in VALID_COLOR_SPACES:
            await ctx.reply(f"Please enter valid color space! [{"|".join(VALID_COLOR_SPACES)}]")
            return

        if not modifications:
            await ctx.reply("Please specify modifications!")
            return

        await this.COMMAND_LOCK.acquire()
        imagesToProcess: set[TypedBytesIO] = set()

        if ctx.message.attachments:
            imagesToProcess.update(await this.getImageAttachmentsFromMessage(ctx.message))
            imagesToProcess.update(await this.getCustomEmojisFromMessage(ctx.message))
            imagesToProcess.update(await this.getImagesFromLinks(ctx.message))
        if ctx.message.reference and ctx.message.reference.message_id:
            orig = await ctx.message.channel.fetch_message(ctx.message.reference.message_id)
            imagesToProcess.update(await this.getImageAttachmentsFromMessage(orig))
            imagesToProcess.update(await this.getImagesFromEmbeds(orig))
            imagesToProcess.update(await this.getCustomEmojisFromMessage(orig))
            imagesToProcess.update(await this.getImagesFromLinks(orig))

        if not imagesToProcess:
            this.COMMAND_LOCK.release()
            return

        tasks: set[Coroutine[Any, Any, BytesIO]] = set()
        TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        for i, image in enumerate(imagesToProcess):
            currentImgPath: Path = TEMP_IMAGES_DIR / f"{i}.bmp"
            pic = Image.open(image.content)
            pic.convert("RGBA").save(currentImgPath)
            tasks.add(this.runChroma(currentImgPath, colorspace, modifications))

        results: list[Union[BaseException, BytesIO]] = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, BaseException):
                log.error(res.args)
                results.remove(res)
                await ctx.reply("There's an error.")
                await this.cleanup()
                return

        results: list[BytesIO]

        await ctx.reply(f"**[i]** Images converted!", files=[discord.File(file, filename=f"{idx}.png") for idx, file in enumerate(results)])
        await this.cleanup()
        return

async def setup(client: TZBot):
    await client.add_cog(Chroma(client))