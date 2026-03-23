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
    └── auth.json
```

By default:
- `scripts/helper.py` stores API auth headers in `./.ytmusic/auth.json`
- `scripts/player.py` does not use local browser state files; it connects to an existing Chrome session via CDP

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

Start Chrome with remote debugging enabled and make sure you are already signed in to YouTube Music:

```bash
open -a 'Google Chrome' --args --remote-debugging-port=9222
```

Examples:

```bash
uv run --with playwright python scripts/player.py open <videoId>
uv run --with playwright python scripts/player.py status
uv run --with playwright python scripts/player.py --chrome-port 9222 next
```

## Notes

- `uv` is required
- `ytmusicapi` is pulled on demand via `uv run --with ytmusicapi ...`
- `playwright` is pulled on demand via `uv run --with playwright ...`
- Playback depends on a real Chrome session with remote debugging enabled

## ClawHub Notes

- Bump `version` in `SKILL.md` for every published release
- Publish from the skill root directory
- ClawHub-published skills are distributed under ClawHub's platform terms
