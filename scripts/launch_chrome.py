#!/usr/bin/env python3
"""
Launch Chrome for YouTube Music playback with CDP enabled.

Uses a dedicated profile by default because modern Chrome versions no longer
allow remote debugging against the default Chrome data directory.
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


def _default_system_user_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise FileNotFoundError("LOCALAPPDATA is not set; cannot locate the Chrome profile")
        return Path(local_app_data) / "Google/Chrome/User Data"

    chrome_dir = Path.home() / ".config/google-chrome"
    if chrome_dir.exists():
        return chrome_dir
    chromium_dir = Path.home() / ".config/chromium"
    if chromium_dir.exists():
        return chromium_dir
    return chrome_dir


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


def _chrome_major_version(chrome_path: str) -> int | None:
    result = subprocess.run(
        [chrome_path, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for part in result.stdout.strip().split():
        if part[:1].isdigit():
            try:
                return int(part.split(".", 1)[0])
            except ValueError:
                return None
    return None


def _build_command(chrome_path: str, args: argparse.Namespace) -> list[str]:
    command = [
        chrome_path,
        f"--remote-debugging-port={args.chrome_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={args.user_data_dir}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if args.profile_directory:
        command.append(f"--profile-directory={args.profile_directory}")
    command.append(args.url)
    return command


def _chrome_running() -> bool:
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["pgrep", "-x", "Google Chrome"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    if system == "Linux":
        for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]:
            result = subprocess.run(
                ["pgrep", "-x", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode == 0:
                return True
        return False
    if system == "Windows":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
            check=False,
        )
        return "chrome.exe" in result.stdout.lower()
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ytmusic-launch-chrome",
        description="Launch Chrome with CDP enabled for YouTube Music control",
    )
    parser.add_argument(
        "--chrome-port",
        type=int,
        default=9222,
        help="CDP port to expose (default: 9222)",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Attempt to reuse the platform default Chrome user-data-dir; blocked by Chrome 136+",
    )
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        help="Chrome user-data-dir root to launch with; defaults to a dedicated launcher profile",
    )
    parser.add_argument(
        "--profile-directory",
        help="Optional Chrome profile directory inside the user-data-dir, for example Default or 'Profile 1'",
    )
    parser.add_argument(
        "--url",
        default=YTM_URL,
        help=f"URL to open after launch (default: {YTM_URL})",
    )
    args = parser.parse_args()

    profile_mode = "dedicated"
    if args.use_system_profile:
        try:
            args.user_data_dir = _default_system_user_data_dir()
        except FileNotFoundError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        profile_mode = "system"
    elif args.user_data_dir:
        args.user_data_dir = args.user_data_dir.expanduser().resolve()
        profile_mode = "custom"
    else:
        args.user_data_dir = _default_profile_dir()

    args.user_data_dir = args.user_data_dir.expanduser().resolve()
    args.user_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        chrome_path = _find_chrome()
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    chrome_major_version = _chrome_major_version(chrome_path)

    if profile_mode == "system" and chrome_major_version is not None and chrome_major_version >= 136:
        print(
            json.dumps(
                {
                    "error": (
                        "Chrome 136+ does not allow --remote-debugging-port against the default Chrome "
                        "user data directory."
                    ),
                    "chrome_version": chrome_major_version,
                    "next_action": (
                        "Use the dedicated launcher profile instead, or switch the skill to a separate "
                        "Chrome for Testing workflow."
                    ),
                    "details": [
                        "This is an official Chrome security change, not a launcher bug.",
                        "Reusing your normal signed-in Chrome profile is unsupported for this CDP-based skill on modern Chrome.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)

    if profile_mode == "system" and _chrome_running():
        print(
            json.dumps(
                {
                    "error": "Chrome appears to already be running.",
                    "next_action": (
                        "Fully quit Chrome, then rerun this command. Even then, modern Chrome versions "
                        "still block remote debugging on the default profile."
                    ),
                    "user_data_dir": str(args.user_data_dir),
                    "profile_directory": args.profile_directory,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
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
                "profile_mode": "dedicated" if profile_mode == "system" else profile_mode,
                "platform": platform.system().lower(),
                "chrome_path": chrome_path,
                "chrome_version": chrome_major_version,
                "chrome_port": args.chrome_port,
                "user_data_dir": str(args.user_data_dir),
                "profile_directory": args.profile_directory,
                "url": args.url,
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
