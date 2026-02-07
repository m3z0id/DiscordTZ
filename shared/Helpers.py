import asyncio
import gzip
import json
import logging
import os
import secrets
import string
import tempfile
import zlib
from io import BytesIO
from pathlib import Path
from typing import ParamSpec, TypeVar, Optional

import discord
import msgpack
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from msgpack import ExtraData, FormatError, StackError

from dtypes import UInt64
from shared import MAGICK_EXEC_FILE, BMPGEN_EXEC_FILE, HOSTS_PATTERN, HOSTS_FILE, HOSTNAME_FILE

P = ParamSpec("P")
R = TypeVar("R")

log = logging.getLogger(__name__)

class Helpers:
    @staticmethod
    async def getHosts() -> Optional[dict[str, str]]:
        try:
            with HOSTS_FILE.open("r") as f:
                content = f.read()
        except FileNotFoundError:
            log.fatal("Hosts file not found.")
            return None
        except PermissionError:
            log.fatal("Permission denied when trying to read /etc/hosts.")
            return None

        return dict(HOSTS_PATTERN.findall(content))

    @staticmethod
    async def getCountryOrHost(request: "SimpleRequest") -> str:
        hosts: Optional[dict[str, str]] = await Helpers.getHosts()

        if request.city:
            return request.city.country.iso_code

        if request.client.ip.is_loopback:
            with HOSTNAME_FILE.open("r") as f:
                return f.read().capitalize()

        if not hosts:
            return "Unknown"

        return hosts.get(str(request.client.ip), "Local").capitalize()

    @staticmethod
    def generateRandomNum(maximum: int, minimum: int = 0) -> int:
        if maximum < minimum:
            raise ValueError("Maximum cannot be smaller than minimum!")

        return secrets.randbelow(maximum - minimum) + minimum

    @staticmethod
    def generateCharSequence(n: int) -> str:
        return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))

    @staticmethod
    async def generateImage(r: str, g: str, b: str) -> Optional[BytesIO]:
        if not BMPGEN_EXEC_FILE.is_file() or not MAGICK_EXEC_FILE.is_file():
            log.error("BMPGen or ImageMagick is not present!")
            return None

        with tempfile.TemporaryDirectory() as tempDir:
            tempPath = Path(tempDir)
            
            bmpGen = await asyncio.create_subprocess_exec(
                BMPGEN_EXEC_FILE.absolute(), "-r", f"{r}", "-g", f"{g}", "-b", f"{b}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=tempPath
            )
            stdout, stderr = await bmpGen.communicate()

            if bmpGen.returncode != 0:
                log.error(f"There was an error generating BMP image. Return code: {bmpGen.returncode}")
                return None

            magick = await asyncio.create_subprocess_exec(
                MAGICK_EXEC_FILE.absolute(),
                "output.bmp",
                "-define",
                "png:compression-level=9",
                "-define",
                "png:compression-strategy=1",
                "output.png",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tempPath
            )
            stdout, stderr = await magick.communicate()

            if magick.returncode != 0:
                log.error(f"There was an error with conversion from BMP to PNG. Return code: {magick.returncode}")
                return None

            outputPng = tempPath / "output.png"
            if outputPng.exists():
                with outputPng.open("rb") as f:
                    return BytesIO(f.read())
            
            return None

    @staticmethod
    def AESDecrypt(msg: bytes, key: bytes, additional: Optional[bytes] = None) -> bytes:
        iv = msg[:12]
        ciphertext = msg[12:]

        cipher = AESGCM(key)
        return cipher.decrypt(iv, ciphertext, additional)

    @staticmethod
    def AESEncrypt(msg: bytes, key: bytes, additional: Optional[bytes] = None) -> bytes:
        iv = os.urandom(12)
        cipher = AESGCM(key)

        return iv + cipher.encrypt(iv, msg, additional)

    @staticmethod
    def ChaCha20Decrypt(msg: bytes, key: bytes, additional: Optional[bytes] = None) -> bytes:
        iv = msg[:12]
        ciphertext = msg[12:]

        cipher = ChaCha20Poly1305(key)
        return cipher.decrypt(iv, ciphertext, additional)

    @staticmethod
    def ChaCha20Encrypt(msg: bytes, key: bytes, additional: Optional[bytes]= None) -> bytes:
        iv = os.urandom(12)
        cipher = ChaCha20Poly1305(key)

        return iv + cipher.encrypt(iv, msg, additional)

    @staticmethod
    def unGzip(msg: bytes) -> Optional[bytes]:
        try:
            return gzip.decompress(msg)
        except zlib.error as e:
            log.error(f"Error while unzipping payload: {e!s}")
            return None

    @staticmethod
    def compressGzip(msg: bytes) -> bytes:
        return gzip.compress(msg)

    @staticmethod
    def msgpackToJson(msg: bytes) -> Optional[bytes]:
        try:
            obj = msgpack.unpackb(msg, raw=False)
            return json.dumps(obj).encode()
        except (ExtraData, FormatError, StackError, ValueError) as e:
            log.error(f"Error while unpacking from MSGPack: {e!s}")
            return None

    @staticmethod
    def jsonToMsgpack(msg: bytes) -> bytes:
        obj = json.loads(msg.decode())
        return msgpack.packb(obj)


def isOwner(ctx: discord.Interaction) -> bool:
    return ctx.client.isOwner(UInt64(ctx.user.id))
