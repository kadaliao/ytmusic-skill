# ytmusic-skill

A lightweight `SKILL.md` skill for controlling YouTube Music via natural language.

## Install

Any agent that supports `SKILL.md`-style skills can install this folder directly.

Paste the following into your agent
> `Install the ytmusic skill from https://github.com/kadaliao/ytmusic-skill`

## Runtime Layout

```text
ytmusic-skill/
├── SKILL.md
├── scripts/
│   ├── helper.py
│   ├── launch_chrome.py
│   └── player.py
├── references/
│   └── commands.md
└── .ytmusic/
    └── auth.json
```

By default:
- `scripts/helper.py` stores API auth headers in `./.ytmusic/auth.json`
- `scripts/player.py` does not use local browser state files; it connects to an existing Chrome session via CDP
- `scripts/launch_chrome.py` starts a dedicated Chrome profile for CDP playback control

If needed, you can override the runtime data directory with `YTMUSIC_DATA_DIR`.

## Local Usage

From the skill root:

```bash
uv run --with ytmusicapi python scripts/helper.py auth check
uv run --with playwright python scripts/player.py status
```

## Auth Setup

Cookie string:

```bash
uv run --with ytmusicapi python scripts/helper.py auth setup --cookie '<cookie string>'
```

Cookie JSON export:

```bash
uv run --with ytmusicapi python scripts/helper.py auth setup --cookies-file /path/to/cookies.json
```

Verify:

```bash
uv run --with ytmusicapi python scripts/helper.py auth check
```

## Playback Modes

`scripts/player.py` only supports Chrome CDP playback.
`open`, `play`, `pause`, `next`, `prev`, `seek`, `volume`, and `status` all require the same active Chrome debugging session.

Start Chrome with the helper launcher:

```bash
uv run python scripts/launch_chrome.py
```

On macOS, prefer this helper over `open -a 'Google Chrome' --args ...`.
It uses a dedicated `--user-data-dir`, which is more reliable for remote debugging. Because that is a separate Chrome profile, you may need to sign in again inside the launched window.
If you want to reuse your normal Chrome profile instead, fully quit Chrome first and launch with `--use-system-profile`.

Examples:

```bash
uv run python scripts/launch_chrome.py --chrome-port 9223
uv run python scripts/launch_chrome.py --user-data-dir ~/.ytmusic-chrome-profile
uv run python scripts/launch_chrome.py --use-system-profile --profile-directory Default
uv run python scripts/launch_chrome.py --use-system-profile --profile-directory 'Profile 1'
uv run --with playwright python scripts/player.py open <videoId>
uv run --with playwright python scripts/player.py status
uv run --with playwright python scripts/player.py --chrome-port 9222 next
```

## Notes

- `uv` is required
- `ytmusicapi` is pulled on demand via `uv run --with ytmusicapi ...`
- `playwright` is pulled on demand via `uv run --with playwright ...`
- Playback depends on a real Chrome session with remote debugging enabled
- If `open <videoId>` loads a track but does not start audio, autoplay was likely blocked and the user may need to click play once in the launched Chrome window
- `status` also depends on the active CDP Chrome session; it does not work without the debugging port
- Reusing your existing Chrome profile requires Chrome to be fully quit before relaunch; otherwise the debugging flags may be ignored

## ClawHub Notes

- Bump `version` in `SKILL.md` for every published release
- Publish from the skill root directory
- ClawHub-published skills are distributed under ClawHub's platform terms
