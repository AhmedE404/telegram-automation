"""
Telegram client singleton.

The module exposes a single `client` instance built from config/settings.py.
Import it wherever a Telethon client is needed — guarantees one session file
is shared across the entire process.

Usage:
    from core.client import client
"""

import os
from telethon import TelegramClient

from config import settings

# Ensure the parent directory for the session file exists on all operating systems
session_dir = os.path.dirname(settings.SESSION_NAME)
if session_dir and not os.path.exists(session_dir):
    os.makedirs(session_dir, exist_ok=True)

client = TelegramClient(
    settings.SESSION_NAME,
    settings.TELEGRAM_API_ID,
    settings.TELEGRAM_API_HASH,
)
