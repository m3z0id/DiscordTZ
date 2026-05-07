import asyncio
import contextlib
from asyncio import DatagramTransport
from typing import Final, TYPE_CHECKING, override

from dtypes import PacketFlags, ValidProtocol
from server.protocol import Client

if TYPE_CHECKING:
    from server.APIServer import APIServer

class UDPClient(Client):
    def __init__(this, transport: asyncio.DatagramTransport, ipAddress: tuple[str, int], aesKey: bytes, server: APIServer, flags: PacketFlags = PacketFlags.NONE) -> None:
        super().__init__(ipAddress, aesKey, flags, server)
        this.transport: asyncio.DatagramTransport = transport

    async def send(this, data: dict) -> None:
        finalData = this._applyFlags(data)
        this.transport.sendto(finalData, (str(this.ip), this.port()))

    @override
    def getProtocolStringRepr(this) -> ValidProtocol:
        return "UDP"


class UDPProtocol(asyncio.DatagramProtocol):
    _STOP_EVENT: Final[asyncio.Event]

    def __init__(this, server: APIServer) -> None:  # noqa: ANN001
        this.server = server
        this.transport: DatagramTransport = None

        this._STOP_EVENT = asyncio.Event()

    def connection_made(this, transport: DatagramTransport) -> None:
        this.transport = transport

    def datagram_received(this, data: bytes, addr: tuple[str, int]) -> None:
        client: UDPClient = UDPClient(this.transport, addr, this.server.aesKey, this.server)
        if not data.startswith(b"tz"):
            asyncio.create_task(this.server.respondToInvalid(data, client))
            return

        asyncio.create_task(this.server.processRequest(data, client))

    def close(this):
        this.transport.close()
        with contextlib.suppress(asyncio.CancelledError, TypeError):
            this._STOP_EVENT.set()