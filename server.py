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

class GetRequest:
    userId: int
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    database: Database
    def __init__(this, data: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, database: Database):
        this.reader = reader
        this.writer = writer
        this.userId = int(data.get("userId"))
        this.database = database
        if(this.userId == None):
            Logger.error(f"Invalid GetRequest. Received data: {data}")
            this = None
    
    async def respond(this) -> str:
        key: bytes = str(json.loads(open("config.json", "r").read())["server"]["aesKey"]).encode()
        message: str | None = this.database.get(this.userId)
        code: int = 200
        if(message == None):
            message: str = "Not Found"
            code: int = 404

        Server.sendResponse(key, this.writer, code, message)

class RequestType(Enum):
    GET_REQUEST = GetRequest

    def __call__(this, *args, **kwargs):
        return this.value(*args, **kwargs)

class Server:
    serverSettings: dict
    database: Database
    def __init__(this, database: Database):
        this.database = database
        this.serverSettings = json.loads(open("config.json", "r").read())["server"]

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
                Logger.log("Server running!")
                await server.serve_forever()
        except asyncio.CancelledError:
            Logger.log("Server shutting down!")

    async def RequestDecoder(this, client: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        key: bytes = str(this.serverSettings['aesKey']).encode()
        msg: bytes = await client.read(4096)

        data: str | None = decrypt(msg, key)

        if(data == None):
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
                Logger.error(f"Received an invalid packet type. {dct["requestType"]}")
                await Server.sendResponse(key, writer, 405, "Method Not Allowed")
                return
            
            additionalData: dict = dct["data"]
            await reqType(additionalData, client, writer, this.database).respond()