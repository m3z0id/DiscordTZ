import logging
from typing import Optional

from database.abstract.SQLiteSource import SQLiteSource
from shared import API_KEYS_DB_FILE
from dtypes import UInt64

log = logging.getLogger(__name__)

class APIKeyDatabase:
    sqlite: SQLiteSource
    
    def __init__(this) -> None:
        this.sqlite = SQLiteSource(API_KEYS_DB_FILE)

    async def asyncInit(this) -> None:
        statements: list[str] = [
            """
            CREATE TABLE IF NOT EXISTS pendingApiKeys (
                jwt TEXT PRIMARY KEY NOT NULL,
                messageId BIGINT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS apiKeys (
                jwt TEXT PRIMARY KEY NOT NULL
            );
            """
        ]

        await this.sqlite.asyncInit(statements)

    async def addKeyToPending(this, apiKey: str, msgId: UInt64) -> None:
        async with this.sqlite.getConn() as conn:
            await conn.execute("INSERT INTO pendingApiKeys (jwt, messageId) VALUES (?, ?)", (apiKey, msgId()))
            await conn.commit()

    async def makeKeyValid(this, apiKey: str) -> None:
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute("DELETE FROM pendingApiKeys WHERE jwt = ?", (apiKey,))
            await conn.commit()

            if cur.rowcount < 0:
                log.error("Could not find API key to move to.")
                return

            await conn.execute("INSERT INTO apiKeys (jwt) VALUES (?)", (apiKey,))
            await conn.commit()

    async def getPendingKeyByMsgId(this, msgId: UInt64) -> Optional[str]:
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute("SELECT jwt FROM pendingApiKeys WHERE messageId = ?", (msgId(),))
            rows = await cur.fetchone()
            return rows[0] if rows and hasattr(rows, "__getitem__") else None

    async def denyKey(this, msgId: UInt64) -> None:
        async with this.sqlite.getConn() as conn:
            await conn.execute("DELETE FROM pendingApiKeys WHERE messageId = ?", (msgId(),))
            await conn.commit()

    async def isKeyValid(this, apiKey: str) -> bool:
        async with this.sqlite.getConn() as conn:
            cur = await conn.execute("SELECT EXISTS(SELECT 1 FROM apiKeys WHERE jwt = ?)", (apiKey,))
            rows = await cur.fetchone()

            return rows[0] if rows and hasattr(rows, "__getitem__") else False
