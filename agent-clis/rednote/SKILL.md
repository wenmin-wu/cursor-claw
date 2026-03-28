# rednote-cli — Agent Skill

You have access to `rednote-cli`, a tool for fetching and searching Xiaohongshu (小红书 / RedNote) notes locally.

## How notes are stored

Each fetched note is saved to a folder named by its 24-character hex ID:

```
<data_dir>/
  69c3eb81000000002102d93c/
    content.txt   ← title, author, tags, body text (UTF-8)
    image_00.jpg  ← downloaded images
    image_01.jpg
    note.json     ← full metadata (JSON)
```

Default `data_dir`: `~/.local/share/rednote-cli/notes/`
Config file: `~/.config/rednote-cli/config.json`
SQLite index: `~/.local/share/rednote-cli/notes.db`

## Commands

### Fetch a note

```bash
rednote-cli fetch "<url_or_share_text>"
```

- Accepts full URLs (`https://www.xiaohongshu.com/explore/<id>`) or share text containing xhslink / xiaohongshu URLs
- Opens the page via Chrome (must be running with `--remote-debugging-port=19327`)
- Saves text + images to `<data_dir>/<note_id>/`
- Indexes the note in local SQLite for future searches
- Prints `note_dir` on success — read `content.txt` and image files from there

```bash
# with JSON output for programmatic use
rednote-cli fetch "<url>" --json
```

### Search locally

```bash
rednote-cli search --local "<keyword>"   # full-text search
rednote-cli search ""                    # list all notes (newest first)
rednote-cli search "健康食谱" --json     # JSON output
rednote-cli search "穿搭" --limit 10
```

### Show a note by ID

```bash
rednote-cli show 69c3eb81000000002102d93c
rednote-cli show 69c3eb81000000002102d93c --json
```

### List all indexed notes

```bash
rednote-cli list
rednote-cli list --limit 100 --json
```

### Configure

```bash
rednote-cli config --show                          # view current config
rednote-cli config --data-dir ~/my-notes           # change note storage dir
rednote-cli config --cdp-port 9222                 # change Chrome debug port
rednote-cli config --max-images 10                 # limit images per fetch
rednote-cli config --storage-state ~/.xhs-auth.json  # Playwright auth cookies
```

## Workflow

1. **User shares a RedNote link** → run `rednote-cli fetch "<url>"`
2. **Read the saved content** → `cat <note_dir>/content.txt`
3. **View images** → list files in `<note_dir>/` matching `image_*.jpg`
4. **Search saved notes** → `rednote-cli search --local "<keyword>"`
5. **Get full metadata** → `rednote-cli show <note_id> --json`

## Reading content in your response

After fetching, read the note content like this:

```bash
# Get the note_dir from fetch output, then:
cat <note_dir>/content.txt
ls <note_dir>/image_*.jpg 2>/dev/null
```

Images are plain JPEG/PNG files saved to disk — open or display them as needed.

## Prerequisite: Chrome with remote debugging

```bash
# macOS
open -a "Google Chrome" --args --remote-debugging-port=19327

# Linux
google-chrome --remote-debugging-port=19327 &
```

You must be logged into Xiaohongshu in that Chrome instance. To persist login across restarts, save the storage state once and configure it:

```bash
rednote-cli config --storage-state ~/.xhs-auth.json
```
