import asyncio
from pathlib import Path
from typing import Final, LiteralString

import aiomysql
import aiosqlite

from config.Config import MariaDBConfig
from shared.Helpers import Helpers
from shell.Logger import Logger


class Database:
    DB_FILENAME: Final[Path] = Path("dbFiles/timezones.sqlite")

    def __init__(this, mdbConfig: MariaDBConfig) -> None:
        this.mdbConfig = mdbConfig

        asyncio.create_task(this._postInit())

    async def _postInit(this) -> None:
        this.conn = await aiosqlite.connect(this.DB_FILENAME)
        try:
            this.mdbPool = await aiomysql.create_pool(
                loop=asyncio.get_event_loop(),
                **this.mdbConfig.to_connection_params(),
            )
        except Exception:
            Logger.error("MDB is not available!")
            this.mdbPool = None

    async def executeSetQuery(this, query: LiteralString, mdbQuery: LiteralString, values: tuple) -> bool:
        cursor = await this.conn.execute(query, values)
        await this.conn.commit()

        if this.mdbPool:
            async with this.mdbPool.acquire() as conn, conn.cursor() as cur:
                await cur.execute(mdbQuery, values)

                return cursor.rowcount != 0 and cur.rowcount != 0
        return cursor.rowcount != 0

    async def executeGetStrQuery(this, query: LiteralString, values: tuple) -> str | None:
        cursor = await this.conn.execute(query, values)
        await this.conn.commit()
        if val := await cursor.fetchone():
            return val[0]

        return None

    async def setTimezone(this, userId: int, timezone: str, alias: str) -> bool:
        query = "INSERT INTO timezones (user, timezone) VALUES (?, ?)\
                 ON CONFLICT DO UPDATE SET timezone = ?, alias = ?;"
        mdbQuery = "INSERT INTO timezones (user, timezone) VALUES (%s, %s)\
                 ON DUPLICATE KEY UPDATE timezone = %s, alias = %s;"

        return await this.executeSetQuery(query, mdbQuery, (userId, timezone.replace(" ", "_"), alias, timezone.replace(" ", "_"), alias))

    async def getTimeZone(this, userId: int) -> str | None:
        query = "SELECT timezone from timezones WHERE user = ?"
        return await this.executeGetStrQuery(query, (userId,))

    async def assignUUIDToUserId(this, uuid: Helpers.UUIDStr, userId: int, timezone: str) -> bool:
        query = "INSERT INTO timezones (user, uuid, timezone, alias) VALUES (?, ?, ?, ?) ON CONFLICT(user) DO UPDATE SET uuid = ?;"
        mdbQuery = "INSERT INTO timezones (user, uuid, timezone, alias) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE uuid = %s;"

        return await this.executeSetQuery(query, mdbQuery, (userId, uuid, timezone.replace(" ", "_"), uuid, uuid))

    async def unassignUUIDFromUserId(this, userId: int) -> bool:
        query = "UPDATE timezones SET uuid = NULL WHERE user = ?"
        return await this.executeSetQuery(query, query.replace("?", "%s"), (userId,))

    async def getUUIDByUserId(this, userId: int) -> str | None:
        query = "SELECT uuid from timezones WHERE user = ?"
        return await this.executeGetStrQuery(query, (userId,))

    async def getUserIdByUUID(this, uuid: Helpers.UUIDStr) -> str | None:
        query = "SELECT user from timezones WHERE uuid = ?"
        return await this.executeGetStrQuery(query, (uuid,))

    async def getTimezoneByUUID(this, uuid: Helpers.UUIDStr) -> str | None:
        query = "SELECT timezone from timezones WHERE uuid = ?"
        return await this.executeGetStrQuery(query, (uuid,))
