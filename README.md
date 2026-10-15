# JobAds: Job Ads Rewriter

A Windows desktop app that collects job ads, rewrites them with Claude Sonnet for a specific community, and distributes them to WhatsApp after manual review. Requirements: `PRD.md`.

## Project layout

| Path | Contents |
|---|---|
| `jobads/` | The application code |
| `jobads/ui/` | The screens (PySide6) |
| `communities/<name>/` | Per community: `system_prompt.txt`, `aids.xlsx`, `examples.txt` |
| `config.json` | Your settings when running from source: active community, model, effort, WhatsApp group per community |
| `packaging/config.default.json` | The settings a new installation starts with (no WhatsApp group: the user sets it in the menu) |
| `api_key.json` | The Anthropic API key. Not in git: copy `api_key.example.json` to `api_key.json` and put your key in it |
| `tests/` | Tests (`test_browser_edge.py` runs only on Windows with Edge) |
| `packaging/` | PyInstaller recipe (`jobads.spec`) and installer script (`installer.iss`) |
| `build.bat` | Builds `dist\setup.exe` |

## First setup after cloning

1. Copy `api_key.example.json` to `api_key.json` and put your Anthropic API key in it.
2. Copy `packaging/config.default.json` to `config.json`.
3. Run `build.bat` once: it creates `.venv` with the libraries (and builds the installer).

## Run from source (Windows)

```
.venv\Scripts\python run.py
```
The first run of `build.bat` creates `.venv`. Running from source uses the files in the project folder (`config.json`, `communities\`, and it creates `data\`, `logs\`, `browser_profile\`).

## Build the installer

1. Put the API key in `api_key.json`.
2. Install Inno Setup 6 (free): https://jrsoftware.org/isinfo.php
3. Run `build.bat`. It installs the libraries, runs the tests, builds `dist\JobAds\` and then `dist\setup.exe`.

## Diagnostics

- Errors are written to `logs\app.log` next to `JobAds.exe`.
- `JobAds.exe --check-browser` opens an invisible Edge and exits. Exit code 0 means the browser works.

## Adding a community

1. Create `communities\<folder>\` with `system_prompt.txt`, `aids.xlsx`, `examples.txt`.
2. Add it to `config.json` (and to `packaging/config.default.json` for new installations) under `communities`, with `display_name`. The WhatsApp group is set in the app's menu.
3. Click "Reload files" in the menu, or restart the app.

## WhatsApp Web selectors

If WhatsApp changes its page and opening the group or filling the message stops working, update the selector lists at the top of `jobads/browser.py` (`WA_CHAT_LIST`, `WA_SEARCH`, `WA_MESSAGE_BOX`).
