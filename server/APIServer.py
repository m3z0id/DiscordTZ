import asyncio
import json
import struct
from asyncio import Server, IncompleteReadError
from json import JSONDecodeError
from typing import Final, TypedDict, NotRequired

from cryptography.exceptions import InvalidTag

from server.protocol.APIPayload import APIPayload, PacketFlags
from server.protocol.Client import Client
from server.protocol.TCP import TCPClient
from server.protocol.UDP import UDPProtocol
from server.requests.AbstractRequests import SimpleRequest, RequestDataPayload, RequestHeaders
from server.requests.Requests import PingRequest, TimeZoneRequest, TimeZoneFromIPRequest, UserIdUUIDLinkPost, \
    TimezoneFromUUIDRequest, IsLinkedRequest, UserIDFromUUIDRequest, UUIDFromUserIDRequest
from shared.Helpers import Helpers
from shell.Logger import Logger


class APIServer:
    TCP_SERVER: Final[Server]
    UDP_SERVER: Final[UDPProtocol]
    _STOP_EVENT: Final[asyncio.Event]

    REQUEST_TYPES: Final[list[type[SimpleRequest]]] = [
        PingRequest,
        TimeZoneRequest,
        TimeZoneFromIPRequest,
        UserIdUUIDLinkPost,
        TimezoneFromUUIDRequest,
        IsLinkedRequest,
        UserIDFromUUIDRequest,
        UUIDFromUserIDRequest
    ]

    transport: asyncio.DatagramTransport

    def __init__(this, tzBot: "TZBot") -> None:
        this.tzBot = tzBot
        this.db = tzBot.db
        this.serverConfig = tzBot.config.server
        this.aesKey: bytes = this.serverConfig.aesKey.encode()
        this._STOP_EVENT = asyncio.Event()

    def getRequestType(this, index: int) -> type[SimpleRequest]:
        try:
            return this.REQUEST_TYPES[index]
        except IndexError:
            return SimpleRequest


    async def start(this) -> None:
        this.TCP_SERVER = await asyncio.start_server(this.TCPReceived, "0.0.0.0", int(this.serverConfig.port))
        this.UDP_SERVER = UDPProtocol(this)

        loop = asyncio.get_running_loop()
        transport, *_ = await loop.create_datagram_endpoint(lambda: this.UDP_SERVER, local_addr=("0.0.0.0", int(this.serverConfig.port)))
        this.transport = transport

        Logger.success("Server running!")
        try:
            await this._STOP_EVENT.wait()
        finally:
            Logger.log("Server shutting down!")

    async def stop(this):
        this.TCP_SERVER.close()
        this.UDP_SERVER.close()
        this._STOP_EVENT.set()

    async def TCPReceived(this, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client: TCPClient = TCPClient(reader, writer, this.aesKey, this)
        try:
            magic = await reader.readexactly(2)
            if magic != b"tz":
                rest = magic + await reader.read(65535)
                await this.respondToInvalid(rest, client)
                return

            headerLen = int.from_bytes(await reader.readexactly(1), "big")
            rest = await reader.readexactly(headerLen)

            header = magic + headerLen.to_bytes(1, "big") + rest

            if len(header) < 7:
                writer.close()
                return

            bodyLen = int.from_bytes(header[5:7], "big")
            body = await reader.readexactly(bodyLen)

            msg = header + body

            client: TCPClient = TCPClient(reader, writer, this.aesKey, this)
            await this.processRequest(msg, client)
        except IncompleteReadError as e:
            Logger.error(f"Didn't get enough bytes to check for header! {e!s}")
            writer.close()

    async def parsePacketInfo(this, msg: bytes) -> APIPayload | None:
        tLetter, zLetter, *payload = struct.unpack(">BBBBBH", msg[0:7])
        if tLetter != ord("t") or zLetter != ord("z") or len(payload) != 4 or payload[0] < 7 or payload[-1] + payload[0] > len(msg):
            return None

        return APIPayload.fromTuple(payload)

class JsonPacketEnvelope(TypedDict):
    requestType: int | str
    data: RequestDataPayload
    headers: NotRequired[RequestHeaders]


    async def respondToInvalid(this, msg: str | bytes, client: Client):
        if isinstance(client, TCPClient):
            protocol = "TCP"
        else:
            protocol = "UDP"

        # [SAFETY] Safely decode bytes; prevent JSON serialization crash
        safe_msg: str = msg.decode('utf-8', errors='replace') if isinstance(msg, bytes) else msg

        Logger.log(f"Got an invalid {protocol} request: {safe_msg}")
        
        fakeJson: JsonPacketEnvelope = {
            "requestType": "INVALID",
            "data": {"message": safe_msg}
        }

        # Extract data, explicitly typed as BaseData (compatible with RequestDataPayload)
        fakeData = fakeJson["data"]

        request = SimpleRequest(client, {}, fakeData, this.tzBot)
        await request.process()
        return

    async def processRequest(this, msg: bytes, client: Client) -> None:
        await this.tzBot.statsDb.addReceivedDataBandwidth(len(msg))

        if isinstance(client, TCPClient):
            protocol: str = "TCP"
        else:
            protocol: str = "UDP"

        await this.tzBot.statsDb.addProtocol(protocol)

        payload: APIPayload | None = await this.parsePacketInfo(msg)
        if not payload:
            await this.respondToInvalid(msg, client)
            return

        client.flags = payload.flags
        header = msg[:payload.dataOffset]
        content = msg[payload.dataOffset:payload.contentLen + payload.dataOffset]

        appliedFlags = []

        # Process flags
        if payload.flags & PacketFlags.AESGCM and payload.flags & PacketFlags.CHACHAPOLY:
            Logger.error("Used more encryption algorithms!")
            client.flags = 0
            await this.respondToInvalid(content, client)
            return

        try:
            if payload.flags & PacketFlags.AESGCM:
                content = Helpers.AESDecrypt(content, this.aesKey, header)
                appliedFlags.append("AES-256-GCM encrypted")

            elif payload.flags & PacketFlags.CHACHAPOLY:
                content = Helpers.ChaCha20Decrypt(content, this.aesKey, header)
                appliedFlags.append("ChaCha20-Poly1305 encrypted")

            else:
                appliedFlags.append("unencrypted")

        except InvalidTag:
            Logger.error("Request with invalid tag, rejecting!")
            client.flags = 0
            await this.respondToInvalid(content, client)
            return

        if payload.flags & PacketFlags.GUNZIP:
            decompressed = Helpers.unGzip(content)
            if not decompressed:
                client.flags = 0
                await this.respondToInvalid(msg, client)
                return
            content = decompressed
            appliedFlags.append("GZIPped")

        if payload.flags & PacketFlags.MSGPACK:
            unpacked = Helpers.msgpackToJson(content)
            if not unpacked:
                client.flags = 0
                await this.respondToInvalid(msg, client)
                return
            content = unpacked
            appliedFlags.append("MSGPack")
        else:
            appliedFlags.append("JSON")

        try:
            jsonRequest: dict = json.loads(content.decode("utf-8", errors="ignore"))
        except (JSONDecodeError, TypeError):
            client.flags = 0
            await this.respondToInvalid(content, client)
            return

        reqType: type[SimpleRequest] = this.getRequestType(payload.requestType)
        payload: dict = jsonRequest.pop("data", {})

        if reqType != SimpleRequest:
            Logger.log(f"Got a known {protocol}, {", ".join(appliedFlags)} request: {content.decode()}")
            request = reqType(client, jsonRequest, payload, this.tzBot)
            await request.process()

            await this.tzBot.statsDb.addEstablishedKnownRequestType(request.packetNameStringRepr())
        else:
            await this.respondToInvalid(content, client)
