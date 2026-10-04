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
    TARGET_CHANNELS,
    URL_PATTERN,
    CLAIM_AND_DETECT_JS,
    BUTTON_POLL_TIMEOUT,
)

logger = get_logger(__name__)

# Concurrency lock: process one message batch at a time
_sniper_lock: asyncio.Lock = asyncio.Lock()


def _process_urls_sync(urls: list[str]) -> bool:
    """
    Synchronous worker: processes URLs using bounded concurrent tabs
    (or sequential if CONCURRENT_TABS=1), navigating non-blocking and
    claiming the first valid link with an active button.
    """
    total = len(urls)
    concurrency = settings.CONCURRENT_TABS
    logger.info(
        "[link_sniper] Starting batch of %d URL(s) (concurrency: %d tab(s))...",
        total,
        concurrency,
    )

    # Chunk URLs into slices of size `concurrency`
    chunks = [urls[i : i + concurrency] for i in range(0, total, concurrency)]

    for chunk_idx, chunk in enumerate(chunks, start=1):
        if len(chunk) == 1:
            url = chunk[0]
            logger.info("[link_sniper] Opening: %s", url)
            browser.safe_navigate(url, timeout=3.0)
            status = browser.poll_and_evaluate_js(
                CLAIM_AND_DETECT_JS,
                timeout=BUTTON_POLL_TIMEOUT,
                poll_interval=0.03,
            )
            if status == "CLICKED":
                logger.info("[link_sniper] Claimed: footer button clicked on %s", url)
                return True
            if status in ("EXPIRED_PAGE", "NO_FOOTER"):
                logger.info("[link_sniper] Link expired / no claim button.")
            else:
                logger.info("[link_sniper] Timeout waiting for claim button.")
        else:
            logger.info(
                "[link_sniper] [Batch %d/%d] Racing %d links concurrently across tabs...",
                chunk_idx,
                len(chunks),
                len(chunk),
            )
            for idx, u in enumerate(chunk, start=1):
                logger.info("[link_sniper]   -> Tab %d: %s", idx, u)

            status, winning_url = browser.race_tabs_and_evaluate(
                chunk,
                CLAIM_AND_DETECT_JS,
                timeout=BUTTON_POLL_TIMEOUT,
                poll_interval=0.03,
            )

            if status == "CLICKED" and winning_url:
                logger.info(
                    "[link_sniper] Claimed: Won race and clicked claim button on %s",
                    winning_url,
                )
                return True

            logger.info(
                "[link_sniper] [Batch %d/%d] Finished (%s) — moving to next batch.",
                chunk_idx,
                len(chunks),
                status,
            )

    logger.warning("[link_sniper] Exhausted all %d URL(s) without finding an active claim button.", total)
    return False


async def on_startup(client: TelegramClient) -> None:
    """Called once after the client connects — logs all monitored channels."""
    mode_label = (
        "DUAL MODE (PRODUCTION + TEST)"
        if settings.CHANNEL_MODE == "both"
        else ("TEST MODE" if settings.CHANNEL_MODE == "test" else "PRODUCTION")
    )
    logger.info("link_sniper: Active channel mode: [%s]", mode_label)

    for ch in TARGET_CHANNELS:
        try:
            entity = await client.get_entity(ch)
            title = (
                getattr(entity, "title", None)
                or getattr(entity, "username", None)
                or str(ch)
            )
            ch_type = "TEST CHANNEL" if str(ch) == str(settings.TEST_CHANNEL_ID) else "PRODUCTION"
            logger.info("link_sniper: Monitoring channel '%s' (%s) [%s]", title, ch, ch_type)
        except Exception as exc:
            logger.error("link_sniper: Could not resolve channel %s: %s", ch, exc)


def register(client: TelegramClient) -> None:
    """Register Telegram event handlers for the link sniper automation."""

    @client.on(events.NewMessage(chats=TARGET_CHANNELS))
    async def _handle_new_message(event: events.NewMessage.Event) -> None:
        msg = event.message
        raw_text = msg.message or ""

        # Identify which channel this event came from
        is_test = str(event.chat_id) == str(settings.TEST_CHANNEL_ID)
        origin_tag = "[Test Channel]" if is_test else "[Production]"

        # ── Safe media type detection (prevents crashes on any Telegram message type) ──
        media_tag = ""
        if msg.photo:
            media_tag = "[Photo]"
        elif msg.video:
            media_tag = "[Video]"
        elif msg.document:
            doc_name = getattr(msg.file, "name", None)
            media_tag = f"[Document: {doc_name}]" if doc_name else "[Document]"
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
            logger.info("Channel event %s: %s Caption: %s", origin_tag, media_tag, snippet)
        elif media_tag:
            logger.info("Channel event %s: %s (no caption)", origin_tag, media_tag)
        elif snippet:
            logger.info("Channel event %s: %s", origin_tag, snippet)
        else:
            logger.info("Channel event %s: (Empty/Action)", origin_tag)

        # ── 1. Extract matching URLs (from text body, media caption, or embedded hyperlinks) ──
        raw_matches: list[str] = URL_PATTERN.findall(raw_text)

        if msg.entities:
            for ent in msg.entities:
                url_candidate = getattr(ent, "url", None)
                if url_candidate:
                    raw_matches.extend(URL_PATTERN.findall(url_candidate))

        # ── 1b. Extract matching URLs from attached text documents (e.g. .txt files) in memory ──
        if msg.document:
            file_name = (getattr(msg.file, "name", None) or "").lower()
            file_ext = (getattr(msg.file, "ext", None) or "").lower()
            mime_type = (getattr(msg.file, "mime_type", None) or "").lower()
            file_size = getattr(msg.file, "size", 0) or 0

            is_text_file = (
                file_ext in (".txt", ".text", ".csv", ".log")
                or file_name.endswith((".txt", ".text", ".csv", ".log"))
                or mime_type.startswith("text/")
                or mime_type in ("application/json", "application/x-empty")
            )
            # Enforce 5MB limit to prevent memory issues with massive unintended files
            if is_text_file and file_size <= 5 * 1024 * 1024:
                try:
                    content_bytes = await msg.download_media(bytes)
                    if content_bytes:
                        file_text = content_bytes.decode("utf-8-sig", errors="ignore")
                        doc_matches = URL_PATTERN.findall(file_text)
                        if doc_matches:
                            logger.info(
                                "[link_sniper] %s Extracted %d URL(s) from attached document '%s'",
                                origin_tag,
                                len(doc_matches),
                                file_name or "document.txt",
                            )
                            raw_matches.extend(doc_matches)
                except Exception as exc:
                    logger.warning("[link_sniper] Failed to read attached document: %s", exc)

        # Deduplicate while preserving order, and strip trailing sentence punctuation
        urls: list[str] = []
        for match in raw_matches:
            cleaned = match.rstrip(").,;'\"")
            if cleaned and cleaned not in urls:
                urls.append(cleaned)

        if not urls:
            return

        # ── 2. Shuffle — randomize order ──
        random.shuffle(urls)
        logger.info(
            "[link_sniper] %s Received %d matching URL(s) — shuffled order.",
            origin_tag,
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
