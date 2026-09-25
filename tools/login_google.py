"""
Google Account Login Helper.

Interactive tool to log into your Google Account using the project's
persistent browser profile and settings.
"""

from config import settings
from integrations import browser


def run_login() -> None:
    """Launch browser, navigate to Google login, and wait for user to sign in."""
    print("=" * 60)
    print(" Google Account Login Setup")
    print("=" * 60)
    profile_info = settings.BROWSER_USER_DATA_DIR if settings.BROWSER_USE_PROFILE else "Disabled (set BROWSER_USE_PROFILE=true in .env to enable)"
    print(f"Profile: {profile_info}")
    print(f"Port:    {settings.BROWSER_PORT}")
    print("=" * 60)

    login_url = "https://accounts.google.com/"
    print("\nStarting browser... please wait.")

    try:
        page = browser.get_page(force_new=True)
        page.get(login_url)
    except Exception as exc:
        print(f"\n[ERROR] Failed to start browser: {exc}")
        return

    print("\n" + "#" * 60)
    print(" Browser is now open!")
    print(" 1. Sign in with your Google email and password.")
    print(" 2. Complete any 2-step verification (2FA) if prompted.")
    print(" 3. Make sure you are fully signed in to your account.")
    print(" 4. Come back to this terminal and press [ENTER] when done.")
    print("#" * 60 + "\n")

    try:
        input("Press [ENTER] here once you have finished signing in: ")
    except (KeyboardInterrupt, EOFError):
        print("\nExiting...")

    print("\nSaving session...")
    try:
        current_url = page.url
        print(f"Final page: {current_url}")
    except Exception:
        pass

    print("Session and cookies saved successfully in your persistent profile.")
    print("You can now run main.py and your Google account will remain logged in.")


if __name__ == "__main__":
    run_login()
