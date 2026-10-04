"""
Configuration specific to the link_sniper automation.
"""

import os
import re
from typing import Union

from config import settings


def _parse_target_channel(raw_val: str) -> Union[int, str]:
    """
    Parse the target channel identifier from environment.
    Supports:
      - Integer channel IDs (e.g. -1001234567890 for private channels)
      - Username strings (e.g. @channel_username for public channels)
    """
    val = raw_val.strip()
    if not val:
        return 0
    try:
        return int(val)
    except ValueError:
        return val


def _resolve_target_channels() -> list[Union[int, str]]:
    """
    Resolve the list of monitored channels based on settings.CHANNEL_MODE.
    Supports:
      - 'production' : Monitored channel is only the production channel (@samsshopofficial).
      - 'test'       : Monitored channel is only the TEST_CHANNEL_ID.
      - 'both'       : Listens to BOTH production channel and TEST_CHANNEL_ID simultaneously.
    """
    prod_raw = os.getenv(
        "LINK_SNIPER_TARGET_CHANNEL",
        os.getenv("TARGET_CHANNEL", "@samsshopofficial"),
    ).strip()
    prod_ch = _parse_target_channel(prod_raw) if prod_raw else "@samsshopofficial"
    test_ch = _parse_target_channel(settings.TEST_CHANNEL_ID) if settings.TEST_CHANNEL_ID else None

    if settings.CHANNEL_MODE == "test":
        return [test_ch] if test_ch else [prod_ch]

    if settings.CHANNEL_MODE == "both":
        channels: list[Union[int, str]] = [prod_ch]
        if test_ch and test_ch not in channels:
            channels.append(test_ch)
        return channels

    return [prod_ch]


TARGET_CHANNELS: list[Union[int, str]] = _resolve_target_channels()
TARGET_CHANNEL: Union[int, str] = TARGET_CHANNELS[0]
TARGET_CHANNEL_ID: Union[int, str] = TARGET_CHANNEL

# Flexible pattern: matches Google subscription links and redirector gateways across all variants:
# 1. Direct and mirror links containing subscription/new/<token>
# 2. Redirector gateway links (e.g. .top domains with /gimini/new/activation?token=...)
# 3. Any activation gateway matching activation?token=
URL_PATTERN: re.Pattern = re.compile(
    r"https?://[^\s<>\"']*(?:subscription/new/|\.top/[^\s<>\"']*|activation\?token=)[^\s<>\"']+"
)

# JS expression that resolves to the target claim button, or undefined/null if absent.
# Optional chaining (?.) prevents errors when footer doesn't exist.
FOOTER_BUTTON_JS: str = "document.querySelector('footer')?.querySelector('button')"

# Unified JS snippet: language-agnostic evaluation of claim button, page structure, and redirectors
CLAIM_AND_DETECT_JS: str = """
return (() => {
    // 1. If claim button exists and is active, click immediately
    const btn = document.querySelector('footer')?.querySelector('button');
    if (btn && !btn.disabled) {
        btn.scrollIntoView({block: 'center'});
        btn.focus();
        btn.click();
        return 'CLICKED';
    }

    // 2. If intermediate redirector page (e.g. .top / activation redirectors)
    const mainEl = document.querySelector('main');
    if (mainEl && mainEl.getAttribute('data-state') === 'error') {
        return 'EXPIRED_PAGE';
    }
    if (!window.location.hostname.includes('google.com')) {
        // Still on redirector gateway, wait for redirect to Google One
        return 'PENDING';
    }

    // 3. If footer exists in DOM on Google page, wait for button to become enabled
    if (document.querySelector('footer')) {
        return 'PENDING';
    }

    // 4. On Google domain and reached complete state without a footer
    if (document.readyState === 'complete') {
        return 'NO_FOOTER';
    }

    return 'PENDING';
})()
"""

# Maximum seconds to poll each URL for the button before moving to the next
BUTTON_POLL_TIMEOUT: float = settings.BUTTON_POLL_TIMEOUT

