#!/usr/bin/env python3
"""
YouTube Music Playback Controller

Two modes:
  isolated (default)  Self-managed Chromium, cookies injected from
                      <skill-root>/.ytmusic/auth.json by default.
                      No Chrome installation required. Chromium auto-downloads on first use.

  chrome              Connect to your existing Chrome via CDP.
                      Chrome must be running with --remote-debugging-port=<port>.
                      Uses Chrome's own login session — no auth.json needed.

Usage:
  uv run --with playwright python scripts/player.py [--mode isolated|chrome] [--chrome-port N] <action> [args]

Actions:
  open <videoId>   Open and play a song
  play             Resume playback
  pause            Pause playback
  toggle           Toggle play/pause
  next             Skip to next track
  prev             Go to previous track
  volume <0-100>   Set volume level
  seek <seconds>   Seek to position in seconds
  status           Show current song and playback state
  shuffle          Toggle shuffle mode
  repeat           Cycle repeat mode

Examples:
  # Isolated mode (default)
  uv run --with playwright python scripts/player.py open SJKoWAd5ySo
  uv run --with playwright python scripts/player.py pause

  # Chrome mode (reuse existing Chrome session)
  uv run --with playwright python scripts/player.py --mode chrome status
  uv run --with playwright python scripts/player.py --mode chrome --chrome-port 9222 next
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


def _resolve_data_dir() -> Path:
    configured = os.environ.get("YTMUSIC_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parent.parent / ".ytmusic"


SCRIPT_PATH = Path(__file__).resolve()
DATA_DIR = _resolve_data_dir()
AUTH_FILE = DATA_DIR / "auth.json"
BROWSER_DATA_DIR = DATA_DIR / "browser-profile"
YTM_URL = "https://music.youtube.com"

KEYS = {
    "toggle": "k",
    "next":   "Shift+N",
    "prev":   "Shift+P",
}

SELECTORS = {
    "player_bar": "ytmusic-player-bar",
    "shuffle":    ".shuffle",
    "repeat":     ".repeat",
    "title":      ".title.ytmusic-player-bar",
}


# ─── Output helpers ──────────────────────────────────────────────────────────

def bail(msg: str) -> NoReturn:
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def out(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ─── Setup: Playwright chromium (isolated mode only) ─────────────────────────

def ensure_playwright() -> None:
    """Auto-install Playwright's Chromium browser if not present."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if not Path(exe).exists():
                _install_chromium()
    except ImportError:
        bail(
            "Playwright is not available in this environment.\n"
            f"Run: uv run --with playwright python {SCRIPT_PATH} <action>"
        )
    except Exception:
        _install_chromium()


def _install_chromium() -> None:
    """Download Playwright's Chromium browser."""
    print(json.dumps({"status": "installing", "message": "Downloading Chromium (one-time setup, ~150MB)..."}), flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=False,
    )
    if result.returncode != 0:
        bail(
            "Failed to install Chromium. "
            "Try running manually: uv run --with playwright python -m playwright install chromium"
        )


# ─── Auth: parse cookies from auth.json (isolated mode only) ─────────────────

def load_cookies() -> list[dict]:
    """Parse cookies from auth.json into Playwright cookie dicts.

    Supports two formats:
    - cookies_json: full cookie objects imported via `helper.py auth setup --cookies-file`
    - Cookie string: legacy format, parsed from the raw Cookie header value
    """
    if not AUTH_FILE.exists():
        return []
    try:
        auth = json.loads(AUTH_FILE.read_text())
        # Prefer full cookie objects when available (more accurate attributes)
        if "cookies_json" in auth:
            return auth["cookies_json"]
        cookie_str = auth.get("Cookie", "")
    except Exception:
        return []

    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        secure = name.startswith("__Secure-") or name.startswith("__Host-")
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".youtube.com",
            "path": "/",
            "secure": secure,
            "httpOnly": False,
            "sameSite": "None" if secure else "Lax",
        })
    return cookies


def check_auth(args=None) -> None:
    """Verify auth is available. Skipped in chrome mode (Chrome handles its own session)."""
    if getattr(args, "mode", "isolated") == "chrome":
        return
    if AUTH_FILE.exists() and load_cookies():
        return

    guide = (
        "YouTube Music requires authentication to play full songs.\n\n"
        "Setup steps (one-time):\n"
        "  1. Open Chrome and go to https://music.youtube.com\n"
        "  2. Make sure you are logged in to your Google account\n"
        "  3. Press F12 (or Cmd+Option+I on Mac) to open DevTools\n"
        "  4. Click the 'Network' tab\n"
        "  5. In the filter box, type: /browse\n"
        "  6. Reload the page (Cmd+R / F5)\n"
        "  7. Click any request that appears in the list\n"
        "  8. Right-click → 'Copy' → 'Copy as fetch (Node.js)'\n"
        "  9. Find the 'Cookie:' line and copy everything after 'Cookie: '\n"
        " 10. Run:\n\n"
        f"       uv run --with ytmusicapi python {SCRIPT_PATH.parent / 'helper.py'} auth setup --cookie '<paste here>'\n\n"
        "Then retry your command.\n\n"
        "Tip: use --mode chrome to control your existing Chrome session without auth.json."
    )
    bail(guide)


# ─── Browser: isolated mode ───────────────────────────────────────────────────

def launch_persistent(playwright, headless: bool = False):
    """
    Launch a persistent Chromium context backed by BROWSER_DATA_DIR.
    The cookies database is cleared before each launch so that fresh cookies
    from auth.json are always used — no stale session state.
    Returns (context, page).
    """
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Delete the stored cookies file so our injected cookies are the only ones.
    # Avoids stale/expired cookies in the profile overriding auth.json.
    cookies_db = BROWSER_DATA_DIR / "Default" / "Network" / "Cookies"
    if cookies_db.exists():
        cookies_db.unlink()

    context = playwright.chromium.launch_persistent_context(
        str(BROWSER_DATA_DIR),
        headless=headless,
        args=["--autoplay-policy=no-user-gesture-required"],
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    cookies = load_cookies()
    if cookies:
        context.add_cookies(cookies)
        _inject_cookie_header(context, cookies)
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def _inject_cookie_header(context, cookies: list[dict]) -> None:
    """
    Intercept all YouTube Music requests and force the Cookie header to match
    auth.json. This ensures the server sees a complete, up-to-date session
    even when the browser's internal cookie storage has stale data.
    """
    raw = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def _handle(route):
        headers = {**route.request.headers, "cookie": raw}
        route.continue_(headers=headers)

    context.route("https://music.youtube.com/**", _handle)
    context.route("https://www.youtube.com/youtubei/**", _handle)


# ─── Browser: chrome CDP mode ─────────────────────────────────────────────────

def connect_chrome(playwright, port: int = 9222):
    """Connect to an existing Chrome instance via CDP. Returns browser."""
    try:
        return playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
    except Exception:
        bail(
            f"Could not connect to Chrome on port {port}.\n\n"
            f"Start Chrome with remote debugging enabled:\n"
            f"  macOS:   open -a 'Google Chrome' --args --remote-debugging-port={port}\n"
            f"  Linux:   google-chrome --remote-debugging-port={port}\n"
            f"  Windows: chrome.exe --remote-debugging-port={port}\n\n"
            f"Then retry your command."
        )


def find_or_open_ytm(browser):
    """Find the existing YouTube Music tab, or open a new one."""
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "music.youtube.com" in page.url:
                return page
    # No YTM tab found — open one
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    navigate_to_ytm(page)
    return page


# ─── Unified page getter ──────────────────────────────────────────────────────

def get_page(pw, args):
    """
    Returns (close_fn, page) for the selected mode.

    isolated: launches own Chromium, navigates to YTM root.
    chrome:   connects to existing Chrome via CDP, finds/opens YTM tab without
              navigating away from whatever is currently playing.
    """
    if getattr(args, "mode", "isolated") == "chrome":
        browser = connect_chrome(pw, getattr(args, "chrome_port", 9222))
        page = find_or_open_ytm(browser)
        return browser.close, page
    else:
        ctx, page = launch_persistent(pw, headless=False)
        navigate_to_ytm(page)
        return ctx.close, page


# ─── Navigation / wait helpers ────────────────────────────────────────────────

def navigate_to_ytm(page, path: str = "") -> None:
    """Navigate to YouTube Music and wait for the app shell."""
    page.goto(f"{YTM_URL}{path}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector("ytmusic-app", timeout=15000)
    except Exception:
        pass


def wait_for_player(page, timeout: int = 15000) -> None:
    """Wait for the player bar to appear."""
    try:
        page.wait_for_selector(SELECTORS["player_bar"], timeout=timeout)
    except Exception:
        bail(
            "Player bar not found — the page may not be logged in or no song is playing.\n"
            "Tip: try --mode chrome to control your existing Chrome session instead."
        )


# ─── Playback helpers ─────────────────────────────────────────────────────────

def send_key(page, key: str) -> None:
    page.focus("body")
    page.keyboard.press(key)
    time.sleep(0.3)


def _is_playing(page) -> bool:
    try:
        return bool(page.evaluate("""
            (() => { const v = document.querySelector('video'); return v ? !v.paused : false; })()
        """))
    except Exception:
        return False


def _get_status(page) -> dict:
    try:
        return page.evaluate("""
            (() => {
                const video = document.querySelector('video');
                const titleEl = document.querySelector('.title.ytmusic-player-bar');
                const artistEl = document.querySelector('.byline-wrapper.ytmusic-player-bar a');

                const title  = titleEl  ? titleEl.innerText.trim()  : null;
                const artist = artistEl ? artistEl.innerText.trim() : null;

                const cur  = video ? Math.floor(video.currentTime) : 0;
                const dur  = video ? Math.floor(video.duration) || 0 : 0;
                const fmt  = s => { const m = Math.floor(s/60); return m+':'+(s%60+'').padStart(2,'0'); };

                return {
                    title,
                    artist,
                    playing: video ? !video.paused : false,
                    position: fmt(cur),
                    duration: fmt(dur),
                    position_seconds: cur,
                    duration_seconds: dur,
                    volume: video ? Math.round(video.volume * 100) : null,
                };
            })()
        """)
    except Exception as e:
        return {"error": str(e)}


# ─── Actions ──────────────────────────────────────────────────────────────────

def cmd_open(args):
    check_auth(args)
    mode = getattr(args, "mode", "isolated")
    if mode == "isolated":
        ensure_playwright()

    from playwright.sync_api import sync_playwright
    video_id = args.video_id
    url = f"{YTM_URL}/watch?v={video_id}"

    with sync_playwright() as pw:
        if mode == "chrome":
            browser = connect_chrome(pw, getattr(args, "chrome_port", 9222))
            page = find_or_open_ytm(browser)
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(SELECTORS["player_bar"], timeout=15000)
                time.sleep(2)
            except Exception:
                pass
            status = _get_status(page)
            out({"action": "open", "url": url, "mode": "chrome", **status})
            browser.close()
        else:
            ctx, page = launch_persistent(pw, headless=args.headless)
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(SELECTORS["player_bar"], timeout=15000)
                time.sleep(2)
            except Exception:
                pass
            status = _get_status(page)
            out({"action": "open", "url": url, "mode": "isolated", **status})
            # Keep browser alive until music ends (or Ctrl+C)
            try:
                duration = status.get("duration_seconds", 0) or 300
                time.sleep(max(duration, 10))
            except KeyboardInterrupt:
                pass
            ctx.close()


def cmd_control(action: str, args):
    """Generic handler for toggle/play/pause/next/prev/status."""
    if getattr(args, "mode", "isolated") == "isolated":
        ensure_playwright()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        close, page = get_page(pw, args)
        wait_for_player(page)

        if action == "toggle":
            send_key(page, KEYS["toggle"])
            time.sleep(0.3)
        elif action == "play":
            if not _is_playing(page):
                send_key(page, KEYS["toggle"])
                time.sleep(0.3)
        elif action == "pause":
            if _is_playing(page):
                send_key(page, KEYS["toggle"])
                time.sleep(0.3)
        elif action == "next":
            send_key(page, KEYS["next"])
            time.sleep(1.5)
        elif action == "prev":
            send_key(page, KEYS["prev"])
            time.sleep(1.5)

        status = _get_status(page)
        close()
    out({"action": action, **status})


def cmd_volume(args):
    if getattr(args, "mode", "isolated") == "isolated":
        ensure_playwright()
    level = max(0, min(100, args.level))

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        close, page = get_page(pw, args)
        wait_for_player(page)
        result = page.evaluate(f"""
            (() => {{
                const v = document.querySelector('video');
                if (!v) return 'video_not_found';
                v.volume = {level / 100};
                v.muted = false;
                return Math.round(v.volume * 100);
            }})()
        """)
        close()
    out({"action": "volume", "level": level, "result": result})


def cmd_seek(args):
    if getattr(args, "mode", "isolated") == "isolated":
        ensure_playwright()
    seconds = max(0, args.seconds)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        close, page = get_page(pw, args)
        wait_for_player(page)
        result = page.evaluate(f"""
            (() => {{
                const v = document.querySelector('video');
                if (!v) return 'video_not_found';
                v.currentTime = {seconds};
                return Math.floor(v.currentTime);
            }})()
        """)
        time.sleep(0.3)
        status = _get_status(page)
        close()
    out({"action": "seek", "target_seconds": seconds, "result": result, **status})


def cmd_shuffle(args):
    if getattr(args, "mode", "isolated") == "isolated":
        ensure_playwright()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        close, page = get_page(pw, args)
        wait_for_player(page)
        try:
            btn = page.locator(SELECTORS["shuffle"])
            btn.click()
            time.sleep(0.3)
            active = btn.get_attribute("aria-checked") == "true"
            close()
            out({"action": "shuffle", "shuffle_on": active})
        except Exception as e:
            close()
            bail(f"Could not find shuffle button: {e}")


def cmd_repeat(args):
    if getattr(args, "mode", "isolated") == "isolated":
        ensure_playwright()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        close, page = get_page(pw, args)
        wait_for_player(page)
        try:
            btn = page.locator(SELECTORS["repeat"])
            btn.click()
            time.sleep(0.3)
            mode = btn.get_attribute("aria-label") or "unknown"
            close()
            out({"action": "repeat", "mode": mode})
        except Exception as e:
            close()
            bail(f"Could not find repeat button: {e}")


def cmd_status(args):
    if getattr(args, "mode", "isolated") == "isolated":
        ensure_playwright()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        close, page = get_page(pw, args)
        wait_for_player(page)
        status = _get_status(page)
        close()
    out({"action": "status", **status})


# ─── Parser ───────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ytmusic-player",
        description="Control YouTube Music playback via Playwright",
    )
    p.add_argument(
        "--mode", choices=["isolated", "chrome"], default="isolated",
        help=(
            "isolated (default): self-managed Chromium, cookies from auth.json; "
            "chrome: connect to your existing Chrome via CDP"
        ),
    )
    p.add_argument(
        "--chrome-port", type=int, default=9222, dest="chrome_port",
        help="CDP port when using --mode chrome (default: 9222)",
    )
    p.add_argument("--headless", action="store_true", help="Run in headless mode (isolated only)")
    sub = p.add_subparsers(dest="action", metavar="ACTION")

    po = sub.add_parser("open", help="Open and play a song by videoId")
    po.add_argument("video_id")
    po.set_defaults(func=cmd_open)

    for name, help_text in [
        ("toggle", "Toggle play/pause"),
        ("play",   "Resume playback"),
        ("pause",  "Pause playback"),
        ("next",   "Skip to next track"),
        ("prev",   "Go to previous track"),
        ("status", "Show current playback status"),
    ]:
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(func=lambda a, n=name: cmd_control(n, a))

    psh = sub.add_parser("shuffle", help="Toggle shuffle mode")
    psh.set_defaults(func=cmd_shuffle)

    prp = sub.add_parser("repeat", help="Cycle repeat mode")
    prp.set_defaults(func=cmd_repeat)

    pv = sub.add_parser("volume", help="Set volume (0-100)")
    pv.add_argument("level", type=int)
    pv.set_defaults(func=cmd_volume)

    ps = sub.add_parser("seek", help="Seek to position in seconds")
    ps.add_argument("seconds", type=float)
    ps.set_defaults(func=cmd_seek)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
