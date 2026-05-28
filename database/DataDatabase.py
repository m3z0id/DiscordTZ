import logging
from typing import Optional
from uuid import UUID

from database.abstract.MDBSource import MDBSource
from database.abstract.SQLiteSource import SQLiteSource
from dtypes import MariaDBConfig, UInt8
from dtypes import UInt64
from shared import DB_FILE

log = logging.getLogger(__name__)
class DataDatabase:
    sqlite: SQLiteSource
    mdb: MDBSource

    def __init__(this, mdbConfig: MariaDBConfig) -> None:
        this.sqlite = SQLiteSource(DB_FILE)
        this.mdb = MDBSource(mdbConfig)

    async def asyncInit(this) -> None:
        sqliteStatements = [
            """
            CREATE TABLE IF NOT EXISTS timezones (
                user INTEGER PRIMARY KEY NOT NULL,
                timezone TEXT NOT NULL,
                lastUpdate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                uuid TEXT UNIQUE DEFAULT NULL
            );
            """,
            """
            CREATE TRIGGER IF NOT EXISTS onTimezonesUpdate
            AFTER UPDATE ON timezones
            BEGIN 
                UPDATE timezones SET lastUpdate = CURRENT_TIMESTAMP WHERE user = NEW.user;
            END;
            """
        ]
        await this.sqlite.asyncInit(sqliteStatements)

        mdbStatements = [
            """
            CREATE TABLE IF NOT EXISTS timezones (
                user BIGINT PRIMARY KEY NOT NULL,
                timezone TEXT NOT NULL,
                lastUpdate datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
                uuid uuid UNIQUE DEFAULT NULL
            );
            """
        ]
        await this.mdb.asyncInit(mdbStatements)

    async def setTimezone(this, userId: UInt64, timezone: str) -> UInt8:
        sqliteQuery = "INSERT INTO timezones (user, timezone) VALUES (?, ?) ON CONFLICT DO UPDATE SET timezone = ?"
        mdbQuery = "INSERT INTO timezones (user, timezone) VALUES (%s, %s) ON DUPLICATE KEY UPDATE timezone = VALUES(timezone)"

        result: int = 0
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute(sqliteQuery, (userId(), timezone, timezone))
            await conn.commit()
            result |= cur.rowcount != 0

        async with this.mdb.getConn() as conn, conn.cursor() as cur:
            await cur.execute(mdbQuery, (userId(), timezone))
            await conn.commit()
            result |= (cur.rowcount != 0) << 1

        return UInt8(0b11)

    async def setTimezoneUUID(this, uuid: UUID, timezone: str) -> UInt8:
        sqliteQuery = "UPDATE timezones SET timezone = ? WHERE uuid = ?"
        mdbQuery = sqliteQuery.replace("?", "%s")

        result: int = 0
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute(sqliteQuery, (timezone, str(uuid)))
            await conn.commit()
            log.info("SQLite: %d", cur.rowcount)
            result |= cur.rowcount != 0

        try:
            async with this.mdb.getConn() as conn, conn.cursor() as cur:
                await cur.execute(mdbQuery, (timezone, str(uuid)))
                await conn.commit()
                log.info("MDB: %d", cur.rowcount)
                result |= (cur.rowcount != 0) << 1
        except AttributeError as e:
            log.error(f"Attribute error: {e!s}")
            pass

        return UInt8(result)

    async def getTimezoneFromUserId(this, userId: UInt64) -> Optional[str]:
        sqliteQuery = "SELECT timezone from timezones WHERE user = ?"

        async with this.sqlite.getConn() as conn:
            res = await (await conn.execute(sqliteQuery, (userId(),))).fetchone()
            return str(res[0]) if res and hasattr(res, "__getitem__") else None

    async def getTimezoneFromUUID(this, uuid: UUID) -> Optional[str]:
        sqliteQuery = "SELECT timezone from timezones WHERE uuid = ?"

        async with this.sqlite.getConn() as conn:
            res = await (await conn.execute(sqliteQuery, (str(uuid),))).fetchone()
            return str(res[0]) if res and hasattr(res, "__getitem__") else None

    async def getUUIDFromUserId(this, userId: UInt64) -> Optional[UUID]:
        sqliteQuery = "SELECT uuid from timezones WHERE user = ?"

        try:
            async with this.sqlite.getConn() as conn:
                res = await (await conn.execute(sqliteQuery, (userId(),))).fetchone()
                return UUID(str(res[0])) if res and hasattr(res, "__getitem__") else None
        except ValueError:
            return None

    async def getUserIdFromUUID(this, uuid: UUID) -> Optional[UInt64]:
        sqliteQuery = "SELECT user from timezones WHERE uuid = ?"

        async with this.sqlite.getConn() as conn:
            res = await (await conn.execute(sqliteQuery, (str(uuid),))).fetchone()
            return UInt64(int(res[0])) if res and hasattr(res, "__getitem__") else None

    async def assignUUIDToUserId(this, uuid: UUID, userId: UInt64, timezone: str) -> bool:
        sqliteQuery = "INSERT INTO timezones (user, uuid, timezone) VALUES (?, ?, ?) ON CONFLICT(user) DO UPDATE SET uuid = ?;"
        mdbQuery = "INSERT INTO timezones (user, uuid, timezone) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE uuid = %s;"

        result: int = 0
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute(sqliteQuery, (userId(), str(uuid), timezone, str(uuid)))
            await conn.commit()
            result |= cur.rowcount != 0

        async with this.mdb.getConn() as conn, conn.cursor() as cur:
            await cur.execute(mdbQuery, (userId(), str(uuid), timezone, str(uuid)))
            await conn.commit()
            result |= (cur.rowcount != 0) << 1

        return result == 0b11

    async def unassignUUIDFromUserId(this, userId: UInt64) -> bool:
        query = "UPDATE timezones SET uuid = NULL WHERE user = ?"

        result: int = 0
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute(query, (userId(),))
            await conn.commit()
            result |= cur.rowcount != 0

        async with this.mdb.getConn() as conn, conn.cursor() as cur:
            await cur.execute(query.replace("?", "%s"), (userId(),))
            await conn.commit()
            result |= (cur.rowcount != 0) << 1

        return result == 0b11