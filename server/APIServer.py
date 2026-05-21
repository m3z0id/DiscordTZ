from __future__ import annotations

import asyncio
import copy
import json
import logging
import struct
from asyncio import Server
from json import JSONDecodeError
from typing import Final, Optional, TYPE_CHECKING

from cryptography.exceptions import InvalidTag

from dtypes import APIPayload, PacketFlags, UInt8, UInt16
from server.protocol import Client, TCPClient, UDPProtocol
from server.requests import SimpleRequest, PingRequest, TimezoneFromUserIdRequest, TimezoneFromIPRequest, \
    UserIdUUIDLinkPost, \
    TimezoneFromUUIDRequest, IsLinkedRequest, UserIdFromUUIDRequest, UUIDFromUserIdRequest, TimezoneAdjustRequest
from shared import Helpers

if TYPE_CHECKING:
    from modules import TZBot

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
        UUIDFromUserIdRequest,
        TimezoneAdjustRequest
    ]

    transport: asyncio.DatagramTransport

    def __init__(this, tzBot: TZBot) -> None:
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
        this.transport, *_ = await loop.create_datagram_endpoint(lambda: this.UDP_SERVER, local_addr=("0.0.0.0", this.serverConfig.port()))

        log.info("Server running!")

    async def respondToInvalid(this, msg: bytes, client: Client) -> None:
        log.warning(f"Got an invalid {client.getProtocolStringRepr()} request: {msg}")
        client.flags = PacketFlags.NONE
        fakeJson: dict = {"requestType": "INVALID", "data": msg}
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

        # Explicit otherwise it's always int
        return APIPayload(UInt8(payload[0]), UInt8(payload[1]), PacketFlags(payload[2]), UInt16(payload[3]))

    async def processRequest(this, msg: bytes, client: Client) -> None:
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
            await this.respondToInvalid(content, client)
            return

        contentObj: Optional[dict]
        if payload.flags & PacketFlags.MSGPACK:
            try:
                contentObj = Helpers.msgpackToJson(content)
                appliedFlags.append("MSGPack")
            except:
                log.error("Invalid MSGPack, rejecting!")
                await this.respondToInvalid(content, client)
                return
        else:
            try:
                contentObj: Optional[dict] = json.loads(content.decode("utf-8", errors="ignore"))
                appliedFlags.append("JSON")
            except (JSONDecodeError, TypeError):
                await this.respondToInvalid(content, client)
                return

        if contentObj is None:  # empty dict is falsy, explicit null check
            await this.respondToInvalid(content, client)
            return

        reqType: type[SimpleRequest] = this.getRequestType(payload.requestType)
        contentObjCopy = copy.deepcopy(contentObj)
        payload: dict = contentObj.pop("data", {})

        if reqType != SimpleRequest:
            request = reqType(client, contentObj, payload, this.tzBot)
            log.info(f"Got a known {client.getProtocolStringRepr()}, {", ".join(appliedFlags)} {request.packetNameStringRepr()} request: {contentObjCopy}")
            await request.process()

        else:
            await this.respondToInvalid(content, client)
