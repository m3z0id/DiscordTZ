import logging
from io import BytesIO
from ipaddress import IPv4Address
from pathlib import Path
from typing import TYPE_CHECKING, Self, Optional

import geoip2.database
import geoip2.errors
import maxminddb.errors
from aiohttp import BasicAuth

from shared import Helpers, DAY_SECONDS, GEO_IP_URL

if TYPE_CHECKING:
    from modules import TZBot

log = logging.getLogger(__name__)

class GeoIP:
    tzBot: TZBot
    dbPath: Path
    _maxMindDb: geoip2.database.Reader

    def __init__(this, tzBot: TZBot, dbPath: Path) -> None:
        this.tzBot = tzBot
        this.dbPath = dbPath

    @classmethod
    async def create(cls, tzBot: TZBot, dbPath: Path) -> Self:
        obj = cls(tzBot, dbPath)

        if obj._shouldDownload():
            await obj._download()

        obj._maxMindDb = geoip2.database.Reader(obj.dbPath)
        return obj


    def _shouldDownload(this) -> bool:
        if not this.dbPath.is_file(): return True
        if not (age := Helpers.getFileAge(this.dbPath)) or age > DAY_SECONDS: return True

        try:
            this._maxMindDb: geoip2.database.Reader = geoip2.database.Reader(this.dbPath)
            log.info("Skipping GeoLite2 database download, it was updated less than 24 hours ago.")
            return False
        except maxminddb.errors.InvalidDatabaseError:
            return True

    async def _download(this) -> None:
        maxmindConfig = this.tzBot.config.maxmind
        contentType, archive = await this.tzBot.netClient.downloadFile(GEO_IP_URL, mimeTypes=["application/gzip", "application/xml"], auth=BasicAuth(str(maxmindConfig.accountId), maxmindConfig.token))

        if not (mmdb := Helpers.getFileFromTar(archive, "/GeoLite2-City.mmdb")):
            log.fatal("Failed to fetch GeoLite2!")
            return

        with this.dbPath.open("wb") as f:
            f.write(mmdb)

    def city(this, ip: IPv4Address) -> Optional[geoip2.database.City]:
        try:
            return this._maxMindDb.city(str(ip))
        except geoip2.errors.AddressNotFoundError:
            return None