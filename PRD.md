# Product Requirements Document — Job Ads Rewriter

**Version:** 1.0 — 15.10.2026
**Based on:** `project_prompt.txt`, `system_prompt.txt`

---

## 1. Overview

A Windows desktop application that helps an organization collect job ads from Facebook groups, WhatsApp groups and job websites, rewrite them with AI (Claude Sonnet) so they are clear and suitable for a specific community, review them manually, and distribute them to a WhatsApp group.

The first community is autistic job seekers. Other communities (e.g. transgender job seekers) are added later by adding a community folder — no code change.

### 1.1 Goals
- Cut the time staff spend finding and rewriting job ads.
- Produce consistent, clear ads in the organization's format and style.
- Keep a human in control: every ad is reviewed before it is distributed.
- Support more than one community with the same application.
- Keep the data needed to train a local rewriting model in the future.

### 1.2 Out of scope (version 1)
- Automatic sending of WhatsApp messages (the user always presses Send).
- Automatic scrolling or crawling of Facebook, WhatsApp or websites.
- The sheet `פרופילים (בבנייה)`.
- Editing the Excel, system prompt or examples from inside the app (they are edited in Excel / a text editor).
- Mac and Linux.
- Multiple users or a shared database.
- Training a local model (only the data for it is collected — §13).

---

## 2. Users and Environment

- **User:** one staff member of the organization, not technical.
- **PC:** Windows 10/11, with Microsoft Edge (installed by default) and an internet connection.
- **Accounts:** the user's own Facebook and WhatsApp accounts, logged in through the app's browser window.

---

## 3. Ad Process

```
Collect (capture ad text)  →  Rephrase (Sonnet)  →  Review (edit, approve/reject)  →  Distribute (WhatsApp, user presses Send)
```

### 3.1 Status flow
```
new ──► approved ──► distributed
 │         │
 └──► rejected
```
- A new ad starts as `new`.
- `approved` and `rejected` can be changed back to `new` (to fix a mistake).
- `distributed` is set only after the user confirms the message was sent (§10.3). It is final.

---

## 4. Folder Layout

Everything is installed in one folder, for the current user (default: `%LOCALAPPDATA%\JobAds`).

```
JobAds\
├── JobAds.exe
├── _internal\                  ← bundled Python and libraries (do not touch)
├── config.json
├── api_key.json
├── communities\
│   └── autism\
│       ├── system_prompt.txt
│       ├── aids.xlsx
│       └── examples.txt
├── data\
│   ├── ads.db                  ← SQLite database
│   └── prompt_versions\        ← copies of the prompt files used (§13)
├── browser_profile\            ← Edge profile: Facebook/WhatsApp logins
└── logs\
    └── app.log
```

---

## 5. Configuration Files

### 5.1 `config.json`
```json
{
  "active_community": "autism",
  "model": "claude-sonnet-5-5",
  "effort": "low",
  "communities": {
    "autism": {
      "display_name": "אוטיזם",
      "whatsapp_group": "thomas vinters"
    }
  }
}
```
- `active_community` — the folder name of the last community chosen. Updated by the app when the user switches.
- `model`, `effort` — the Sonnet call settings (§9.2).
- `communities` — per community: the name shown in the menu, and the exact name of the WhatsApp distribution group.
- A folder in `communities\` that has no entry here is still shown, using the folder name as its display name, and with no distribution group (distribution shows an error until it is set).

### 5.2 `api_key.json`
```json
{ "api_key": "sk-ant-..." }
```
- Plain text, by design: the installation ships with the developer's key, with a spending limit set in the Anthropic console, so a new user can try the system. A user who keeps the app buys their own key and replaces it in this file.

---

## 6. Communities

- A community = a folder under `communities\` with three files: `system_prompt.txt`, `aids.xlsx`, `examples.txt`.
- The menu screen lists all community folders (§8.1). Choosing one loads its three files and saves it as `active_community`.
- The presenting screen shows only the active community's ads.
- Each ad records the community it was handled for.
- If a community folder is missing one of the three files, it is listed but cannot be chosen; the menu shows which file is missing.

---

## 7. Excel Loading (`aids.xlsx`)

The active community's Excel is read once, when the community is loaded (at startup or when switching), and kept in memory. If the user edits the Excel while the app is open, a **"Reload files"** button in the menu reloads all three files.

| Sheet | Used as | Columns |
|---|---|---|
| `פורמט` | Ad format, sent to Sonnet | One column; each non-empty cell is a block of the format, in order |
| `ניסוחים נפוצים` | Common phrasings, sent to Sonnet | `תיאור דרישה [דוגמאות]`, `ניסוח`, `הערות` |
| `תיוגים` | Tags, sent to Sonnet; tag list for validation and filters | category (column A — filled only on the first row of each category; carried down to the rows below), `האשטג`, `סוג התוכן`, `הערות` |
| `מילות מפתח לחיפוש` | Keywords, sent to Sonnet; keyword list for validation and filters | `מילת חיפוש`, `פירוט` |
| `ערוצי איתור משרות` | Sources list in the collecting screen | `שם ערוץ`, `טווח`, `לינק`, `הערות`, `תדירות` |

Rules:
- Empty rows are skipped.
- In `ערוצי איתור משרות`, each `לינק` cell displays the word "לינק" and holds the real URL as an Excel hyperlink. The app reads the hyperlink's URL, not the displayed word. A cell that contains a plain URL as text is also accepted.
- The source type is decided from the URL: `facebook.com` → Facebook, `chat.whatsapp.com` or `whatsapp.com` → WhatsApp, anything else → website.
- A missing sheet, or a missing required column, stops the community from loading, with a message naming the sheet/column.

---

## 8. Screens

General:
- Right-to-left layout; all labels in Hebrew.
- A top navigation bar on every screen except the menu: **תפריט** (menu), **איסוף** (collecting), **מודעות** (presenting). The user can move between collecting and presenting directly.
- The active community's name is always shown in the top bar.
- Long operations (Sonnet call, opening the browser) never freeze the window; a progress indicator is shown.

### 8.1 Menu
- Active community name.
- Community chooser (shown only when there is more than one community folder).
- Buttons: **איסוף מודעות** (collecting), **הצגת מודעות** (presenting), **התחברות לפייסבוק ולווטסאפ** (log in to Facebook and WhatsApp, §10.4), **טעינה מחדש של קבצים** (reload files).

### 8.2 Collecting
**Sources table** (from `ערוצי איתור משרות`): name, type (Facebook / WhatsApp / website), range, notes, frequency.

**Actions:**
1. **Open** (per source): opens the source in the app's Edge window (§10.1).
2. **Capture**: the user selects the ad text in the browser and clicks **Capture** in the app. The app reads the selected text from the active browser tab.
3. **Paste manually**: a fallback for when capture fails or the ad came from elsewhere. The user pastes text; the source is set to "ידני" (manual).

**After capture / paste**, the text is cleaned (§10.2), and a preview panel shows:
- The cleaned text (editable, so the user can remove junk such as "Like · Reply").
- The ad's images (§10.2), as thumbnails, each with a **הסרה** (remove) button. **הדבקת תמונה** (paste image) adds an image from the clipboard; Ctrl+V of an image in the text box does the same. Up to 4 images per ad. An ad can be only images, with no text.
- The source name and URL (the URL of the tab at capture time).
- Buttons: **שכתוב** (rephrase) and **ביטול** (cancel).

**Rephrase:**
- **Duplicate check:** the app checks whether the same ad already exists in the database for this community, and if so warns "ad already exists" and offers to open the existing ad or continue anyway. How it works:
  - The text is reduced to a fingerprint: spaces, line breaks, punctuation and emojis are removed and English letters are lowercased, then a SHA-256 hash of the result is computed.
  - The hash is stored with every ad (`origin_hash`, §12) in an indexed column, so the check is a single lookup and takes under a millisecond even with hundreds of thousands of ads.
  - Only identical ads are caught (the same text, even with different spacing or emojis). An ad that was reposted with changed wording is not caught; the user will recognize it during review.
- The app calls Sonnet (§9). On success, the ad is saved as `new` and the detailed screen opens. If Sonnet says it is not a job ad, a message is shown and nothing is saved.

### 8.3 Presenting
A table of all ads of the active community. **The ad text is not shown.**

| Column | Notes |
|---|---|
| Collect date | |
| Source name | |
| Status | |
| Score | 0–100 |
| Tags | |
| Keywords | |

- **Filters:** status (multi-select), tags (multi-select, from the tag list), keywords (multi-select, from the keyword list), score range, source, collect date range.
- **Sort:** click any column header. Default: newest first.
- Double-click (or **פתח**) on a row opens the detailed screen.
- A counter shows how many ads match the filters.

### 8.4 Detailed Ad
**Shown:**
- The ad text (`user_ad`) — editable.
- The original ad (`origin_ad`) — read-only, in a collapsible panel.
- Status, score, score explanation, tags, keywords, source name + URL (clickable), collect date, distribute date.

**Actions:**
| Action | Available when | Result |
|---|---|---|
| **שמירה** (save text) | status `new` or `approved` | saves `user_ad` |
| **אישור** (approve) | status `new` | status → `approved`; blocked if the text is empty |
| **דחייה** (reject) | status `new` | status → `rejected` |
| **החזרה לחדשה** (back to new) | status `approved` or `rejected` | status → `new` |
| **הפצה** (distribute) | status `approved` | §10.3 |
| **העתקה** (copy) | always | copies `user_ad` to the clipboard |

- Leaving the screen with unsaved text asks: save / discard / stay.
- When the status is `distributed`, the text is read-only.

---

## 9. Sonnet Call

### 9.1 Request
- **System prompt:** the community's `system_prompt.txt`, then the reference material, each in a clearly labeled section:
  - `פורמט` — the format blocks in order
  - `ניסוחים נפוצים` — one line per row: `description | phrasing | notes`
  - `תיוגים` — one line per row: `category | tag | description | notes`
  - `מילות מפתח לחיפוש` — one line per row: `keyword | details`
  - examples — the full `examples.txt`
- **User message:** the source ad text. When the ad has images, the images come first, then a short line saying they are part of the ad, then the text. `system_prompt.txt` does not change.
- **Images:** scaled to at most 1568 pixels on the long side and sent as JPEG. Images smaller than 200 pixels are not ad content (profile pictures, icons) and are skipped. Each image adds about 1,000–1,600 input tokens (≈0.3 cents).
- The reference material is sent in Hebrew, as is (it is not translated).

### 9.2 Parameters
- `model`: from `config.json` (default `claude-sonnet-5-5`).
- `effort`: from `config.json` (default `low`).
- No prompt caching (handling one ad typically takes longer than the cache lifetime).
- Structured output: the response must match this JSON schema:

```json
{
  "type": "object",
  "properties": {
    "is_job_ad":    { "type": "boolean" },
    "rewritten_ad": { "type": "string" },
    "tags":         { "type": "array", "items": { "type": "string" } },
    "keywords":     { "type": "array", "items": { "type": "string" } },
    "score":        { "type": "integer" },
    "score_reason": { "type": "string" }
  },
  "required": ["is_job_ad", "rewritten_ad", "tags", "keywords", "score", "score_reason"],
  "additionalProperties": false
}
```

### 9.3 Checking the response
- `is_job_ad = false` → show "הטקסט אינו מודעת דרושים" (the text is not a job ad); nothing is saved.
- Tags and keywords that are not in the community's lists are removed and written to the log.
- `score` outside 0–100 is clamped to 0–100.
- Empty `rewritten_ad` on a job ad → treated as a failed call (§11).

### 9.4 Cost
Estimated $12–20 per 1,000 ads (Sonnet 5.5, effort `low`). Spending is limited by the limit set in the Anthropic console.

---

## 10. Browser Automation (Playwright + Edge)

- One Edge window, opened by the app with a persistent profile (`browser_profile\`), so logins are kept between runs.
- The same window is used for collecting and for distribution.
- The window is visible; the user does all browsing. The app never scrolls, clicks posts, or navigates within groups by itself.
- Closing the app closes the window.

### 10.1 Opening a source
| Type | What the app does |
|---|---|
| Facebook | Opens the group URL. The user logs in on first use. |
| Website | Opens the URL. |
| WhatsApp | Opens WhatsApp Web; the user scans the QR code on first use. The app tries to open the chat whose name matches the source name; if not found, the user opens the chat themselves. |

### 10.2 Capture
- Reads the text currently selected in the active tab. Only text is captured: images, videos and icons drawn as pictures are never included, so they are never sent to Sonnet.
- **Cleaning** (applied to captured and pasted text, before the preview):
  - Emojis and decorative symbols are removed (e.g. 📍 📞 ✅ 👇 ⭐).
  - Invisible characters are removed (e.g. direction marks such as ⁦ ⁩, zero-width spaces).
  - Repeated spaces and more than one empty line in a row are reduced to one.
  - Hebrew, English, digits, punctuation, emails, phone numbers and links are kept as is.
- Cleaning saves a little cost (emojis are a few tokens each) but mainly gives Sonnet cleaner input. The user can still edit the cleaned text in the preview.
- **Images:** the ad's details are often in an image. On Capture, the app also takes the images of the post that contains the selection (on Facebook, a post is a `role="article"` block; images of its comments are not taken). On other sites, it takes images inside the selection. Images are downloaded with the browser's own session. If an image is missed, the user copies it in Edge (right-click → Copy image) and pastes it in the preview.
- Facebook truncates long posts ("See more" / "עוד"): the user must expand the post before selecting it. The collecting screen shows this as a hint.

### 10.3 Distribution
1. The user clicks **הפצה** in the detailed screen.
2. The app opens WhatsApp Web, opens the community's distribution group (`whatsapp_group` in `config.json`), and fills the message box with `user_ad`.
3. The user checks the message in WhatsApp and presses Send.
4. The app asks "האם ההודעה נשלחה?" (was the message sent?). **Yes** → status `distributed`, `distribute_date` = now. **No** → nothing changes.
- The app never presses Send.

### 10.4 Logging in (Facebook and WhatsApp)
- Facebook's login can hang in a browser controlled by automation. So logging in is done in a **normal** Edge window, not controlled by the app, that uses the app's profile (`browser_profile\`).
- The menu button **התחברות לפייסבוק ולווטסאפ** closes the app's automated window, opens the normal window with Facebook and WhatsApp Web in two tabs, and shows instructions: log in to Facebook, scan the WhatsApp QR code, close the window, then click **סיימתי** (done). If Edge is still running in the background after that, the app waits a few seconds (Edge saves the logins on exit) and then closes it. "Keep running in the background" is turned off in the app's profile only, so Edge normally exits when its window closes.
- The logins are saved in the profile, so the automated window opens already logged in.
- If the user clicks Open source while the login window is still open, the app asks them to close it first (two windows cannot use the same profile).

---

## 11. Error Handling

| Situation | What the user sees | Notes |
|---|---|---|
| `config.json` or `api_key.json` missing or invalid | Error dialog naming the file and the problem; the app does not start | |
| Community file missing | Community listed but not selectable; missing file named (§6) | |
| Excel sheet or column missing | Error naming the sheet/column; community not loaded (§7) | |
| No internet | "אין חיבור לאינטרנט" (no internet connection); the captured text stays in the preview so nothing is lost | |
| Invalid API key | "מפתח ה-API אינו תקין" (the API key is invalid) — check `api_key.json` | |
| Spending limit reached / out of credit | "הגעת למגבלת השימוש ב-API" (API usage limit reached) | |
| API busy / temporary error | Retried automatically (2 times); then an error with **נסה שוב** (try again) | |
| Sonnet declines the request | "המודל סירב לעבד את המודעה" (the model declined to process the ad) | |
| Edge not found | Error explaining Edge is required | |
| Capture: nothing selected | "לא נבחר טקסט" (no text selected) | |
| WhatsApp Web logged out | Window shows the QR code; message asks the user to scan it | |
| Distribution group not found | "הקבוצה לא נמצאה" (group not found) + the text is copied to the clipboard so the user can paste it manually | |
| Message box fill fails | Text copied to the clipboard + message | |
| Database file missing | Created automatically (empty) | |
| Database corrupted | Error dialog; the app does not start | |

All errors are written to `logs\app.log` with details (never the API key).

---

## 12. Database

SQLite, file `data\ads.db`, one table `ads`:

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `community` | TEXT | community folder name |
| `collect_date` | TEXT | ISO date-time |
| `distribute_date` | TEXT | empty until distributed |
| `source_name` | TEXT | "ידני" for manual paste |
| `source_url` | TEXT | URL of the tab at capture time |
| `origin_ad` | TEXT | the ad text as sent to Sonnet (after cleaning and the user's preview edits); never changed |
| `origin_hash` | TEXT, indexed | fingerprint of `origin_ad` (and its images, if any) for the duplicate check (§8.2) |
| `origin_images` | TEXT | JSON list of the ad's image files in `data\images\` (`<id>_<n>.jpg`); shown with the original ad on the detailed screen |
| `sonnet_ad` | TEXT | Sonnet's rewrite; never changed |
| `user_ad` | TEXT | final text; starts as a copy of `sonnet_ad` |
| `status` | TEXT | `new` / `approved` / `rejected` / `distributed` |
| `tags` | TEXT | JSON list |
| `keywords` | TEXT | JSON list |
| `score` | INTEGER | 0–100 |
| `score_reason` | TEXT | |
| `model` | TEXT | model that produced `sonnet_ad` |
| `prompt_version` | TEXT | §13 |
| `updated_at` | TEXT | ISO date-time of the last change |

- Ads are never deleted.
- All text is stored as UTF-8.

---

## 13. Data for Training a Local Model (future)

The app collects what is needed to train a local rewriting model later:
- **Training pairs:** `origin_ad` (+ `origin_images`) → `user_ad`, for ads with status `approved` or `distributed`.
- **Corrections:** `sonnet_ad` vs `user_ad` shows what the user had to fix.
- **Prompt version:** `prompt_version` is the first 12 characters of a SHA-256 hash of the community's `system_prompt.txt` + `aids.xlsx` + `examples.txt`. The first time a version is used, the app copies the three files to `data\prompt_versions\<prompt_version>\`, so the exact instructions behind every ad are kept even after the files are edited.
- **Per community:** `community` allows training a model per community.

---

## 14. Hebrew Display

- Right-to-left layout for the whole UI.
- Text areas display mixed Hebrew/English text correctly (company names, emails, job titles).
- A font with full Hebrew support.
- All files are read and written as UTF-8.
- UI framework: PySide6 (Qt).

---

## 15. Installation and Updates

- The user receives one file, `setup.exe` (built with PyInstaller + Inno Setup).
- Install: Next, Next, Finish. No administrator rights. Installs to `%LOCALAPPDATA%\JobAds` with a desktop shortcut, a Start menu entry and an uninstaller.
- Nothing else to install: Python and all libraries are bundled; Playwright uses the PC's Edge.
- The EXE is not code-signed: on the first run Windows may show "Windows protected your PC" → the user clicks **More info → Run anyway** once.
- **Updates:** the user runs a new `setup.exe`. It replaces the program files (`JobAds.exe`, `_internal\`) and never overwrites `config.json`, `api_key.json`, `communities\`, `data\`, `browser_profile\`.
- **Uninstall** removes the program files; it asks before deleting `data\` (the ads database).

---

## 16. Technology

| Area | Choice |
|---|---|
| Language | Python 3.12 |
| UI | PySide6 |
| AI | Anthropic Python SDK, model `claude-sonnet-5-5` |
| Browser automation | Playwright, Microsoft Edge (`channel="msedge"`), persistent profile |
| Excel | openpyxl (reads hyperlinks too) |
| Database | SQLite (Python built-in) |
| Packaging | PyInstaller (one folder) + Inno Setup |

---

## 17. Acceptance Criteria

**Communities & files**
- With two community folders, the menu shows both; switching loads the other community's sources, tags and keywords, and the presenting screen shows only its ads.
- The app reopens with the last community used.
- Editing the Excel and clicking "Reload files" shows the change without restarting.
- The sources table shows the real URLs from the hyperlinks in `לינק`.

**Collecting**
- Selecting a post's text on Facebook, in WhatsApp Web and on a website, then clicking Capture, puts that exact text in the preview.
- Capturing with nothing selected shows "לא נבחר טקסט".
- Capturing the same ad twice shows the "ad already exists" warning, also when the second copy differs only in spacing or emojis.
- Captured text has no emojis or invisible characters; Hebrew, English, emails, phone numbers and links are unchanged.

**Rephrasing**
- A real job ad produces an ad in the `פורמט` format, with tags and keywords only from the community's lists, a score 0–100 and an explanation, saved as `new`.
- A non-job text (e.g. a chat message) shows "not a job ad" and is not saved.
- With the internet disconnected, an error is shown and the captured text is not lost.

**Review & distribution**
- Edited text is saved in `user_ad`; `origin_ad` and `sonnet_ad` do not change.
- An approved ad, after Distribute, appears in the WhatsApp message box of the configured group; nothing is sent until the user presses Send.
- Answering "yes" to "was the message sent?" sets `distributed` and the distribute date.

**Presenting**
- The list shows date, source, status, score, tags, keywords — no ad text.
- Each filter and each column sort works.

**Installation**
- On a clean Windows 11 PC with no Python, `setup.exe` installs without administrator rights and the app runs.
- Installing a newer `setup.exe` keeps the database, config, API key, communities and logins.

**Training data**
- Every saved ad has `community`, `model` and `prompt_version`, and the matching folder exists in `data\prompt_versions\`.

---

## 18. Decisions (resolved open questions)

1. **WhatsApp source names:** if a source name in `ערוצי איתור משרות` does not match the group name in WhatsApp, the user opens the chat manually (§10.1). No extra column.
2. **Distribution group** for the autism community: `thomas vinters`.
3. **First community:** folder `autism`, display name `אוטיזם`.
