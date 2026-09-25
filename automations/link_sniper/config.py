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


def _resolve_target_channel() -> Union[int, str]:
    """
    Resolve the monitored channel based on test mode setting.
    If USE_TEST_CHANNEL is true, listens to the permanent TEST_CHANNEL_ID.
    Otherwise, listens to LINK_SNIPER_TARGET_CHANNEL (or TARGET_CHANNEL).
    """
    if settings.USE_TEST_CHANNEL and settings.TEST_CHANNEL_ID:
        return _parse_target_channel(settings.TEST_CHANNEL_ID)

    prod = os.getenv(
        "LINK_SNIPER_TARGET_CHANNEL",
        os.getenv("TARGET_CHANNEL", "@samsshopofficial"),
    ).strip()
    if prod:
        return _parse_target_channel(prod)

    return "@samsshopofficial"


TARGET_CHANNEL: Union[int, str] = _resolve_target_channel()
TARGET_CHANNEL_ID = TARGET_CHANNEL

# Matches Google subscription activation links regardless of subdomain or path prefix.
# Covers known variants:
#   https://serviceactivation.google.com/subscription/new/<token>
#   https://one.google.com/u/3/activate-plan/subscription/new/<token>?...
URL_PATTERN: re.Pattern = re.compile(
    r"https://[a-zA-Z0-9.-]+\.google\.com/[^\s<>\"']*subscription/new/[^\s<>\"']+"
)

# JS expression that resolves to the target claim button, or undefined/null if absent.
# Optional chaining (?.) prevents errors when footer doesn't exist.
FOOTER_BUTTON_JS: str = "document.querySelector('footer')?.querySelector('button')"

# Unified JS snippet: language-agnostic evaluation of claim button and page structure
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

    // 2. If footer exists in DOM, wait for button to become enabled
    if (document.querySelector('footer')) {
        return 'PENDING';
    }

    // 3. Page reached complete state without a footer
    if (document.readyState === 'complete') {
        return 'NO_FOOTER';
    }

    return 'PENDING';
})()
"""

# Maximum seconds to poll each URL for the button before moving to the next
BUTTON_POLL_TIMEOUT: float = settings.BUTTON_POLL_TIMEOUT

