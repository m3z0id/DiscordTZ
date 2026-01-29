import asyncio
import gzip
import ipaddress
import json
import os
import random
import string
import tempfile
from io import BytesIO
from pathlib import Path
from typing import ParamSpec, TypeVar

import msgpack
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from shared.Constants import MAGICK_EXEC_FILE, BMPGEN_EXEC_FILE, HOSTS_PATTERN, HOSTS_FILE, HOSTNAME_FILE, ZONEINFO_DIR
from shell.Logger import Logger

P = ParamSpec("P")
R = TypeVar("R")

class Helpers:
    tzBot: "TZBot" = None

    @staticmethod
    async def getHosts() -> dict[str, str]:
        try:
            with HOSTS_FILE.open("r") as f:
                content = f.read()
        except FileNotFoundError:
            Logger.error("Hosts file not found.")
            return {}
        except PermissionError:
            Logger.error("Permission denied when trying to read /etc/hosts.")
            return {}

        return dict(HOSTS_PATTERN.findall(content))

    @staticmethod
    async def getCountryOrHost(request: "SimpleRequest") -> str:
        hosts: dict[str, str] = await Helpers.getHosts()

        if request.city:
            return request.city.country.iso_code

        if request.client.ip.address == "127.0.0.1":
            with HOSTNAME_FILE.open("r") as f:
                return f.read().capitalize()

        return hosts.get(request.client.ip.address, "Local").capitalize()

    @staticmethod
    async def isLocalSubnet(ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    @staticmethod
    async def generateCharSequence(n: int) -> str:
        return "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(n))

    @staticmethod
    async def generateImage(r: str, g: str, b: str) -> tuple[bool, BytesIO]:
        if not BMPGEN_EXEC_FILE.is_file() or not MAGICK_EXEC_FILE.is_file():
            Logger.error("BMPGen or ImageMagick is not present!")
            return False, BytesIO(b"")

        with tempfile.TemporaryDirectory() as tempDir:
            tempPath = Path(tempDir)
            
            bmpGen = await asyncio.create_subprocess_exec(
                BMPGEN_EXEC_FILE.absolute(), "-r", f"{r}", "-g", f"{g}", "-b", f"{b}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=tempPath
            )
            stdout, stderr = await bmpGen.communicate()

            if bmpGen.returncode != 0:
                Logger.error(f"There was an error generating BMP image. Return code: {bmpGen.returncode}; stderr: {stderr.decode('utf-8', errors='ignore')}")
                Logger.error(f"Red: {r}")
                Logger.error(f"Green: {g}")
                Logger.error(f"Blue: {b}")
                return False, BytesIO(b"")

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
                Logger.error(f"There was an error with conversion from BMP to PNG. Return code: {magick.returncode}; stderr: {stderr.decode('utf-8', errors='ignore')}")
                return False, BytesIO(b"")

            outputPng = tempPath / "output.png"
            if outputPng.exists():
                with outputPng.open("rb") as f:
                    return True, BytesIO(f.read())
            
            return False, BytesIO(b"")


    @staticmethod
    def AESCBCDecrypt(msg: bytes, key: bytes) -> bytes | None:
        iv = msg[:16]
        data = msg[16:]

        try:
            cipher = AES.new(key, AES.MODE_CBC, iv=iv)
            decryptedData = cipher.decrypt(data)
            decryptedData = unpad(decryptedData, AES.block_size)
            return decryptedData.strip()
        except ValueError:
            return None

    @staticmethod
    def AESCBCEncrypt(message: bytes, key: bytes) -> bytes:
        iv = os.urandom(16)
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)

        paddedMessage = pad(message, AES.block_size)
        encryptedMessage = cipher.encrypt(paddedMessage)
        return iv + encryptedMessage

    @staticmethod
    def AESDecrypt(msg: bytes, key: bytes, additional: bytes | None = None) -> bytes:
        iv = msg[:12]
        ciphertext = msg[12:]

        cipher = AESGCM(key)
        return cipher.decrypt(iv, ciphertext, additional)

    @staticmethod
    def AESEncrypt(msg: bytes, key: bytes, additional: bytes | None = None) -> bytes:
        iv = os.urandom(12)
        cipher = AESGCM(key)

        return iv + cipher.encrypt(iv, msg, additional)

    @staticmethod
    def ChaCha20Decrypt(msg: bytes, key: bytes, additional: bytes | None = None) -> bytes:
        iv = msg[:12]
        ciphertext = msg[12:]

        cipher = ChaCha20Poly1305(key)
        return cipher.decrypt(iv, ciphertext, additional)

    @staticmethod
    def ChaCha20Encrypt(msg: bytes, key: bytes, additional: bytes | None = None) -> bytes:
        iv = os.urandom(12)
        cipher = ChaCha20Poly1305(key)

        return iv + cipher.encrypt(iv, msg, additional)

    @staticmethod
    def unGzip(msg: bytes) -> bytes | None:
        try:
            return gzip.decompress(msg)
        except Exception:
            return None

    @staticmethod
    def compressGzip(msg: bytes) -> bytes:
        return gzip.compress(msg)

    @staticmethod
    def msgpackToJson(msg: bytes) -> bytes | None:
        try:
            obj = msgpack.unpackb(msg, raw=False)
            return json.dumps(obj).encode()
        except Exception:
            return None

    @staticmethod
    def jsonToMsgpack(msg: bytes) -> bytes:
        obj = json.loads(msg.decode())
        return msgpack.packb(obj)
