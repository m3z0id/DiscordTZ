import json
import os
from database import Database
from enum import Enum
from logger import Logger
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad

def decrypt(encrypted_data: bytes, key: bytes) -> str:
        if not isinstance(encrypted_data, (bytes, bytearray)):
            Logger.error("Encrypted data must be bytes or bytearray")
            return
    
        iv = encrypted_data[:16]
        data = bytearray(encrypted_data[16:])
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        decrypted_data = cipher.decrypt(data)
        decrypted_data = unpad(decrypted_data, AES.block_size)
        return decrypted_data.decode('utf-8').strip()

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
        response: dict = {}
        message: str | bool = this.database.get(this.userId)
        if(isinstance(message, bool)):
            response["message"] = "Failed"
            response["code"] = 404
        else:
            response["message"] = message
            response["code"] = 200    
        
        messageText = json.dumps(response)
        Logger.log(f"Responding with {messageText}")
        payload: bytes = encrypt(messageText.encode(), str(json.loads(open("config.json", "r").read())["server"]["aesKey"]).encode())

        this.writer.write(payload)
        await this.writer.drain()
        this.writer.close()
        await this.writer.wait_closed()

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

        data: str = decrypt(msg, key)
        Logger.log(f"Got message {data}")
        dct: dict = json.loads(data)

        if("requestType" in dct and "data" in dct):
            name, member = str(dct["requestType"]).split(".")
            try:
                reqType: RequestType = getattr(RequestType, member)
            except AttributeError:
                Logger.error(f"Received an invalid packet type. {dct["requestType"]}")
                return
            
            additionalData: dict = dct["data"]
            await reqType(additionalData, client, writer, this.database).respond()