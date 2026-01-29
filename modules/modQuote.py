from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands

from database.stats.StatsDatabase import collectCommandStats
from modules.TZBot import TZBot
from shared.Constants import IMAGE_CONTENT_TYPES, QUOTE_DEFAULT_FONT_SIZE, QUOTE_SMALLEST_FONT_SIZE, FONT_FILE, \
    QUOTE_BOUNDING_BOX


class Quote(commands.Cog):
    def __init__(this, client: TZBot):
        this.client = client

    async def generateLinearGradient(this, width: int, height: int, startColor: tuple[int, int, int, int], endColor: tuple[int, int, int, int]) -> Image.Image:
        r1, g1, b1, a1 = startColor
        r2, g2, b2, a2 = endColor
        gradient = Image.new("RGBA", (width, height))

        data = []
        for y in range(height):
            row = []
            for x in range(width):
                alpha = x / (width - 1)
                r = round(r1 * (1 - alpha) + r2 * alpha)
                g = round(g1 * (1 - alpha) + g2 * alpha)
                b = round(b1 * (1 - alpha) + b2 * alpha)
                a = round(a1 * (1 - alpha) + a2 * alpha)
                row.append((r, g, b, a))
            data.extend(row)

        gradient.putdata(data)
        return gradient

    async def renderQuote(this, text: str) -> Image.Image:
        maxWidth, maxHeight = this.QUOTE_BOUNDING_BOX
        fontSize = this.QUOTE_DEFAULT_FONT_SIZE

        while fontSize > this.QUOTE_SMALLEST_FONT_SIZE:
            font = ImageFont.truetype(this.FONT_PATH, fontSize)

            wrappedLines = []
            for paragraph in text.split('\n'):
                words = paragraph.split(' ')
                currentLine = ""
                for word in words:
                    testLine = f"{currentLine} {word}".strip()
                    bboxLine = font.getbbox(testLine)
                    lineWidth = bboxLine[2] - bboxLine[0]
                    if lineWidth <= maxWidth:
                        currentLine = testLine
                    else:
                        if currentLine:
                            wrappedLines.append(currentLine)
                        currentLine = word
                wrappedLines.append(currentLine)

            lineHeight = (font.getbbox("Ay")[3] - font.getbbox("Ay")[1]) + 15
            totalHeight = lineHeight * len(wrappedLines)

            widestLine = max(font.getbbox(line)[2] - font.getbbox(line)[0] for line in wrappedLines)

            if totalHeight <= maxHeight and widestLine <= maxWidth:
                image = Image.new("RGBA", this.QUOTE_BOUNDING_BOX, (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                y = 0
                for line in wrappedLines:
                    draw.text((0, y), line, font=font, fill=(255, 255, 255, 255))
                    y += lineHeight
                return image

            fontSize -= 1

        return Image.new("RGBA", this.QUOTE_BOUNDING_BOX, (0, 0, 0, 0))

    async def renderAuthor(this, text: str) -> Image.Image:
        fontSize = QUOTE_DEFAULT_FONT_SIZE

        while fontSize > QUOTE_SMALLEST_FONT_SIZE:
            font = ImageFont.truetype(FONT_FILE, fontSize)
            bbox = font.getbbox(text)
            textWidth = int(bbox[2] - bbox[0])
            textHeight = int(bbox[3] - bbox[1])

            if textWidth <= QUOTE_BOUNDING_BOX[0]:
                image = Image.new("RGBA", (QUOTE_BOUNDING_BOX[0], textHeight), (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                draw.text((-bbox[0], -bbox[1]), text, font=font, fill=(255, 255, 255, 255))
                return image

            fontSize -= 1

        return Image.new("RGBA", (QUOTE_BOUNDING_BOX[0], QUOTE_DEFAULT_FONT_SIZE), (0, 0, 0, 0))

    @commands.message_command(name="Quote Message")
    @collectCommandStats
    async def quote(self, ctx: discord.ApplicationContext, msg: discord.Message) -> bool:
        await ctx.response.defer()
        authorPfpUrl = msg.author.avatar.url
        authorPfpUrl = authorPfpUrl.replace(".gif", ".webp")

        pfp = await self.client.downloadFile(authorPfpUrl, IMAGE_CONTENT_TYPES)
        if pfp is None:
            await ctx.followup.send("**[i]** There was an error with your command execution.")
            return False

        base = Image.new("RGBA", (2048, 1024), color=(0, 0, 0, 255))

        pfpImage = Image.open(BytesIO(pfp[1])).convert("RGBA")
        pfpImage = pfpImage.resize((1024, 1024), resample=Image.Resampling.NEAREST)
        gradient = await self.generateLinearGradient(1024, 1024, (0, 0, 0, 0), (0, 0, 0, 255))
        expanded = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
        expanded.paste(gradient, (0, 0))
        quoteText = await self.renderQuote(f"\"{msg.content}\"")
        quoteAuthor = await self.renderAuthor(f"- {msg.author.display_name}")

        base.paste(pfpImage, (0, 0))
        base = Image.alpha_composite(base, expanded)
        base.paste(quoteText, (1024 + 200, 200), quoteText)
        base.paste(quoteAuthor, (2048 - 200 - self.QUOTE_BOUNDING_BOX[0], 200 + self.QUOTE_BOUNDING_BOX[1] + 10), quoteAuthor)

        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)

        await ctx.followup.send("**[i]** Your quote has been generated!", file=discord.File(buffer, filename="generated.png"))
        return True


def setup(bot: TZBot):
    bot.add_cog(Quote(bot))