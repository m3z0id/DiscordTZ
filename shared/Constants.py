import re
import shutil
from pathlib import Path
from typing import Final, Optional

import discord
import tzlocal

from dtypes import PresenceType, ActivityType, ColorSpace, TimezoneRepr

# Country Blacklist
BLACKLISTED_COUNTRIES: Final[set[str]] = {"SG", "CN", "MO", "HK", "TW", "RU"}

# Root
ROOT_DIR = Path(__file__).parent.parent

# Config
CONFIG_FILE: Final[Path] = ROOT_DIR / "config.json"

# Dir Structure
STATE_DIR = ROOT_DIR / "state"
MODULES_DIR: Final[Path] = ROOT_DIR / "modules"
TEMP_IMAGES_DIR: Final[Path] = ROOT_DIR / "temp"
DB_FILES_DIR: Final[Path] = ROOT_DIR / "dbFiles"
EXECS_DIR: Final[Path] = ROOT_DIR / "execs"

FONT_FILE: Final[Path] = STATE_DIR / "Monocraft.ttf"
GEO_IP_DB_FILE: Final[Path] = STATE_DIR / "GeoLite2-Country.mmdb"
COLORLIST_FILE: Final[Path] = STATE_DIR / "colorlist.bin"
PROFILE_FILE: Final[Path] = STATE_DIR / "profile.json"
MOD_BLACKLIST_FILE: Final[Path] = STATE_DIR / "blacklist.txt"

API_KEYS_DB_FILE: Final[Path] = DB_FILES_DIR / "apiKeys.db"
DB_FILE: Final[Path] = DB_FILES_DIR / "timezones.sqlite"

BMPGEN_EXEC_FILE: Final[Optional[Path]] = shutil.which("BMPGen")
MAGICK_EXEC_FILE: Final[Optional[Path]] = shutil.which("magick")
CHROMA_EXEC_FILE: Final[Optional[Path]] = shutil.which("chroma")

# System Files
ZONEINFO_DIR: Final[Path] = Path("/usr/share/zoneinfo/")
HOSTS_FILE: Final[Path] = Path("/etc/hosts")
HOSTNAME_FILE: Final[Path] = Path("/etc/hostname")

# Embeds
SUCCESS: Final[discord.Embed] = discord.Embed(title="**Success!**", description="The operation was successful!",
                                              color=discord.Color.green())
FAIL: Final[discord.Embed] = discord.Embed(title="**Something went wrong.**",
                                           description="There was an error in the operation.",
                                           color=discord.Color.red())

# HTTPS
IMAGE_CONTENT_TYPES: Final[set[str]] = {"image/bmp", "image/png", "image/jpeg", "image/webp"}
HTTP_HEADERS: Final[dict[str, str]] = {
    "User-Agent": "TZUtil",
    "Accept": "text/html,application/xhtml+xml,application/xml",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, zstd"  # exclude brotli
}

# Patterns for parsing
HOSTS_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b((?:10|192\.168|172\.(?:1[6-9]|2[0-9]|3[0-1]))(?:\.\d{1,3}){3})\s+(\S+)", re.IGNORECASE)
EMOJI_PATTERN: Final[re.Pattern[str]] = re.compile("<:[a-zA-Z0-9_-]{2,32}:(\\d{18,20})>")
URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_+.~#?&//=]*)")

# Response patterns
SORRY_PATTERN: Final[re.Pattern] = re.compile(r"sorry", re.IGNORECASE)
ROMANIA_PATTERN: Final[re.Pattern] = re.compile(r"(vampires?|st(eal|olen?))", re.IGNORECASE)

# Timezones
def _fetchTimezones() -> set[TimezoneRepr]:
    tzs: set[TimezoneRepr] = set()
    for topLevelDir in ZONEINFO_DIR.iterdir():
        if not topLevelDir.is_dir(): continue
        if topLevelDir.name.lower() in {"posix", "etc", "right"}: continue
        for zoneFile in topLevelDir.iterdir():
            tzs.add(TimezoneRepr(area=topLevelDir.name, city=zoneFile.name.replace("_", " ")))

    return tzs

LOCAL_TZ: Final[str] = tzlocal.get_localzone().key
TIMEZONES: Final[set[TimezoneRepr]] = _fetchTimezones()
TIMEZONE_CHECK_SET: Final[set[str]] = {tz.stringify() for tz in TIMEZONES}

# Quote module
QUOTE_DEFAULT_FONT_SIZE: Final[int] = 50
QUOTE_SMALLEST_FONT_SIZE: Final[int] = 15
QUOTE_START_COORDS: Final[tuple[int, int]] = 1024 + 200, 200
QUOTE_BOUNDING_BOX: Final[tuple[int, int]] = 624, 594

# Activity
ACTIVITY_TYPES: Final[list[ActivityType]] = ["unknown", "playing", "streaming", "listening", "watching"]
PRESENCE_TYPES: Final[list[PresenceType]] = ["online", "offline", "idle", "dnd", "invisible", "streaming"]

# Misc
VALID_COLOR_SPACES: Final[set[ColorSpace]] = {"rgb", "hsl", "oklab", "oklch", "okhsl"}
GEO_IP_URL: Final[str] = "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz"
DAY_SECONDS: Final[int] = 86_400
MAX_SHOWABLE_RESULTS: Final[int] = 25
VERIFY_CODE_LEN: Final[int] = 6
MAX_DATA_EMBED_LEN: Final[int] = 1500
MAX_TIMESTAMP: Final[int] = 253402300799

# Sandbox
SYSTEM_READ: Final[set[str]] = {
    "/usr/lib",
    "/usr/lib64",
    "/etc",
    "/usr/share",
}

SYSTEM_RW: Final[set[str]] = {
    "/tmp",
}