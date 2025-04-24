import mariadb
import os
from logger import Logger

class Database:
    conn: mariadb.Connection
    tableName: str

    def __init__(this, connectionDetails: dict):
        this.conn = mariadb.connect(
            database=connectionDetails.get("database"),
            user=connectionDetails.get("user"),
            password=connectionDetails.get("password"),
            host=connectionDetails.get("host"),
            port=int(connectionDetails.get("port")),
            autocommit=bool(connectionDetails.get("autocommit"))
        )
        this.tableName = connectionDetails.get("tableName")
        
    def set(this, userId: int, timezone: str, alias: str) -> bool:
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"INSERT into {this.tableName} (user, timezone, alias) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE timezone = VALUES(timezone), alias = VALUES(alias);"

        data: tuple[int, str, str] = (userId, timezone.replace(" ", "_"), alias)

        try:
            cursor.execute(query, data)
            conn.commit()
            return True
        except mariadb.Error as e:
            Logger.error(f"Error while writing data to database: {e}")
            return False

    def setAlias(this, userId: int, alias: str) -> bool:
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"INSERT into {this.tableName} (user, alias) VALUES (%s, %s) ON DUPLICATE KEY UPDATE alias = VALUES(alias);"

        data: tuple[int, str] = (userId, alias)

        try:
            cursor.execute(query, data)
            conn.commit()
            return True
        except mariadb.Error as e:
            Logger.error(f"Error while writing data to database: {e}")
            return False
        
    def getTimeZone(this, userId: int) -> str | None:
        if (not isinstance(userId, int)):
            return None
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"SELECT timezone from {this.tableName} WHERE user = %s"
        data: list[int] = [userId]

        try:
            cursor.execute(query, data)
            conn.commit()

            result = cursor.fetchone()

            if(result):
                return str(result[0])
            else:
                return this.defaultTz()

        except mariadb.Error as e:
            Logger.error(e)
            return None

    def getAlias(this, userId: int) -> str | None:
        if (not isinstance(userId, int)):
            return None
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"SELECT alias from {this.tableName} WHERE user = %s"
        data: list[int] = [userId]
        try:
            cursor.execute(query, data)
            conn.commit()
            result = cursor.fetchone()
            if(result):
                return str(result[0])
            else:
                return None

        except mariadb.Error as e:
            Logger.error(e)
            return None

    def getUserByAlias(this, alias: str) -> str | None:
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"SELECT user from {this.tableName} WHERE alias = %s"
        data: list[str] = [alias]
        try:
            cursor.execute(query, data)
            conn.commit()
            result = cursor.fetchone()
            if(result):
                return str(result[0])
            else:
                return None

        except mariadb.Error as e:
            Logger.error(e)
            return None

    def getTimeZoneByAlias(this, alias: str) -> str | None:
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"SELECT timezone from {this.tableName} WHERE alias = %s"
        data: list[str] = [alias]
        try:
            cursor.execute(query, data)
            conn.commit()
            result = cursor.fetchone()
            if(result):
                return str(result[0])
            else:
                return None

        except mariadb.Error as e:
            Logger.error(e)
            return None

    def defaultTz(this) -> str:
        temp: list[str] = os.readlink("/etc/localtime").split("/")
        return f"{temp[-2]}/{temp[-1]}"
            