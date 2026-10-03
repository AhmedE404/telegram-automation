"""
Central configuration — all settings loaded from environment variables.
Add new env vars here; never scatter os.getenv() calls across the codebase.
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Raise a clear error if a required env variable is missing."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Check your .env file."
        )
    return value.strip()


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_API_ID: int = int(_require("API_ID"))
TELEGRAM_API_HASH: str = _require("API_HASH")

# Path for the Telethon session file (relative to project root, normalized for all OS)
SESSION_NAME: str = os.path.normpath(os.getenv("SESSION_NAME", "session/telegram"))

# ── Channels ──────────────────────────────────────────────────────────────────
# Permanent private test channel (saved for developing and testing automations)
TEST_CHANNEL_ID: str = os.getenv("TEST_CHANNEL_ID", "").strip()

# Channel monitoring mode:
#   "production" (default) — listen to production channels only (USE_TEST_CHANNEL=false)
#   "test"                 — listen to TEST_CHANNEL_ID only (USE_TEST_CHANNEL=true)
#   "both"                 — listen to BOTH production and TEST_CHANNEL_ID simultaneously (USE_TEST_CHANNEL=both)
_raw_channel_mode: str = os.getenv("USE_TEST_CHANNEL", "false").strip().lower()
if _raw_channel_mode in ("both", "dual", "all"):
    CHANNEL_MODE: str = "both"
elif _raw_channel_mode in ("true", "1", "yes"):
    CHANNEL_MODE: str = "test"
else:
    CHANNEL_MODE: str = "production"

USE_TEST_CHANNEL: bool = CHANNEL_MODE == "test"

# ── Application Environment ───────────────────────────────────────────────────
# APP_MODE:
#   production  (default) — automatic unattended run of ACTIVE_AUTOMATIONS (link_sniper)
#   local                 — interactive selection menu on startup
APP_MODE: str = os.getenv("APP_MODE", "production").strip().lower()

# Comma-separated list of active automations for production mode (e.g. link_sniper)
ACTIVE_AUTOMATIONS: list[str] = [
    item.strip()
    for item in os.getenv("ACTIVE_AUTOMATIONS", "link_sniper").split(",")
    if item.strip()
]

# ── Browser ───────────────────────────────────────────────────────────────────
# Whether to run Chrome without a visible window.
# false (default) — browser window is visible; easier to monitor and less likely
#                   to be flagged as a bot by sites like Google.
# true             — no window; use only for fully unattended background runs
#                   where bot detection is not a concern.
BROWSER_HEADLESS: bool = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"

# Port used for DrissionPage remote debugging (dedicated port 9555 avoids conflicts with IDE tools on 9222)
BROWSER_PORT: int = int(os.getenv("BROWSER_PORT", "9555"))

# Persistent browser profile (optional; disabled by default)
BROWSER_USE_PROFILE: bool = (
    os.getenv("BROWSER_USE_PROFILE", "false").strip().lower() == "true"
)
BROWSER_USER_DATA_DIR: Optional[str] = (
    os.path.abspath(os.getenv("BROWSER_USER_DATA_DIR", "browser_profile"))
    if BROWSER_USE_PROFILE
    else None
)

# Maximum time to poll each page for the claim button (in seconds)
BUTTON_POLL_TIMEOUT: float = float(os.getenv("BUTTON_POLL_TIMEOUT", "1.2"))

# Hard deadline (seconds) for processing one message's entire URL batch.
# If the browser hangs for any reason, the batch is abandoned after this time
# and the script returns to listening — never blocked forever.
BROWSER_BATCH_TIMEOUT: float = float(os.getenv("BROWSER_BATCH_TIMEOUT", "120"))
