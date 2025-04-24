import json
import os
from database import Database
from enum import Enum
from logger import Logger
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad

def decrypt(encrypted_data: bytes, key: bytes) -> str | None:
    iv = encrypted_data[:16]
    data = bytearray(encrypted_data[16:])

    try:
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        decryptedData = cipher.decrypt(data)
        decryptedData = unpad(decryptedData, AES.block_size)
        return decryptedData.decode('utf-8').strip()
    except ValueError:
        return None

def encrypt(message: bytes, key: bytes) -> bytes:
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)

    paddedMessage = pad(message, AES.block_size)
    encryptedMessage = cipher.encrypt(paddedMessage)
    return iv + encryptedMessage

class EventHandler:
    def __init__(self):
        self.init_callbacks = []

    def onError(self, callback):
        self.init_callbacks.append(callback)

    def trigger(self, instance):
        for callback in self.init_callbacks:
            asyncio.create_task(callback(instance))

class SimpleRequest:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    database: Database
    data: dict
    key: bytes
    response: int = 0

    eventHandler: EventHandler = EventHandler()

    def __init__(this, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, database: Database, data: dict):
        this.reader = reader
        this.writer = writer
        this.database = database
        this.data = data
        this.key = str(json.loads(open("config.json", "r").read())["server"]["aesKey"]).encode()

    async def respond(this):
        pass

class TimeZoneRequest(SimpleRequest):
    userId: int | None

    def __init__(this, data: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, database: Database):
        super().__init__(reader, writer, database, data)
        this.userId = None
        this.userId = int(data.get("userId")) if str(data.get("userId")).isnumeric() else None
    
    async def respond(this) -> None:
        if(this.userId is None):
            await Server.badRequest(this)
            return

        message: str | None = this.database.getTimeZone(this.userId)
        this.response = 200
        if(message is None or message == ""):
            await Server.notFound(this)
            return

        await Server.sendResponse(this.key, this.writer, this.response, message)

class AliasFromUserRequest(SimpleRequest):
    userId: int | None

    def __init__(this, data: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, database: Database):
        super().__init__(reader, writer, database, data)
        this.userId = int(data.get("userId")) if str(data.get("userId")).isnumeric() else None

    async def respond(this) -> None:
        if(this.userId is None):
            await Server.badRequest(this)
            return

        message: str | None = this.database.getAlias(this.userId)
        this.response = 200
        if (message is None or message == ""):
            await Server.notFound(this)
            return

        await Server.sendResponse(this.key, this.writer, this.response, message)

class UserFromAliasRequest(SimpleRequest):
    alias: str

    def __init__(this, data: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, database: Database):
        super().__init__(reader, writer, database, data)
        this.alias = str(data.get("alias"))

    async def respond(this) -> None:
        message: str | None = this.database.getUserByAlias(this.alias)
        this.response = 200
        if (message is None or message == ""):
            await Server.notFound(this)
            return

        await Server.sendResponse(this.key, this.writer, this.response, message)

class TimeZoneFromAliasRequest(SimpleRequest):
    alias: str

    def __init__(this, data: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, database: Database):
        super().__init__(reader, writer, database, data)
        this.alias = str(data.get("alias"))

    async def respond(this) -> None:
        message: str | None = this.database.getTimeZoneByAlias(this.alias)
        this.response = 200
        if (message is None or message == ""):
            await Server.notFound(this)
            return

        await Server.sendResponse(this.key, this.writer, this.response, message)

class RequestType(Enum):
    TIMEZONE_REQUEST = TimeZoneRequest
    ALIAS_REQUEST = AliasFromUserRequest
    USER_FROM_ALIAS_REQUEST = UserFromAliasRequest
    TIMEZONE_FROM_ALIAS_REQUEST = TimeZoneFromAliasRequest

    def __call__(this, *args, **kwargs):
        return this.value(*args, **kwargs)

    @classmethod
    def get(cls, value, default=None):
        for member in cls:
            if member.value == value or member.value.__name__ == value:
                return member
        return default

class Server:
    serverSettings: dict
    database: Database
    eventHandler: EventHandler = EventHandler()
    
    def __init__(this, database: Database):
        this.database = database
        this.serverSettings = json.loads(open("config.json", "r").read())["server"]

    @staticmethod
    async def badRequest(request: SimpleRequest) -> None:
        Logger.error(f"Invalid {request.data["requestType"] if request.__class__.__name__ == "SimpleRequest" else RequestType.get(request.__class__.__name__)}. Received data: {request.data["data"] if request.__class__.__name__ == "SimpleRequest" else request.data}")
        request.response = 400
        request.eventHandler.trigger(request)
        await Server.sendResponse(request.key, request.writer, 400, "Bad Request")

    @staticmethod
    async def notFound(request: SimpleRequest) -> None:
        Logger.error(f"{request.data["data"] if request.__class__.__name__ == "SimpleRequest" else request.data} in {request.data["requestType"] if request.__class__.__name__ == "SimpleRequest" else RequestType.get(request)} not found.")
        request.response = 404
        request.eventHandler.trigger(request)
        await Server.sendResponse(request.key, request.writer, 404, "Not Found")

    @staticmethod
    async def badMethod(request: SimpleRequest) -> None:
        Logger.error(f"Invalid method {request.data["requestType"] if request.__class__.__name__ == "SimpleRequest" else RequestType.get(request)}. Received data: {request.data["data"] if request.__class__.__name__ == "SimpleRequest" else request.data}")
        request.response = 405
        request.eventHandler.trigger(request)
        await Server.sendResponse(request.key, request.writer, 405, "Method Not Allowed")

    @staticmethod
    async def sendResponse(key: bytes, writer: asyncio.StreamWriter, code: int, msg: str) -> None:
        message: dict[str: str, str: int] = {"message": msg, "code": code}
        messageStr: str = json.dumps(message)
        messageEnc: bytes = encrypt(messageStr.encode(), key)

        Logger.log(f"Responding with {messageStr}")
        writer.write(messageEnc)

        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def start(this):
        server = await asyncio.start_server(this.RequestDecoder, "0.0.0.0", int(this.serverSettings["port"]))
        try:
            async with server:
                Logger.log("Server create_taskning!")
                await server.serve_forever()
        except asyncio.CancelledError:
            Logger.log("Server shutting down!")

    async def RequestDecoder(this, client: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        key: bytes = str(this.serverSettings['aesKey']).encode()
        msg: bytes = await client.read(4096)

        data: str | None = decrypt(msg, key)

        if(data is None):
            Logger.error(f"Failed to decrypt the message. {msg}")
            await Server.sendResponse(key, writer, 400, "Bad Request")
            return

        Logger.log(f"Got message {data}")
        try:
            dct: dict = json.loads(data)
        except json.decoder.JSONDecodeError:
            Logger.error(f"Received an invalid packet.")
            await Server.sendResponse(key, writer, 400, "Bad Request")
            return

        if("requestType" in dct and "data" in dct):
            name, member = str(dct["requestType"]).split(".")
            try:
                reqType: RequestType = getattr(RequestType, member)
            except AttributeError:
                req = SimpleRequest(client, writer, this.database, dct)
                await Server.badMethod(req)
                return
            
            additionalData: dict = dct["data"]

            request: SimpleRequest = reqType(additionalData, client, writer, this.database)
            if(request is not None):
                await request.respond()