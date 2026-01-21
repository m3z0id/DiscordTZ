import asyncio
import gzip
import inspect
import ipaddress
import json
import os
import random
import re
import string
import tempfile
from io import BytesIO
from pathlib import Path
from typing import ParamSpec, TypeVar, Callable, Coroutine, Any, NewType

import msgpack
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from typing_extensions import Final
from typing_extensions import TypeIs

from shell.Logger import Logger

P = ParamSpec("P")
R = TypeVar("R")

def cleanupAfter(*attrs: Path | str) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        if not inspect.iscoroutinefunction(func):
            raise RuntimeError(f"{func.__name__} is not callable!")

        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = await func(*args, **kwargs)
            if result[0]:
                for path in attrs:
                    path.unlink(missing_ok=True)

            return result
        return wrapper
    return decorator

class Helpers:
    BLACKLISTED_COUNTRIES: set[str] = {"SG", "CN", "MO", "HK", "TW"}

    HOSTS_FILE: Final[Path] = Path("/etc/hosts")
    HOSTNAME_FILE: Final[Path] = Path("/etc/hostname")
    BMPGEN_EXEC_FILE: Final[Path] = Path("./execs/BMPGen")
    MAGICK_EXEC_FILE: Final[Path] = Path("/usr/bin/magick")

    UUIDStr = NewType("UUIDStr", str)
    IPv4Str = NewType("IPv4Str", str)

    tzBot: "TZBot" = None

    LOCAL_IP_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"""
                ^(?:
                    # Private ranges
                    10(?:\.\d{1,3}){3} |                            # 10.0.0.0/8
                    172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2} |    # 172.16.0.0 - 172.31.255.255
                    192\.168(?:\.\d{1,3}){2} |                     # 192.168.0.0/16

                    # Loopback
                    127(?:\.\d{1,3}){3} |                          # 127.0.0.0/8

                    # Link-local
                    169\.254(?:\.\d{1,3}){2} |                     # 169.254.0.0/16

                    # Carrier-grade NAT
                    100\.(?:6[4-9]|[7-9]\d|1[0-1]\d|12[0-7])(?:\.\d{1,3}){2} |  # 100.64.0.0/10

                    # Reserved for documentation
                    192\.0\.2\.\d{1,3} |                       # 192.0.2.0/24
                    198\.51\.100\.\d{1,3} |                    # 198.51.100.0/24
                    203\.0\.113\.\d{1,3} |                     # 203.0.113.0/24

                    # Reserved for future use
                    240(?:\.\d{1,3}){3} |                          # 240.0.0.0/4
                    255\.255\.255\.255 |                           # Broadcast

                    # IETF Protocol Assignments
                    192\.0\.0\.\d{1,3} |                       # 192.0.0.0/24

                    # Benchmarking
                    198\.18(?:\.\d{1,3}){2} |                      # 198.18.0.0/15
                    198\.19(?:\.\d{1,3}){2}
                )$
                """,
        re.VERBOSE,
    )
    HOSTS_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b((?:10|192\.168|172\.(?:1[6-9]|2[0-9]|3[0-1]))(?:\.\d{1,3}){3})\s+(\S+)", re.IGNORECASE)
    UUID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    @staticmethod
    async def getHosts() -> dict[str, str]:
        try:
            with Helpers.HOSTS_FILE.open("r") as f:
                content = f.read()
        except FileNotFoundError:
            Logger.error("Hosts file not found.")
            return {}
        except PermissionError:
            Logger.error("Permission denied when trying to read /etc/hosts.")
            return {}

        return dict(Helpers.HOSTS_PATTERN.findall(content))

    @staticmethod
    async def getCountryOrHost(request: "SimpleRequest") -> str:
        hosts: dict[str, str] = await Helpers.getHosts()

        if request.city:
            return request.city.country.iso_code

        if request.client.ip.address == "127.0.0.1":
            with Helpers.HOSTNAME_FILE.open("r") as f:
                return f.read().capitalize()

        return hosts.get(request.client.ip.address, "Local").capitalize()

    @staticmethod
    async def isLocalSubnet(ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    @staticmethod
    def isIP(ip: str) -> TypeIs[IPv4Str]:
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def isUUID(uniqueId: str) -> TypeIs[UUIDStr]:
        return bool(Helpers.UUID_PATTERN.match(uniqueId))

    @staticmethod
    async def generateCharSequence(n: int) -> str:
        return "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(n))

    @staticmethod
    async def generateImage(r: str, g: str, b: str) -> tuple[bool, BytesIO]:
        if not Helpers.BMPGEN_EXEC_FILE.is_file() or not Helpers.MAGICK_EXEC_FILE.is_file():
            Logger.error("BMPGen or ImageMagick is not present!")
            return False, BytesIO(b"")

        with tempfile.TemporaryDirectory() as tempDir:
            tempPath = Path(tempDir)
            
            bmpGen = await asyncio.create_subprocess_exec(
                Helpers.BMPGEN_EXEC_FILE.absolute(), "-r", f"{r}", "-g", f"{g}", "-b", f"{b}", 
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
                Helpers.MAGICK_EXEC_FILE.absolute(),
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
