"""
Generic DrissionPage browser integration driver.

Features:
- Persistent singleton browser instance on a dedicated port (default: 9555).
- Persistent user profile directory (preserves Google accounts, logins, cookies).
- Fast non-blocking loading mode (avoids hanging on network assets and third-party trackers).
- Crash and closed-window resilience (auto-recovers in < 1s).
- Atomic and robust JavaScript interaction primitives.
"""

import platform
import subprocess
import time
from typing import Any, Optional

from DrissionPage import ChromiumPage, ChromiumOptions

from config import settings
from core.logger import get_logger

logger = get_logger(__name__)

# ── Singleton state ───────────────────────────────────────────────────────────
_page: Optional[ChromiumPage] = None


def _make_options() -> ChromiumOptions:
    """Build ChromiumOptions with dedicated port, optional profile, and non-blocking load mode."""
    co = ChromiumOptions()
    co.set_local_port(settings.BROWSER_PORT)
    if settings.BROWSER_USE_PROFILE and settings.BROWSER_USER_DATA_DIR:
        co.set_user_data_path(settings.BROWSER_USER_DATA_DIR)
    co.set_load_mode("none")  # Return immediately on navigation so evaluation runs concurrently
    if settings.BROWSER_HEADLESS:
        co.headless()
    return co


def kill_zombie_browser() -> None:
    """
    Cross-platform termination of any stuck process holding our dedicated browser port.
    Supports Windows, macOS, and Linux cleanly without hardcoded shell assumptions.
    """
    port = settings.BROWSER_PORT
    system = platform.system()

    try:
        if system == "Windows":
            cmd = f"netstat -ano | findstr :{port}"
            output = subprocess.check_output(
                cmd, shell=True, text=True, stderr=subprocess.DEVNULL
            )
            for line in output.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = parts[-1]
                    if pid.isdigit() and pid != "0":
                        subprocess.run(
                            f"taskkill /F /PID {pid}",
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
        else:
            # macOS and Linux: try lsof, fallback to fuser
            res = subprocess.run(
                f"lsof -ti tcp:{port} -sTCP:LISTEN | xargs kill -9",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode != 0:
                subprocess.run(
                    f"fuser -k {port}/tcp",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    except Exception:
        pass


def get_page(force_new: bool = False) -> ChromiumPage:
    """
    Return the active ChromiumPage singleton, creating or reconnecting as needed.
    If the window was closed or connection lost, clears the port and relaunches in < 1s.
    """
    global _page

    if not force_new and _page is not None:
        try:
            if bool(_page.tab_ids):
                return _page
        except Exception:
            pass
        logger.warning("Browser connection lost — reconnecting...")
        _page = None

    kill_zombie_browser()
    time.sleep(0.1)
    logger.info(
        "Starting browser on port %d (headless=%s)...",
        settings.BROWSER_PORT,
        settings.BROWSER_HEADLESS,
    )
    _page = ChromiumPage(addr_or_opts=_make_options())
    return _page


def safe_navigate(url: str, timeout: float = 3.0) -> ChromiumPage:
    """
    Navigate to a URL with resilient auto-retry.
    If the browser window was closed or disconnected during navigation,
    reconnects/reopens immediately and navigates.
    """
    global _page
    while True:
        try:
            page = get_page()
            page.get(url, timeout=timeout)
            return page
        except Exception as exc:
            logger.warning("Navigation failed (%s) — recovering browser...", type(exc).__name__)
            _page = None
            time.sleep(0.1)


def run_js(js_code: str) -> Any:
    """Execute a JavaScript snippet in the active page and return its result."""
    page = get_page()
    return page.run_js(js_code)


def poll_and_evaluate_js(
    js_code: str,
    timeout: float = 2.5,
    poll_interval: float = 0.03,
    settle_buffer: float = 0.25,
) -> str:
    """
    Poll up to `timeout` seconds executing `js_code`.
    Expected statuses:
      - 'CLICKED': Claim button clicked -> returns immediately.
      - 'EXPIRED_PAGE': Known terminal error state -> returns immediately.
      - 'NO_FOOTER': Page completed loading without a footer. If sustained for
                     `settle_buffer` seconds (allowing SPA hydration), returns 'NO_FOOTER'.
      - 'TIMEOUT': Fallback if timeout expires.
    """
    start = time.time()
    no_footer_since: Optional[float] = None

    while time.time() - start < timeout:
        try:
            page = get_page()
            res = page.run_js(js_code)
            if res in ("CLICKED", "EXPIRED_PAGE"):
                return str(res)
            if res == "NO_FOOTER":
                if no_footer_since is None:
                    no_footer_since = time.time()
                elif time.time() - no_footer_since >= settle_buffer:
                    return "NO_FOOTER"
            else:
                no_footer_since = None
        except Exception:
            no_footer_since = None

        time.sleep(poll_interval)

    return "TIMEOUT"


def find_and_click_js(
    js_selector: str,
    timeout: float = 1.2,
    poll_interval: float = 0.04,
) -> bool:
    """
    Poll up to `timeout` seconds for a JS expression to resolve to an element.
    When found: scrolls into view, focuses, clicks, and returns True.
    If not found within `timeout`: returns False.
    """
    page = get_page()
    start = time.time()

    click_script = f"""
    const el = {js_selector};
    if (el && !el.disabled) {{
        el.scrollIntoView({{block: 'center'}});
        el.focus();
        el.click();
        return true;
    }}
    return false;
    """

    while time.time() - start < timeout:
        try:
            clicked = bool(page.run_js(click_script))
            if clicked:
                return True
        except Exception:
            pass
        time.sleep(poll_interval)

    return False


def close_browser() -> None:
    """Cleanly close the persistent browser instance."""
    global _page
    if _page is not None:
        try:
            _page.quit()
        except Exception:
            pass
        _page = None
    kill_zombie_browser()
