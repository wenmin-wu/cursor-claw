# rednote-cli — Agent Skill

You have access to `rednote-cli` (the PyPI package by doliz), a full-featured
Xiaohongshu (小红书 / RedNote) CLI that talks directly to the platform API.

## Installation

```bash
pipx install --python python3.12 rednote-cli
# or
pip install rednote-cli
```

First-time setup:

```bash
rednote-cli init runtime       # initialise runtime environment
rednote-cli doctor run --format json   # verify dependencies
rednote-cli account login      # authenticate (interactive browser flow)
rednote-cli account status --format json   # confirm login
```

## Config for this workspace

Read `config.json` in this directory for default values:

```json
{
  "data_dir": "~/.local/share/rednote-cli/notes",
  "default_account": "",
  "default_size": 10,
  "default_sort_by": "latest",
  "default_note_type": "all"
}
```

Save fetched notes to `<data_dir>/<note_id>/note.json` so you can reference them locally later.

## Commands

### Search notes on platform

```bash
rednote-cli search note \
  --keyword "健康食谱" \
  --size 10 \
  --sort-by latest \
  --note-type image_text \
  --format json

# sort-by options: comprehensive | latest | most_liked | most_commented | most_favorited
# note-type:       all | video | image_text
# publish-time:    all | day | week | half_year
# search-scope:    all | viewed | unviewed | following
```

### Fetch a specific note by ID

```bash
rednote-cli note \
  --note-id 69c3eb81000000002102d93c \
  --format json

# If you have xsec_token from a search result, pass it:
rednote-cli note --note-id <id> --xsec-token <token> --xsec-source pc_search --format json
```

`xsec_source` values by context:

| Context | xsec_source |
|---|---|
| Discovery feed | `pc_feed` |
| Search results | `pc_search` |
| User's saved/collect | `pc_collect` |
| User's liked notes | `pc_like` |
| User's own notes | `pc_user` |

### Search users

```bash
rednote-cli search user --keyword "美食博主" --size 10 --format json
```

### Fetch a user profile

```bash
rednote-cli user --user-id <user_id> --format json
rednote-cli user self --format json   # your own profile
```

### Publish a note

```bash
# Image note
rednote-cli publish \
  --target image \
  --account <account_uid> \
  --image-list "img1.jpg,img2.jpg" \
  --title "标题" \
  --content "正文" \
  --tags "标签1,标签2" \
  --format json

# Video note
rednote-cli publish \
  --target video \
  --account <account_uid> \
  --video "video.mp4" \
  --title "标题" \
  --content "正文" \
  --format json

# Scheduled publish (RFC3339 timestamp)
rednote-cli publish --target image --schedule-at "2026-04-01T10:00:00+08:00" ...
```

## JSON input mode (`--input`)

For agent automation, prefer piping JSON via `--input -`:

```bash
echo '{"keyword":"旅行","size":5,"sort_by":"latest"}' | \
  rednote-cli --format json --trace-id req-001 search note --input -

# From a file
rednote-cli --format json --trace-id req-002 note --input payload.json
```

`--input` is supported by: `search note`, `search user`, `note`, `user`, `publish`.

## Saving notes locally

After fetching a note, save it under `data_dir` for future reference:

```bash
NOTE_ID="69c3eb81000000002102d93c"
DATA_DIR="$HOME/.local/share/rednote-cli/notes"
mkdir -p "$DATA_DIR/$NOTE_ID"

rednote-cli note --note-id "$NOTE_ID" --format json > "$DATA_DIR/$NOTE_ID/note.json"
```

To list locally saved notes:

```bash
ls ~/.local/share/rednote-cli/notes/
```

To read a saved note:

```bash
cat ~/.local/share/rednote-cli/notes/<note_id>/note.json
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Parameter error |
| `3` | Auth error (run `account login` again) |
| `4` | Rate-limited / risk control |
| `5` | Internal error |
| `6` | Timeout |
| `7` | Missing dependency / not implemented |

## Recommended agent call pattern

```bash
# Always use --format json and --trace-id for automation
rednote-cli --format json --trace-id req-$(date +%s) search note \
  --keyword "keyword" \
  --size 10 \
  --sort-by latest
```
