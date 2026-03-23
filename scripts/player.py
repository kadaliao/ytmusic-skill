#!/usr/bin/env python3
"""
YouTube Music Playback Controller via Chrome CDP.

This controller only supports connecting to an existing Chrome session.
Chrome must already be running with --remote-debugging-port=<port>.

Usage:
  uv run --with playwright python scripts/player.py [--chrome-port N] <action> [args]

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
"""

import argparse
import json
import sys
import time
from typing import NoReturn

YTM_URL = "https://music.youtube.com"

KEYS = {
    "toggle": "k",
    "next": "Shift+N",
    "prev": "Shift+P",
}

SELECTORS = {
    "player_bar": "ytmusic-player-bar",
    "shuffle": ".shuffle",
    "repeat": ".repeat",
}


def bail(msg: str) -> NoReturn:
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def out(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def connect_chrome(playwright, port: int = 9222):
    try:
        return playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
    except Exception:
        bail(
            f"Could not connect to Chrome on port {port}.\n\n"
            f"Start Chrome with remote debugging enabled:\n"
            f"  macOS:   uv run python scripts/launch_chrome.py --chrome-port {port}\n"
            f"  Linux:   google-chrome --remote-debugging-port={port}\n"
            f"  Windows: chrome.exe --remote-debugging-port={port}\n\n"
            f"On macOS, prefer a dedicated --user-data-dir for Chrome remote debugging.\n"
            f"Make sure you are already signed in at https://music.youtube.com in that launched session, then retry."
        )


def navigate_to_ytm(page, path: str = "") -> None:
    page.goto(f"{YTM_URL}{path}", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector("ytmusic-app", timeout=15000)
    except Exception:
        pass


def find_or_open_ytm(browser):
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "music.youtube.com" in page.url:
                return page
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    navigate_to_ytm(page)
    return page


def wait_for_player(page, timeout: int = 15000) -> None:
    try:
        page.wait_for_selector(SELECTORS["player_bar"], timeout=timeout)
    except Exception:
        bail(
            "Player bar not found. Make sure Chrome is signed in to YouTube Music "
            "and a playable page is open."
        )


def send_key(page, key: str) -> None:
    page.focus("body")
    page.keyboard.press(key)
    time.sleep(0.3)


def _is_playing(page) -> bool:
    try:
        return bool(page.evaluate("""
            (() => {
                const v = document.querySelector('video');
                return v ? !v.paused : false;
            })()
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

                const title = titleEl ? titleEl.innerText.trim() : null;
                const artist = artistEl ? artistEl.innerText.trim() : null;
                const cur = video ? Math.floor(video.currentTime) : 0;
                const dur = video ? Math.floor(video.duration) || 0 : 0;
                const fmt = s => {
                    const m = Math.floor(s / 60);
                    return m + ':' + (s % 60 + '').padStart(2, '0');
                };

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
    except Exception as exc:
        return {"error": str(exc)}


def _attempt_start_playback(page) -> str:
    try:
        started = page.evaluate("""
            async () => {
                const video = document.querySelector('video');
                if (!video) return false;
                try {
                    await video.play();
                    return !video.paused;
                } catch {
                    return false;
                }
            }
        """)
        if started:
            return "video.play()"
    except Exception:
        pass

    for method, action in [
        ("play_button", lambda: page.locator("tp-yt-paper-icon-button.play-pause-button").first.click(timeout=3000)),
        ("toggle_key", lambda: send_key(page, KEYS["toggle"])),
    ]:
        try:
            action()
            time.sleep(0.8)
            if _is_playing(page):
                return method
        except Exception:
            continue
    return "failed"


def _ensure_playing(page, timeout_ms: int = 12000) -> tuple[bool, list[str]]:
    deadline = time.time() + (timeout_ms / 1000)
    actions: list[str] = []
    while time.time() < deadline:
        if _is_playing(page):
            return True, actions
        action = _attempt_start_playback(page)
        if action != "failed":
            actions.append(action)
        if _is_playing(page):
            return True, actions
        time.sleep(1.0)
    return _is_playing(page), actions


def cmd_open(args):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
            url = f"{YTM_URL}/watch?v={args.video_id}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            wait_for_player(page, timeout=20000)
            verified, recovery_actions = _ensure_playing(page)
            status = _get_status(page)
            out({
                "action": "open",
                "url": url,
                "mode": "chrome-cdp",
                "playback_verified": verified,
                "recovery_actions": recovery_actions,
                **status,
            })
        finally:
            browser.close()


def cmd_control(action: str, args):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
            wait_for_player(page)

            if action == "toggle":
                send_key(page, KEYS["toggle"])
                time.sleep(0.3)
            elif action == "play":
                if not _is_playing(page):
                    send_key(page, KEYS["toggle"])
                    time.sleep(0.3)
                    _ensure_playing(page, timeout_ms=5000)
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
        finally:
            browser.close()
    out({"action": action, **status})


def cmd_volume(args):
    from playwright.sync_api import sync_playwright

    level = max(0, min(100, args.level))
    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
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
        finally:
            browser.close()
    out({"action": "volume", "level": level, "result": result})


def cmd_seek(args):
    from playwright.sync_api import sync_playwright

    seconds = max(0, args.seconds)
    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
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
        finally:
            browser.close()
    out({"action": "seek", "target_seconds": seconds, "result": result, **status})


def cmd_shuffle(args):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
            wait_for_player(page)
            btn = page.locator(SELECTORS["shuffle"])
            btn.click()
            time.sleep(0.3)
            active = btn.get_attribute("aria-checked") == "true"
            out({"action": "shuffle", "shuffle_on": active})
        except Exception as exc:
            bail(f"Could not find shuffle button: {exc}")
        finally:
            browser.close()


def cmd_repeat(args):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
            wait_for_player(page)
            btn = page.locator(SELECTORS["repeat"])
            btn.click()
            time.sleep(0.3)
            mode = btn.get_attribute("aria-label") or "unknown"
            out({"action": "repeat", "mode": mode})
        except Exception as exc:
            bail(f"Could not find repeat button: {exc}")
        finally:
            browser.close()


def cmd_status(args):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = connect_chrome(pw, args.chrome_port)
        try:
            page = find_or_open_ytm(browser)
            wait_for_player(page)
            status = _get_status(page)
        finally:
            browser.close()
    out({"action": "status", **status})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ytmusic-player",
        description="Control YouTube Music playback via Chrome CDP",
    )
    p.add_argument(
        "--chrome-port",
        type=int,
        default=9222,
        dest="chrome_port",
        help="CDP port for Chrome remote debugging (default: 9222)",
    )
    sub = p.add_subparsers(dest="action", metavar="ACTION")

    po = sub.add_parser("open", help="Open and play a song by videoId")
    po.add_argument("video_id")
    po.set_defaults(func=cmd_open)

    for name, help_text in [
        ("toggle", "Toggle play/pause"),
        ("play", "Resume playback"),
        ("pause", "Pause playback"),
        ("next", "Skip to next track"),
        ("prev", "Go to previous track"),
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
