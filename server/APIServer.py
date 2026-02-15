import asyncio
import json
import logging
import struct
from asyncio import Server, IncompleteReadError
from json import JSONDecodeError
from typing import Final, Optional

from cryptography.exceptions import InvalidTag

from server.protocol import Client, TCPClient, UDPProtocol
from server.requests import SimpleRequest, PingRequest, TimezoneFromUserIdRequest, TimezoneFromIPRequest, UserIdUUIDLinkPost, \
    TimezoneFromUUIDRequest, IsLinkedRequest, UserIdFromUUIDRequest, UUIDFromUserIdRequest
from shared import Helpers
from dtypes import APIPayload, PacketFlags, UInt8

log = logging.getLogger(__name__)

class APIServer:
    TCP_SERVER: Server = None
    UDP_SERVER: UDPProtocol

    REQUEST_TYPES: Final[list[type[SimpleRequest]]] = [
        PingRequest,
        TimezoneFromUserIdRequest,
        TimezoneFromIPRequest,
        UserIdUUIDLinkPost,
        TimezoneFromUUIDRequest,
        IsLinkedRequest,
        UserIdFromUUIDRequest,
        UUIDFromUserIdRequest
    ]

    transport: asyncio.DatagramTransport

    def __init__(this, tzBot: "TZBot") -> None:
        this.tzBot = tzBot
        this.db = tzBot.db
        this.serverConfig = tzBot.config.server
        this.aesKey: bytes = this.serverConfig.aesKey.encode()

    def getRequestType(this, index: UInt8) -> type[SimpleRequest]:
        try:
            return this.REQUEST_TYPES[index()]
        except IndexError:
            return SimpleRequest


    async def start(this) -> None:
        this.TCP_SERVER = await asyncio.start_server(this.TCPReceived, "0.0.0.0", this.serverConfig.port())
        this.UDP_SERVER = UDPProtocol(this)

        loop = asyncio.get_running_loop()
        transport, *_ = await loop.create_datagram_endpoint(lambda: this.UDP_SERVER, local_addr=("0.0.0.0", this.serverConfig.port()))
        this.transport = transport

        log.info("Server running!")

    async def respondToInvalid(this, msg: bytes, client: Client) -> None:
        if isinstance(client, TCPClient):
            protocol = "TCP"
        else:
            protocol = "UDP"

        log.warning(f"Got an invalid {protocol} request: {msg}")
        fakeJson: dict = {"requestType": "INVALID", "data": {"message": msg}}
        fakeJsonData: dict = fakeJson.pop("data")

        request = SimpleRequest(client, fakeJson, fakeJsonData, this.tzBot)
        await request.process()

    async def TCPReceived(this, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client: TCPClient = TCPClient(reader, writer, this.aesKey, this)
        try:
            req = await reader.read(65535)
            await this.respondToInvalid(req, client)
            return

        except Exception as e:
            log.warning(f"TCP Exception: {e!s}")
            writer.close()

    async def parsePacketInfo(this, msg: bytes) -> Optional[APIPayload]:
        tLetter, zLetter, *payload = struct.unpack(">BBBBBH", msg[0:7])
        if tLetter != ord("t") or zLetter != ord("z") or len(payload) != 4 or payload[0] < 7 or payload[-1] + payload[0] > len(msg):
            return None

        return APIPayload.fromTuple(payload)

    async def processRequest(this, msg: bytes, client: Client) -> None:
        if isinstance(client, TCPClient):
            protocol: str = "TCP"
        else:
            protocol: str = "UDP"

        payload: Optional[APIPayload] = await this.parsePacketInfo(msg)
        if not payload:
            await this.respondToInvalid(msg, client)
            return

        client.flags = payload.flags
        header = msg[:payload.dataOffset()]
        content = msg[payload.dataOffset():payload.contentLen() + payload.dataOffset()]

        appliedFlags = []

        # Process flags
        if payload.flags & PacketFlags.AESGCM and payload.flags & PacketFlags.CHACHAPOLY:
            log.warning("Used more encryption algorithms!")
            client.flags.value = 0
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
            log.error("Request with invalid tag, rejecting!")
            client.flags.value = 0
            await this.respondToInvalid(content, client)
            return

        if payload.flags & PacketFlags.GUNZIP:
            decompressed = Helpers.unGzip(content)
            if not decompressed:
                client.flags.value = 0
                await this.respondToInvalid(msg, client)
                return
            content = decompressed
            appliedFlags.append("GZIPped")

        if payload.flags & PacketFlags.MSGPACK:
            unpacked = Helpers.msgpackToJson(content)
            if not unpacked:
                client.flags.value = 0
                await this.respondToInvalid(msg, client)
                return
            content = unpacked
            appliedFlags.append("MSGPack")
        else:
            appliedFlags.append("JSON")

        try:
            jsonRequest: dict = json.loads(content.decode("utf-8", errors="ignore"))
        except (JSONDecodeError, TypeError):
            client.flags.value = 0
            await this.respondToInvalid(content, client)
            return

        reqType: type[SimpleRequest] = this.getRequestType(payload.requestType)
        payload: dict = jsonRequest.pop("data", {})

        if reqType != SimpleRequest:
            log.info(f"Got a known {protocol}, {", ".join(appliedFlags)} {reqType.__class__} request: {content.decode()}")
            request = reqType(client, jsonRequest, payload, this.tzBot)
            await request.process()

        else:
            await this.respondToInvalid(content, client)
