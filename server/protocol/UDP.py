import asyncio
import contextlib
from asyncio import Queue
from typing import Final

from server.protocol.APIPayload import PacketFlags
from server.protocol.Client import Client


class UDPClient(Client):
    def __init__(this, transport: asyncio.DatagramTransport, ipAddress: tuple[str, int], aesKey: bytes, server: "APIServer", flags: PacketFlags = 0) -> None:
        super().__init__(ipAddress, aesKey, flags, server)
        this.transport: asyncio.DatagramTransport = transport

    async def send(this, data: bytes) -> None:
        finalData = await this._applyFlags(data)
        this.transport.sendto(finalData, tuple(this.ip))


class UDPProtocol(asyncio.DatagramProtocol):
    _STOP_EVENT: Final[asyncio.Event]

    def __init__(this, server: "APIServer") -> None:  # noqa: ANN001
        this.server = server
        this.transport: asyncio.transports.DatagramTransport | None = None
        this.requestQueue: Queue[tuple[bytes, UDPClient]] = Queue()

        this._STOP_EVENT = asyncio.Event()

    def connection_made(this, transport: asyncio.transports.DatagramTransport) -> None:
        this.transport = transport

    def datagram_received(this, data: bytes, addr: tuple[str, int]) -> None:
        client: UDPClient = UDPClient(this.transport, addr, this.server.aesKey, this.server)
        if not data.startswith(b"tz"):
            asyncio.create_task(this.server.respondToInvalid(data, client))
            return

        asyncio.create_task(this.server.processRequest(data, client))

    def close(this):
        this.transport.close()
        this.requestQueue.empty()
        with contextlib.suppress(asyncio.CancelledError, TypeError):
            this._STOP_EVENT.set()
