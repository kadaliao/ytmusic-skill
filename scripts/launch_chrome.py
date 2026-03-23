#!/usr/bin/env python3
"""
Launch Chrome for YouTube Music playback with a dedicated CDP profile.

This is primarily intended to make macOS remote-debugging startup more reliable
than `open -a 'Google Chrome' --args ...`.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

YTM_URL = "https://music.youtube.com"


def _resolve_data_dir() -> Path:
    configured = os.environ.get("YTMUSIC_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parent.parent / ".ytmusic"


def _default_profile_dir() -> Path:
    return _resolve_data_dir() / "chrome-profile"


def _candidate_paths() -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", "")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
        return [
            str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe"),
            str(Path(program_files) / "Google/Chrome/Application/chrome.exe"),
            str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"),
        ]
    return [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]


def _find_chrome() -> str:
    for candidate in _candidate_paths():
        if Path(candidate).exists():
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("Could not find Google Chrome/Chromium on this system")


def _build_command(chrome_path: str, args: argparse.Namespace) -> list[str]:
    return [
        chrome_path,
        f"--remote-debugging-port={args.chrome_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={args.user_data_dir}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        args.url,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ytmusic-launch-chrome",
        description="Launch Chrome with a dedicated profile for YouTube Music CDP control",
    )
    parser.add_argument(
        "--chrome-port",
        type=int,
        default=9222,
        help="CDP port to expose (default: 9222)",
    )
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=_default_profile_dir(),
        help="Chrome profile directory used for the launched session",
    )
    parser.add_argument(
        "--url",
        default=YTM_URL,
        help=f"URL to open after launch (default: {YTM_URL})",
    )
    args = parser.parse_args()

    args.user_data_dir = args.user_data_dir.expanduser().resolve()
    args.user_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        chrome_path = _find_chrome()
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    subprocess.Popen(
        _build_command(chrome_path, args),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    notes = [
        "A dedicated Chrome profile was launched for remote debugging.",
        "If this is the first launch for that profile, sign in to music.youtube.com in the new window.",
        "Keep that Chrome window running while using scripts/player.py commands, including status.",
    ]
    if platform.system() == "Darwin":
        notes.insert(
            0,
            "On macOS this avoids the less reliable `open -a 'Google Chrome' --args ...` path.",
        )

    print(
        json.dumps(
            {
                "status": "launched",
                "platform": platform.system().lower(),
                "chrome_path": chrome_path,
                "chrome_port": args.chrome_port,
                "user_data_dir": str(args.user_data_dir),
                "url": args.url,
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
