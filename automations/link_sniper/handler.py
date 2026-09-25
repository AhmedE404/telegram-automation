"""
link_sniper automation handler.

Behaviour
─────────
1. On startup  → resolves target channel (test vs prod) and logs its title.
2. On message  → logs incoming message safely (supports any media type),
                 extracts matching subscription links, shuffles them,
                 and snipes each link until the claim button is clicked.
"""

import asyncio
import random

from telethon import TelegramClient, events

from config import settings
from core.logger import get_logger
from integrations import browser
from automations.link_sniper.config import (
    TARGET_CHANNEL_ID,
    URL_PATTERN,
    CLAIM_AND_DETECT_JS,
    BUTTON_POLL_TIMEOUT,
)

logger = get_logger(__name__)

# Concurrency lock: process one message batch at a time
_sniper_lock: asyncio.Lock = asyncio.Lock()


def _process_urls_sync(urls: list[str]) -> bool:
    """
    Synchronous worker: iterates through shuffled URLs, navigates
    non-blocking, and claims the first valid link with an active button.
    Exits immediately if expired or claimed.
    """
    total = len(urls)
    logger.info("[link_sniper] Starting batch of %d URL(s)...", total)

    for index, url in enumerate(urls, start=1):
        logger.info("[link_sniper] [%d/%d] Opening: %s", index, total, url)

        # 1. Non-blocking navigation
        browser.safe_navigate(url, timeout=3.0)

        # 2. Fast concurrent detection and click with early expired exit
        status = browser.poll_and_evaluate_js(
            CLAIM_AND_DETECT_JS,
            timeout=BUTTON_POLL_TIMEOUT,
            poll_interval=0.03,
        )

        if status == "CLICKED":
            logger.info(
                "[link_sniper] [%d/%d] Claimed: footer button clicked on %s",
                index,
                total,
                url,
            )
            return True

        if status in ("EXPIRED_PAGE", "NO_FOOTER"):
            logger.info("[link_sniper] [%d/%d] Link expired / no claim button — skipping to next.", index, total)
        else:
            logger.info("[link_sniper] [%d/%d] Timeout waiting for claim button — checking next URL.", index, total)

    logger.warning("[link_sniper] Exhausted all %d URL(s) without finding an active claim button.", total)
    return False


async def on_startup(client: TelegramClient) -> None:
    """Called once after the client connects — logs the monitored channel."""
    try:
        entity = await client.get_entity(TARGET_CHANNEL_ID)
        title = (
            getattr(entity, "title", None)
            or getattr(entity, "username", None)
            or str(TARGET_CHANNEL_ID)
        )
        mode = "TEST MODE" if settings.USE_TEST_CHANNEL else "PRODUCTION"
        logger.info("link_sniper: Monitoring channel '%s' (%s) [%s]", title, TARGET_CHANNEL_ID, mode)
    except Exception as exc:
        logger.error("link_sniper: Could not resolve channel %s: %s", TARGET_CHANNEL_ID, exc)


def register(client: TelegramClient) -> None:
    """Register Telegram event handlers for the link sniper automation."""

    @client.on(events.NewMessage(chats=TARGET_CHANNEL_ID))
    async def _handle_new_message(event: events.NewMessage.Event) -> None:
        msg = event.message
        raw_text = msg.message or ""

        # ── Safe media type detection (prevents crashes on any Telegram message type) ──
        media_tag = ""
        if msg.photo:
            media_tag = "[Photo]"
        elif msg.video:
            media_tag = "[Video]"
        elif msg.document:
            media_tag = "[Document]"
        elif msg.voice:
            media_tag = "[Voice]"
        elif msg.audio:
            media_tag = "[Audio]"
        elif msg.sticker:
            media_tag = "[Sticker]"
        elif msg.poll:
            media_tag = "[Poll]"

        # Format message snippet for console visibility
        snippet = raw_text.replace("\n", " ").strip()
        if len(snippet) > 80:
            snippet = snippet[:80] + "..."

        if media_tag and snippet:
            logger.info("Channel event: %s Caption: %s", media_tag, snippet)
        elif media_tag:
            logger.info("Channel event: %s (no caption)", media_tag)
        elif snippet:
            logger.info("Channel event: %s", snippet)
        else:
            logger.info("Channel event: (Empty/Action)")

        # ── 1. Extract matching URLs (from text body, media caption, or embedded hyperlinks) ──
        urls: list[str] = URL_PATTERN.findall(raw_text)

        if msg.entities:
            for ent in msg.entities:
                url_candidate = getattr(ent, "url", None)
                if url_candidate:
                    for matched_url in URL_PATTERN.findall(url_candidate):
                        if matched_url not in urls:
                            urls.append(matched_url)

        if not urls:
            return

        # ── 2. Shuffle — randomize order ──
        random.shuffle(urls)
        logger.info(
            "[link_sniper] Received %d matching URL(s) — shuffled order.",
            len(urls),
        )

        # ── 3. Process with batch timeout protection ──
        async with _sniper_lock:
            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, _process_urls_sync, urls),
                    timeout=settings.BROWSER_BATCH_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[link_sniper] Batch timed out after %.0fs — returning to listener.",
                    settings.BROWSER_BATCH_TIMEOUT,
                )

    logger.info("link_sniper: handlers registered.")
