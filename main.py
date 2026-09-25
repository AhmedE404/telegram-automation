"""
Entry point for the Telegram Automation Suite.

Provides an interactive menu for local development and direct unattended
execution for production environments.

Usage:
  python3 main.py          # Runs configured automations automatically (default: link_sniper)
  python3 main.py --menu   # Open interactive selection menu
  python3 main.py --login  # Run Google account login helper directly
  python3 main.py --sniper # Run Link Sniper directly
"""

import argparse
import sqlite3
import sys
from typing import Optional

from config import settings
from core.client import client
from core.logger import get_logger
from automations.link_sniper import handler as link_sniper

logger = get_logger(__name__)

# ── Automation Registry ───────────────────────────────────────────────────────
# Maps automation names (from settings.ACTIVE_AUTOMATIONS) to their handler modules.
# Each handler must expose:
#   register(client)   – registers Telethon event handlers
#   on_startup(client) – optional coroutine called after connect
AUTOMATION_REGISTRY = {
    "link_sniper": link_sniper,
}


def get_active_automations() -> list:
    """Resolve configured automations from settings.ACTIVE_AUTOMATIONS."""
    active = []
    for name in settings.ACTIVE_AUTOMATIONS:
        if name in AUTOMATION_REGISTRY:
            active.append(AUTOMATION_REGISTRY[name])
        else:
            logger.warning("Configured automation '%s' not found in registry.", name)
    return active or [link_sniper]


async def run_automations(automations: list) -> None:
    """Connect to Telegram, register handlers, and listen for events."""
    me = await client.get_me()
    logger.info("Logged in as: %s (id=%s)", me.first_name, me.id)

    # 1. Run startup hooks
    for automation in automations:
        if hasattr(automation, "on_startup"):
            await automation.on_startup(client)

    # 2. Register event handlers
    for automation in automations:
        automation.register(client)

    logger.info("All automations active — listening for events…")
    await client.run_until_disconnected()


def start_automations(automations: Optional[list] = None) -> None:
    """Launch the Telegram client with selected or active automations."""
    target_automations = automations or get_active_automations()
    try:
        with client:
            client.loop.run_until_complete(run_automations(target_automations))
    except KeyboardInterrupt:
        logger.info("Shutdown requested — goodbye.")
    except sqlite3.OperationalError as exc:
        if "database is locked" in str(exc).lower():
            logger.error(
                "Session database is locked. "
                "Another instance of this script is probably still running. "
                "Wait a few seconds for it to fully exit, then try again."
            )
        else:
            logger.critical("Database error: %s", exc, exc_info=True)
            sys.exit(1)
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


def start_login() -> None:
    """Launch the Google account login helper."""
    from tools.login_google import run_login
    run_login()


def interactive_menu() -> None:
    """Display the interactive launcher menu for local use."""
    print("\n" + "=" * 50)
    print(" Telegram Automation Suite")
    print("=" * 50)
    print(" [1] Link Sniper (Listen to Telegram channels)")
    print(" [2] Google Account Login (Setup browser session)")
    print(" [3] Exit")
    print("=" * 50)

    try:
        choice = input("Enter choice (1-3, default: 1): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        return

    if choice in ("", "1"):
        print("\nStarting Link Sniper...")
        start_automations([link_sniper])
    elif choice == "2":
        start_login()
    elif choice == "3":
        sys.exit(0)
    else:
        print("\nInvalid option.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram Automation Suite Launcher")
    parser.add_argument("--sniper", "-s", action="store_true", help="Run Link Sniper automation directly")
    parser.add_argument("--login", "-l", action="store_true", help="Run Google login helper directly")
    parser.add_argument("--menu", "-m", action="store_true", help="Open interactive selection menu")

    args = parser.parse_args()

    if args.menu:
        interactive_menu()
    elif args.login:
        start_login()
    elif args.sniper:
        start_automations([link_sniper])
    elif settings.APP_MODE == "local":
        interactive_menu()
    else:
        # Default (production): automatically run configured automations (link_sniper)
        logger.info(
            "Automatic mode active (APP_MODE=production). Running automations: %s",
            settings.ACTIVE_AUTOMATIONS,
        )
        start_automations()


if __name__ == "__main__":
    main()
