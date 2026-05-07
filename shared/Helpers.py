import asyncio
import logging
import os
import secrets
import string
import sys
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import Path
from tarfile import TarFile
from typing import Optional, TYPE_CHECKING, Any, cast
from uuid import UUID

import discord
import msgpack
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from dtypes import UInt64, FileAccessType, UInt32, TimezoneRepr
from shared import MAGICK_EXEC_FILE, BMPGEN_EXEC_FILE, HOSTS_PATTERN, HOSTS_FILE, HOSTNAME_FILE

if TYPE_CHECKING:
    from server.requests.AbstractRequests import SimpleRequest
    from modules import TZBot

log = logging.getLogger(__name__)

class Helpers:
    @staticmethod
    def isFileAccessible(path: Path, flags: FileAccessType) -> bool:
        return path.is_file() and os.access(path, flags)

    @staticmethod
    def isFileR(path: Path) -> bool:
        return Helpers.isFileAccessible(path, FileAccessType.R_OK)

    @staticmethod
    def isFileRW(path: Path) -> bool:
        return Helpers.isFileAccessible(path, FileAccessType.R_OK | FileAccessType.W_OK)

    @staticmethod
    def isFileRX(path: Path) -> bool:
        return Helpers.isFileAccessible(path, FileAccessType.R_OK | FileAccessType.X_OK)

    @staticmethod
    def createDirOrGet(path: Path) -> Path:
        if path.is_dir(): return path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def addDirToPath(path: Path) -> None:
        if not path.is_dir(): raise ValueError(f"{path.as_posix()} must be a directory!")
        sys.path.insert(0, str(path))

    @staticmethod
    async def getHosts() -> dict[str, str]:
        try:
            with HOSTS_FILE.open("r") as f:
                content = f.read()
        except FileNotFoundError:
            log.fatal("Hosts file not found.")
            return {}
        except PermissionError:
            log.fatal("Permission denied when trying to read /etc/hosts.")
            return {}

        return dict(HOSTS_PATTERN.findall(content))

    @staticmethod
    async def getCountryOrHost(request: SimpleRequest) -> str:
        hosts: dict[str, str] = await Helpers.getHosts()

        if request.client.ip.is_loopback:
            with HOSTNAME_FILE.open("r") as f:
                return f.read().capitalize()

        if host := hosts.get(str(request.client.ip)):
            return host

        if isoCode := request.country.country.iso_code:
            return isoCode

        return "Unknown"

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
        if not (BMPGEN_EXEC_FILE and MAGICK_EXEC_FILE):
            log.error("BMPGen or ImageMagick is not present!")
            return None

        with tempfile.TemporaryDirectory() as tempDir:
            tempPath = Path(tempDir)
            
            bmpGen = await asyncio.create_subprocess_exec(
                BMPGEN_EXEC_FILE, "-r", f"{r}", "-g", f"{g}", "-b", f"{b}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=tempPath
            )
            stdout, stderr = await bmpGen.communicate()

            if bmpGen.returncode != 0:
                log.error(f"There was an error generating BMP image. Return code: {bmpGen.returncode}")
                return None

            magick = await asyncio.create_subprocess_exec(
                MAGICK_EXEC_FILE,
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
            if Helpers.isFileR(outputPng):
                with outputPng.open("rb") as f:
                    return BytesIO(f.read())
            
            return None

    @staticmethod
    def getFileAge(path: Path) -> Optional[int]:
        """ Returns the file age in seconds. """
        if path.is_file(): return None
        currentTime = time.time()
        return int(currentTime - path.stat().st_ctime)

    @staticmethod
    def getFileFromTar(inMemoryFile: BytesIO, inTarPath: str) -> Optional[bytes]:
        if not tarfile.is_tarfile(inMemoryFile): return None
        with tarfile.open(fileobj=inMemoryFile) as tar:
            tar: TarFile
            for member in tar:
                if member.isfile() and member.path.endswith(inTarPath):
                    extracted = tar.extractfile(member)
                    if extracted:
                        return extracted.read()

            log.error("Failed to find the desired file in the TAR.")
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
    def msgpackToJson(msg: bytes) -> Optional[dict]:
        return msgpack.unpackb(msg, raw=False)

    @staticmethod
    def jsonToMsgpack(obj: dict) -> bytes:
        return msgpack.packb(obj)

    @staticmethod
    def patchPidFile(rootDir: Path) -> None:
        pidFile = rootDir / "pid"

        if not Helpers.isFileAccessible(pidFile, FileAccessType.W_OK):
            raise PermissionError(f"The PID file {pidFile} does not exist or is unwritable.")

        with pidFile.open("w") as f:
            f.write(str(os.getpid()))

    @staticmethod
    def hasUnderlyingDisable(obj: Any) -> bool:
        return hasattr(obj, "_underlying") and hasattr(obj._underlying, "disable") and isinstance(obj._underlying.disable, bool)

class TChecker:
    @staticmethod
    def expectUUID(data: Any) -> UUID:
        if not isinstance(data, str):
            raise ValueError("Data must a string.")

        return UUID(data)

    @staticmethod
    def expectUInt64(data: Any) -> UInt64:
        if not isinstance(data, int):
            raise ValueError("Data must be an integer.")

        return UInt64.boundsChecked(data)

    @staticmethod
    def expectUInt32(data: Any) -> UInt32:
        if not isinstance(data, int):
            raise ValueError("Data must be an integer.")

        return UInt32.boundsChecked(data)

    @staticmethod
    def expectTimezone(data: Any) -> TimezoneRepr:
        return TimezoneRepr.fromString(data)

    @staticmethod
    def expectTZBot(botClient: discord.Client) -> TZBot:
        if not isinstance(botClient, TZBot):
            raise ValueError("The botClient is not a TZBot!")

        return cast(TZBot, botClient)

def isOwner(ctx: discord.Interaction) -> bool:
    return TChecker.expectTZBot(ctx.client).isOwner(UInt64(ctx.user.id))
