---
summary: How to add a rednote-cli agent skill so Cursor can fetch, search, and publish Xiaohongshu notes.
read_when:
  - user asks to read, search, or download a Xiaohongshu / RedNote / 小红书 note
  - user shares an xhslink.com short link and wants to open it
  - user asks to publish an image or video note to RedNote
  - user asks to search their locally saved notes by keyword
---

# rednote-cli Skill

The `rednote-cli` PyPI tool (v0.1.8) lets the agent interact with Xiaohongshu
(小红书 / RedNote). It uses Playwright to intercept XHS browser API responses.
**Images are returned as CDN URLs, not downloaded automatically.**

## Create the skill file

Create `~/.cursor/skills/rednote-cli/SKILL.md` with the content below, then
Cursor will discover it automatically across all workspaces.

````markdown
---
name: rednote-cli
description: >-
  Fetches, searches, and publishes notes on Xiaohongshu (小红书 / RedNote)
  using the rednote-cli PyPI tool. Use when the user asks to search RedNote,
  read a note by ID, look up a user profile, save note content locally, or
  publish image/video notes to the platform.
---

# rednote-cli

Wraps `rednote-cli` (PyPI v0.1.8). Playwright-based — auto-launches headless
Chromium. **Images are CDN URLs in `data.image_list[].url`, not downloaded.**

## Setup (first time only)

```bash
pip install rednote-cli
rednote-cli init runtime
rednote-cli doctor run --format json
rednote-cli account login                # QR scan in headed browser
rednote-cli account status --format json
```

Session cookies saved to `~/.rednote_cli/accounts/Rednote/{user_no}.json`.
Exit code `3` = session expired, re-run `account login`.

Override app home (always absolute path):
```bash
export REDNOTE_OPERATOR_HOME="$HOME/.rednote_cli"
```

Force headed browser: `REDNOTE_CLI_HEADFUL=1 rednote-cli ...`

## Critical: `--format json` is a global flag

Place it **before** the subcommand, and add `--quiet` to suppress log lines:

```bash
rednote-cli --format json --quiet note --note-id <id> --xsec-token <token>
#           ^^^^^^^^^^^^^^^^^^^^^^^^^^^  ← before the subcommand
```

Every response is wrapped: `{"ok": true, "command": "...", "data": {...}}` — always read `.data`.

**Images:** `image_list[].url` is often empty. Use `info_list` scenes instead:
```python
scenes = {s["image_scene"]: s["url"] for s in img.get("info_list", [])}
url = scenes.get("WB_DFT") or scenes.get("WB_PRV")
```

## Commands

### Resolve a short link (xhslink.com)

```bash
# Step 1 — follow redirect, grab Location header
curl -v "http://xhslink.com/o/XXXXXXX" 2>&1 | grep "< Location:"
# Location: https://...xiaohongshu.com/discovery/item/<NOTE_ID>?...&xsec_token=<TOKEN>&...

# Step 2 — fetch (xsec_source=pc_feed for app-share links)
rednote-cli --format json --quiet note \
  --note-id <NOTE_ID> --xsec-token "<TOKEN>" --xsec-source pc_feed
```

### Fetch note by ID

Always pass `xsec_token` — without it the fetch fails with `INTERNAL_ERROR`:

```bash
rednote-cli --format json --quiet note \
  --note-id <id> --xsec-token <token> --xsec-source pc_feed
```

`xsec-source`: `pc_feed` (discovery/app-share) | `pc_search` | `pc_collect` |
`pc_like` | `pc_user`

### Search notes

```bash
rednote-cli --format json --quiet search note \
  --keyword "健康食谱" --size 10 --sort-by latest --note-type image_text
```

`--sort-by`: `comprehensive` | `latest` | `most_liked` | `most_commented` | `most_favorited`
`--note-type`: `all` | `video` | `image_text`

### Download images

`image_list[].url` is often empty — use `info_list` scenes (`WB_DFT` preferred):

```bash
NOTE_ID="<id>"
DIR="$HOME/.local/share/rednote-cli/notes/$NOTE_ID"
mkdir -p "$DIR"
rednote-cli --format json --quiet note --note-id "$NOTE_ID" --xsec-token "<token>" > "$DIR/note.json"

python3 -c "
import json, pathlib, urllib.request
data = json.loads(pathlib.Path('$DIR/note.json').read_text())
for i, img in enumerate(data['data'].get('image_list', [])):
    scenes = {s['image_scene']: s['url'] for s in img.get('info_list', []) if s.get('url')}
    url = scenes.get('WB_DFT') or scenes.get('WB_PRV')
    if url:
        dest = '$DIR/image_{}.jpg'.format(i)
        urllib.request.urlretrieve(url, dest)
        print('Saved', dest)
"
```

### Local search (SQLite FTS5)

Index after saving notes, then search offline:

```bash
python scripts/notes_db.py index
python scripts/notes_db.py search "旅行*" --limit 5
python scripts/notes_db.py status
```

`scripts/notes_db.py` is in the cursor-claw repo root.

### User & publish

```bash
rednote-cli --format json --quiet user --user-id <id>
rednote-cli --format json --quiet search user --keyword "美食博主" --size 10
rednote-cli --format json --quiet publish --target image \
  --image-list "img1.jpg,img2.jpg" --title "标题" --tags "标签1"
```

## JSON input mode

```bash
echo '{"keyword":"旅行","size":5}' | \
  rednote-cli --format json --quiet search note --input -
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `2` | Parameter error |
| `3` | Auth expired — run `account login` |
| `4` | Rate-limited / risk control |
| `5` | Internal error |
| `6` | Timeout |
| `7` | Dependency missing |
````

## Default config

Create `~/.cursor/skills/rednote-cli/config.json`:

```json
{
  "data_dir": "~/.local/share/rednote-cli/notes",
  "default_account": "",
  "default_size": 10,
  "default_sort_by": "latest",
  "default_note_type": "all",
  "rednote_cli_home": "~/.rednote_cli"
}
```

## Local search script

Copy `scripts/notes_db.py` from this repo to your skill directory or any
location on `$PATH`. It indexes `note.json` files into SQLite FTS5 and
supports keyword search with no extra dependencies.
