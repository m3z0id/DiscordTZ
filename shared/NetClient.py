import logging
from io import BytesIO
from typing import Final, Optional

import aiohttp
from aiohttp import BasicAuth, ClientResponseError

from shared import HTTP_HEADERS

log = logging.getLogger(__name__)
class NetClient:
    client: Final[aiohttp.ClientSession]

    def __init__(this) -> None:
        this.client = aiohttp.ClientSession(headers=HTTP_HEADERS)

    async def downloadFile(this, url: str, *, mimeTypes: Optional[set[str]] = None, auth: Optional[BasicAuth] = None) -> Optional[tuple[str, BytesIO]]:
        headers = HTTP_HEADERS.copy()
        if mimeTypes:
            headers["Accept"] = ",".join(mimeTypes)
        try:
            async with this.client as c, c.get(url, auth=auth) as response:
                if not str(response.status).startswith("2"):
                    log.error(f"Failed to download from {url}: {response.status}")
                    return None

                return response.content_type, BytesIO(await response.read())

        except ClientResponseError as e:
            log.error(f"Download failed: {e!s}")
            return None