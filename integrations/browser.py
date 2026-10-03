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
    # Anti-throttling flags: prevent Chrome from deprioritizing background tabs in multi-tab race mode
    co.set_argument("--disable-background-timer-throttling")
    co.set_argument("--disable-backgrounding-occluded-windows")
    co.set_argument("--disable-renderer-backgrounding")
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


def race_tabs_and_evaluate(
    urls: list[str],
    js_code: str,
    timeout: float = 2.5,
    poll_interval: float = 0.03,
    settle_buffer: float = 0.25,
) -> tuple[str, Optional[str]]:
    """
    Open up to len(urls) tabs in the same browser window concurrently and race them.
    As soon as any tab triggers 'CLICKED':
      - Brings the winning tab to the front.
      - Closes other auxiliary tabs.
      - Returns ('CLICKED', winning_url).
    If all tabs are confirmed expired or without footers:
      - Closes auxiliary tabs.
      - Returns ('EXPIRED', None).
    On timeout:
      - Closes auxiliary tabs.
      - Returns ('TIMEOUT', None).
    """
    if not urls:
        return "EXPIRED", None

    page = get_page()

    # 1. Primary tab loads the first URL
    primary_url = urls[0]
    try:
        page.get(primary_url, timeout=3.0)
    except Exception:
        pass

    # 2. Auxiliary tabs load the remaining URLs in the batch
    tab_map: list[tuple[str, Any]] = [(primary_url, page)]
    for u in urls[1:]:
        try:
            tab = page.new_tab(u, new_window=False)
            tab_map.append((u, tab))
        except Exception as exc:
            logger.warning("Could not open concurrent tab for %s: %s", u, exc)

    start = time.time()
    no_footer_map: dict[str, float] = {}
    active_tabs = list(tab_map)

    while time.time() - start < timeout and active_tabs:
        for item in list(active_tabs):
            url, tab = item
            try:
                res = tab.run_js(js_code)
                if res == "CLICKED":
                    # Winning tab! Bring to front and close losing auxiliary tabs
                    try:
                        page.activate_tab(tab.tab_id)
                    except Exception:
                        pass
                    for other_url, other_tab in tab_map:
                        if other_tab.tab_id != tab.tab_id and other_tab.tab_id != page.tab_id:
                            try:
                                other_tab.close()
                            except Exception:
                                pass
                    return "CLICKED", url

                if res in ("EXPIRED_PAGE", "NO_FOOTER"):
                    now = time.time()
                    if url not in no_footer_map:
                        no_footer_map[url] = now
                    elif now - no_footer_map[url] >= settle_buffer or res == "EXPIRED_PAGE":
                        active_tabs.remove(item)
                        if tab.tab_id != page.tab_id:
                            try:
                                tab.close()
                            except Exception:
                                pass
                else:
                    no_footer_map.pop(url, None)
            except Exception:
                pass

        time.sleep(poll_interval)

    # Clean auxiliary tabs if no tab claimed
    for url, tab in tab_map:
        if tab.tab_id != page.tab_id:
            try:
                tab.close()
            except Exception:
                pass

    return ("TIMEOUT", None) if (time.time() - start >= timeout) else ("EXPIRED", None)


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
