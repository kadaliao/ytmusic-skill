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
│   └── player.py
├── references/
│   └── commands.md
└── .ytmusic/
    ├── auth.json
    ├── browser_cookies.json
    └── browser-profile/
```

By default:
- `scripts/helper.py` stores API auth headers in `./.ytmusic/auth.json`
- `scripts/helper.py` stores browser cookies in `./.ytmusic/browser_cookies.json`
- `scripts/player.py` uses `./.ytmusic/browser_cookies.json` and `./.ytmusic/browser-profile/`

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

`scripts/player.py` supports:
- `isolated`: self-managed Chromium, uses local skill state
- `chrome`: attaches to an existing Chrome session via CDP

Examples:

```bash
uv run --with playwright python scripts/player.py open <videoId>
uv run --with playwright python scripts/player.py --mode chrome status
uv run --with playwright python scripts/player.py --mode chrome --chrome-port 9222 next
uv run --with playwright python scripts/player.py --hold-open-seconds 0 open <videoId>
```

## Notes

- `uv` is required
- `ytmusicapi` is pulled on demand via `uv run --with ytmusicapi ...`
- `playwright` is pulled on demand via `uv run --with playwright ...`
- Chromium is downloaded on first isolated playback run

## ClawHub Notes

- Bump `version` in `SKILL.md` for every published release
- Publish from the skill root directory
- ClawHub-published skills are distributed under ClawHub's platform terms
